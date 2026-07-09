"""
W&B Weave Evaluation Harness for SentinelChain
"""
import asyncio
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import structlog

import weave
from weave import Evaluation, Scorer

from app.agents import get_llm_gateway, LLMGateway
from app.evaluation.golden_set import EvaluationCase, ExpectedOutput, ExpectedRiskFactor, get_cases_by_category
from app.models import RiskLevel, RiskCategory, EvidenceType, Evidence, Supplier, WorkflowType
from app.services.guardrails import get_guardrails, GuardrailsValidator

logger = structlog.get_logger(__name__)


# Weave scorers for evaluation
class RiskFactorF1Scorer(Scorer):
    """Scorer for risk factor F1 score (precision/recall/F1 per category)"""
    
    @weave.op()
    def score(self, output: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, float]:
        pred_factors = output.get("risk_factors", [])
        expected_factors = expected.get("risk_factors", [])
        
        if not expected_factors:
            return {"f1": 1.0 if not pred_factors else 0.0}
        
        # Match by category and level
        matched = 0
        for exp in expected_factors:
            exp_cat = exp.get("category")
            exp_level = exp.get("level")
            for pred in pred_factors:
                if pred.get("category") == exp_cat and pred.get("level") == exp_level:
                    matched += 1
                    break
        
        precision = matched / len(pred_factors) if pred_factors else 0
        recall = matched / len(expected_factors) if expected_factors else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "matched": matched,
            "total_pred": len(pred_factors),
            "total_expected": len(expected_factors)
        }


class EvidenceCitationScorer(Scorer):
    """Scorer for evidence citation completeness"""
    
    @weave.op()
    def score(self, output: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, float]:
        pred_factors = output.get("risk_factors", [])
        
        if not pred_factors:
            return {"citation_rate": 0.0}
        
        cited = sum(1 for f in pred_factors if f.get("evidence_ids") and len(f["evidence_ids"]) > 0)
        rate = cited / len(pred_factors)
        
        return {"citation_rate": rate, "cited": cited, "total": len(pred_factors)}


class ComplianceAccuracyScorer(Scorer):
    """Scorer for auditor compliance accuracy"""
    
    @weave.op()
    def score(self, output: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, float]:
        hitl_pred = output.get("hitl_required", False)
        hitl_expected = expected.get("hitl_required", False)
        
        recommendation_pred = output.get("hitl_recommendation", "")
        recommendation_expected = expected.get("hitl_recommendation", "")
        
        hitl_correct = hitl_pred == hitl_expected
        rec_correct = recommendation_pred == recommendation_expected
        
        return {
            "hitl_accuracy": 1.0 if hitl_correct else 0.0,
            "recommendation_accuracy": 1.0 if rec_correct else 0.0,
            "overall": 1.0 if (hitl_correct and rec_correct) else 0.0
        }


class MitigationRelevanceScorer(Scorer):
    """Scorer for mitigation action relevance (LLM-as-judge via Weave)"""
    
    def __init__(self, llm_gateway):
        self.llm_gateway = llm_gateway
    
    @weave.op()
    async def score(self, output: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, float]:
        pred_mitigations = output.get("mitigation_actions", [])
        expected_mitigations = expected.get("mitigations", [])
        
        if not expected_mitigations:
            return {"relevance": 1.0 if not pred_mitigations else 0.5}
        
        # Use LLM to judge relevance
        prompt = f"""
        Evaluate the relevance of predicted mitigation actions vs expected.
        
        Expected mitigations:
        {json.dumps(expected_mitigations, indent=2)}
        
        Predicted mitigations:
        {json.dumps(pred_mitigations, indent=2)}
        
        Score each predicted mitigation 0-5 for relevance to the risk factors.
        Return JSON: {{"scores": [int], "average": float, "coverage": float}}
        """
        
        try:
            response = await self.llm_gateway.complete(
                messages=[{"role": "user", "content": prompt}],
                role="analyst",
                temperature=0.1
            )
            result = json.loads(response)
            return result
        except Exception as e:
            logger.warning("LLM judge failed", error=str(e))
            # Fallback: simple coverage check
            covered = 0
            for exp in expected_mitigations:
                for pred in pred_mitigations:
                    if pred.get("risk_factor_id") == exp.get("risk_factor_id"):
                        covered += 1
                        break
            coverage = covered / len(expected_mitigations)
            return {"coverage": coverage, "average": 3.0, "scores": []}


class AlternativeQualityScorer(Scorer):
    """Scorer for alternative supplier quality"""
    
    @weave.op()
    def score(self, output: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, float]:
        pred_alts = output.get("alternative_suppliers", [])
        expected_alts = expected.get("alternatives", [])
        
        if not expected_alts:
            return {"quality": 1.0 if not pred_alts else 0.5}
        
        # Check risk scores are below threshold
        valid_risk = sum(1 for a in pred_alts if a.get("risk_score", 100) < 40)
        risk_score_rate = valid_risk / len(pred_alts) if pred_alts else 0
        
        # Check count
        count_score = min(len(pred_alts) / max(len(expected_alts), 1), 1.0)
        
        return {
            "risk_score_rate": risk_score_rate,
            "count_coverage": count_score,
            "overall": (risk_score_rate + count_score) / 2
        }


@dataclass
class EvaluationResult:
    """Results from running evaluation on a case"""
    case_id: str
    agent: str
    scores: Dict[str, float]
    output: Dict[str, Any]
    latency_ms: float
    timestamp: str
    passed: bool


class EvaluationHarness:
    """
    Complete evaluation harness for SentinelChain agents.
    Runs golden set through agents and scores with Weave.
    """
    
    def __init__(self, project: str = "sentinelchain-eval"):
        self.project = project
        self.llm_gateway = None
        self.guardrails = None
        self.results: List[EvaluationResult] = []
        
        # Initialize Weave
        weave.init(project)
        
        # Register scorers
        self.scorers = {
            "risk_f1": RiskFactorF1Scorer(),
            "evidence_citation": EvidenceCitationScorer(),
            "compliance": ComplianceAccuracyScorer(),
            "mitigation_relevance": None,  # Initialized async
            "alternative_quality": AlternativeQualityScorer(),
        }
    
    async def initialize(self):
        """Initialize async components"""
        self.llm_gateway = await get_llm_gateway()
        self.guardrails = await get_guardrails()
        self.scorers["mitigation_relevance"] = MitigationRelevanceScorer(self.llm_gateway)
        
        # Initialize Weave evaluation
        self.evaluation = Evaluation(
            name="sentinelchain_agent_eval",
            scorers=list(self.scorers.values())
        )
    
    async def run_case(self, case: EvaluationCase, agent_name: str = "analyst") -> EvaluationResult:
        """Run a single evaluation case"""
        start_time = datetime.utcnow()
        
        # Prepare input for agent
        supplier = Supplier(
            name=case.supplier_name,
            country=case.supplier_country,
            industry=case.supplier_industry
        )
        
        evidence = [
            Evidence(
                supplier_id=supplier.id,
                type=EvidenceType(e["type"]),
                source=e["source"],
                title=e["title"],
                content=e["content"],
                url=e.get("url"),
                credibility_score=e.get("credibility_score", 0.5),
                relevance_score=e.get("relevance_score", 0.5)
            )
            for e in case.evidence
        ]
        
        # Run through agent (using LLM gateway directly for evaluation)
        if agent_name == "analyst":
            output = await self._run_analyst(supplier, evidence, case.query)
        elif agent_name == "auditor":
            output = await self._run_auditor(supplier, evidence)
        elif agent_name == "mitigator":
            output = await self._run_mitigator(supplier, evidence, output)  # Needs risk factors
        else:
            raise ValueError(f"Unknown agent: {agent_name}")
        
        # Score against expected
        expected_dict = self._expected_to_dict(case.expected)
        scores = {}
        for name, scorer in self.scorers.items():
            if scorer:
                try:
                    if asyncio.iscoroutinefunction(scorer.score):
                        scores[name] = await scorer.score(output, expected_dict)
                    else:
                        scores[name] = scorer.score(output, expected_dict)
                except Exception as e:
                    logger.warning(f"Scorer {name} failed", error=str(e))
                    scores[name] = {"error": str(e)}
        
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Determine pass/fail
        passed = self._check_pass(scores, agent_name)
        
        result = EvaluationResult(
            case_id=case.case_id,
            agent=agent_name,
            scores=scores,
            output=output,
            latency_ms=latency_ms,
            timestamp=datetime.utcnow().isoformat(),
            passed=passed
        )
        
        self.results.append(result)
        return result
    
    async def _run_analyst(self, supplier: Supplier, evidence: List[Evidence], query: str) -> Dict[str, Any]:
        """Run analyst agent via LLM gateway"""
        prompt = self._build_analyst_prompt(supplier, evidence, query)
        
        response = await self.llm_gateway.complete(
            messages=[{"role": "user", "content": prompt}],
            role="analyst",
            temperature=0.1
        )
        
        # Parse and validate with guardrails
        try:
            parsed = json.loads(response)
            validated = await self.guardrails.validate_risk_output(response)
            return validated
        except Exception:
            # Return structured fallback
            return {
                "risk_factors": [],
                "needs_more_evidence": True,
                "summary": "Parse failed"
            }
    
    async def _run_auditor(self, supplier: Supplier, evidence: List[Evidence]) -> Dict[str, Any]:
        """Run auditor agent"""
        prompt = f"""
        You are the Auditor agent. Verify compliance for supplier {supplier.name} ({supplier.country}).
        
        Evidence:
        {json.dumps([e.model_dump() for e in evidence], default=str, indent=2)}
        
        Check against: OFAC sanctions, EU CSDDD, export controls, ESG frameworks.
        
        Output strict JSON:
        {{
            "compliance_results": [
                {{"framework": "OFAC", "requirement": "Sanctions screening", "status": "COMPLIANT|NON_COMPLIANT|PARTIAL|NOT_APPLICABLE", "evidence": "...", "confidence": 0.9}}
            ],
            "hitl_required": true/false,
            "hitl_recommendation": "FREEZE_PAYMENTS|INVESTIGATE_FURTHER|ESCALATE"
        }}
        """
        
        response = await self.llm_gateway.complete(
            messages=[{"role": "user", "content": prompt}],
            role="secure",
            temperature=0.1
        )
        
        return json.loads(response)
    
    async def _run_mitigator(self, supplier: Supplier, evidence: List[Evidence], risk_factors: List[Dict]) -> Dict[str, Any]:
        """Run mitigator agent"""
        prompt = f"""
        You are the Mitigator agent. Generate mitigation actions for supplier {supplier.name}.
        
        Risk factors:
        {json.dumps(risk_factors, indent=2)}
        
        Output strict JSON:
        {{
            "mitigation_actions": [
                {{"id": "ma-...", "risk_factor_id": "...", "title": "...", "description": "...", "action_type": "...", "priority": 1-5, "status": "PROPOSED"}}
            ],
            "alternative_suppliers": [
                {{"id": "as-...", "name": "...", "country": "...", "risk_score": 0-100, "cost_diff_pct": -10.5, "lead_time_days": 14}}
            ],
            "summary": "..."
        }}
        """
        
        response = await self.llm_gateway.complete(
            messages=[{"role": "user", "content": prompt}],
            role="analyst",
            temperature=0.1
        )
        
        return json.loads(response)
    
    def _build_analyst_prompt(self, supplier: Supplier, evidence: List[Evidence], query: str) -> str:
        evidence_str = "\n".join([
            f"- {e.type.value} ({e.source}): {e.title}\n  {e.content[:500]}..."
            for e in evidence
        ])
        
        return f"""
        You are the Analyst agent. Analyze supplier {supplier.name} ({supplier.country}, {supplier.industry}).
        
        Query: {query}
        
        Evidence:
        {evidence_str}
        
        Identify risk factors across: FINANCIAL, GEOPOLITICAL, REGULATORY, ESG, OPERATIONAL, CYBER, REPUTATIONAL
        
        Output STRICT JSON:
        {{
            "risk_factors": [
                {{
                    "id": "rf-...",
                    "category": "FINANCIAL",
                    "level": "HIGH",
                    "title": "...",
                    "description": "...",
                    "confidence": 0.85,
                    "evidence_ids": ["..."],
                    "metadata": {{}}
                }}
            ],
            "needs_more_evidence": false,
            "summary": "..."
        }}
        """
    
    def _expected_to_dict(self, expected: ExpectedOutput) -> Dict[str, Any]:
        return {
            "risk_factors": [
                {
                    "category": rf.category.value,
                    "level": rf.level.value,
                    "title_contains": rf.title_contains,
                    "min_confidence": rf.min_confidence
                }
                for rf in expected.risk_factors
            ],
            "mitigations": [
                {
                    "risk_factor_title_contains": m.risk_factor_title_contains,
                    "title_contains": m.title_contains,
                    "priority": m.priority
                }
                for m in expected.mitigations
            ],
            "alternatives": [
                {"name_contains": a.name_contains, "country": a.country, "max_risk_score": a.max_risk_score}
                for a in expected.alternatives
            ],
            "hitl_required": expected.hitl_required,
            "hitl_recommendation": expected.hitl_recommendation
        }
    
    def _check_pass(self, scores: Dict[str, Any], agent: str) -> bool:
        """Check if evaluation passes thresholds"""
        thresholds = {
            "analyst": {"risk_f1.f1": 0.85, "evidence_citation.citation_rate": 1.0},
            "auditor": {"compliance.overall": 0.95},
            "mitigator": {"mitigation_relevance.coverage": 0.8, "alternative_quality.overall": 0.75}
        }
        
        agent_thresholds = thresholds.get(agent, {})
        for metric, threshold in agent_thresholds.items():
            parts = metric.split(".")
            value = scores
            try:
                for p in parts:
                    value = value.get(p, 0)
                if value < threshold:
                    return False
            except Exception:
                return False
        return True
    
    def get_summary(self) -> Dict[str, Any]:
        """Get evaluation summary"""
        if not self.results:
            return {}
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        
        avg_latency = sum(r.latency_ms for r in self.results) / total
        
        by_agent = {}
        for r in self.results:
            if r.agent not in by_agent:
                by_agent[r.agent] = {"total": 0, "passed": 0}
            by_agent[r.agent]["total"] += 1
            if r.passed:
                by_agent[r.agent]["passed"] += 1
        
        return {
            "total_cases": total,
            "passed": passed,
            "pass_rate": passed / total,
            "avg_latency_ms": avg_latency,
            "by_agent": by_agent
        }
    
    def export_results(self, filepath: str):
        """Export results to JSON"""
        data = {
            "summary": self.get_summary(),
            "results": [asdict(r) for r in self.results]
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)


async def run_full_evaluation() -> EvaluationHarness:
    """Run complete evaluation suite"""
    harness = EvaluationHarness()
    await harness.initialize()
    
    # Get cases by category
    from app.evaluation.golden_set import get_cases_by_category
    
    categories = ["financial_distress", "sanctions_violation", "esg_violation", "geopolitical", "cyber", "low_risk"]
    
    for category in categories:
        cases = get_cases_by_category(category)
        logger.info(f"Evaluating {len(cases)} cases for {category}")
        
        for case in cases:
            # Run analyst evaluation
            await harness.run_case(case, "analyst")
            
            # Run auditor evaluation
            await harness.run_case(case, "auditor")
    
    # Run mitigator on all cases
    for case in golden_cases:
        await harness.run_case(case, "mitigator")
    
    logger.info("Evaluation complete", summary=harness.get_summary())
    return harness


# Global golden set import
from app.evaluation.golden_set import golden_cases