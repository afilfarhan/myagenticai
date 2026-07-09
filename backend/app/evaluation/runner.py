"""
Evaluation runner for SentinelChain agents
"""
import asyncio
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import structlog

import weave
from weave import Evaluation

from app.agents import get_llm_gateway, LLMGateway, ProviderRole
from app.services.guardrails import get_guardrails, GuardrailsValidator
from app.evaluation.golden_set import (
    EvaluationCase, 
    ExpectedOutput, 
    ExpectedRiskFactor,
    ExpectedMitigation,
    ExpectedAlternative,
    golden_cases,
    get_cases_by_category
)
from app.models import RiskLevel, RiskCategory, EvidenceType, Evidence, Supplier, WorkflowType, RiskFactor

logger = structlog.get_logger(__name__)


@dataclass
class EvaluationResult:
    """Results from running evaluation on a case"""
    case_id: str
    agent: str
    scores: Dict[str, Any]
    output: Dict[str, Any]
    latency_ms: float
    timestamp: str
    passed: bool


class EvaluationRunner:
    """
    Complete evaluation harness for SentinelChain agents.
    Runs golden set through agents and scores with Weave.
    """
    
    def __init__(self, project: str = "sentinelchain-eval"):
        self.project = project
        self.llm_gateway: Optional[LLMGateway] = None
        self.guardrails: Optional[GuardrailsValidator] = None
        self.results: List[EvaluationResult] = []
        
        # Initialize Weave
        weave.init(project)
    
    async def initialize(self):
        """Initialize async components"""
        self.llm_gateway = await get_llm_gateway()
        self.guardrails = await get_guardrails()
    
    async def run_case(self, case: EvaluationCase, agent_name: str = "analyst") -> EvaluationResult:
        """Run a single evaluation case"""
        start_time = datetime.utcnow()
        
        # Prepare supplier and evidence
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
        
        # Run through agent
        if agent_name == "analyst":
            output = await self._run_analyst(supplier, evidence, case.query)
        elif agent_name == "auditor":
            output = await self._run_auditor(supplier, evidence)
        elif agent_name == "mitigator":
            # Need risk factors from analyst first
            analyst_output = await self._run_analyst(supplier, evidence, case.query)
            risk_factors = analyst_output.get("risk_factors", [])
            output = await self._run_mitigator(supplier, evidence, risk_factors)
        elif agent_name == "scout":
            output = await self._run_scout(supplier, evidence, case.query)
        else:
            raise ValueError(f"Unknown agent: {agent_name}")
        
        # Score against expected
        expected_dict = self._expected_to_dict(case.expected)
        scores = await self._score_output(output, expected_dict, agent_name)
        
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
        evidence_str = "\n".join([
            f"Evidence {i+1}:\n  Type: {e.type.value}\n  Source: {e.source}\n  Title: {e.title}\n  Content: {e.content[:800]}..."
            for i, e in enumerate(evidence)
        ])
        
        prompt = f"""You are the Analyst agent in SentinelChain, a supply chain risk analysis system.

Your task: analyze the following evidence about supplier "{supplier.name}" ({supplier.country}, {supplier.industry}) and identify risk factors.

## Evidence
{evidence_str}

## Instructions
1. Review each piece of evidence carefully.
2. Identify risk factors across these categories:
   - FINANCIAL (cash flow, debt, credit rating)
   - GEOPOLITICAL (trade wars, sanctions, port strikes, political instability)
   - REGULATORY (sanctions lists, export controls, new laws)
   - ESG (environmental violations, labor disputes, carbon footprint)
   - OPERATIONAL (factory fires, shipping delays, quality failures)
   - REPUTATIONAL (scandals, negative press, lawsuits)
   - CYBER (data breaches, vulnerabilities)
   - NATURAL_DISASTER (earthquakes, floods, hurricanes)
   - SUPPLIER_VIABILITY (bankruptcy risk, ownership changes)
3. Assign a RiskLevel to each: LOW, MEDIUM, HIGH, SEVERE, or CRITICAL
4. Assign a confidence score (0.0 to 1.0) based on evidence quality
5. For each risk factor, cite at least one evidence source
6. If evidence is insufficient to reach a confident assessment, say so explicitly

## Output Format (STRICT JSON - do not deviate)
{{
  "risk_factors": [
    {{
      "id": "rf-<uuid>",
      "category": "<RISK_CATEGORY>",
      "level": "<RISK_LEVEL>",
      "title": "<short title>",
      "description": "<1-2 sentence description>",
      "confidence": <float>,
      "evidence_ids": ["<evidence_index>"],
      "metadata": {{}}
    }}
  ],
  "needs_more_evidence": <bool>,
  "summary": "<1 paragraph summary>"
}}
"""
        
        response = await self.llm_gateway.complete(
            messages=[{"role": "user", "content": prompt}],
            role=ProviderRole.PRIMARY,
            temperature=0.1
        )
        
        # Parse and validate with guardrails
        try:
            parsed = json.loads(response)
            validated = await self.guardrails.validate_risk_output(response)
            return validated
        except Exception as e:
            logger.warning("Analyst output parse/validation failed", error=str(e))
            return {
                "risk_factors": [],
                "needs_more_evidence": True,
                "summary": f"Parse failed: {str(e)}"
            }
    
    async def _run_auditor(self, supplier: Supplier, evidence: List[Evidence]) -> Dict[str, Any]:
        """Run auditor agent"""
        evidence_str = "\n".join([
            f"- {e.type.value} ({e.source}): {e.title}\n  {e.content[:400]}..."
            for e in evidence
        ])
        
        prompt = f"""You are the Auditor agent in SentinelChain. Verify compliance for supplier "{supplier.name}" ({supplier.country}, {supplier.industry}).

## Evidence
{evidence_str}

## Compliance Frameworks to Check
- OFAC SDN List (US sanctions)
- EU CSDDD (Corporate Sustainability Due Diligence Directive)
- Export Control Regulations (EAR, ITAR)
- ESG Frameworks (GRI, SASB, TCFD)
- Anti-Money Laundering (AML)
- Forced Labor / Modern Slavery Acts
- Environmental Regulations

## Output Format (STRICT JSON)
{{
  "compliance_results": [
    {{
      "framework": "OFAC",
      "requirement": "Sanctions screening",
      "status": "COMPLIANT|NON_COMPLIANT|PARTIAL|NOT_APPLICABLE",
      "evidence": "specific evidence reference",
      "confidence": 0.9
    }}
  ],
  "hitl_required": true/false,
  "hitl_recommendation": "FREEZE_PAYMENTS|INVESTIGATE_FURTHER|ESCALATE"
}}
"""
        
        response = await self.llm_gateway.complete(
            messages=[{"role": "user", "content": prompt}],
            role=ProviderRole.SECURE,
            temperature=0.1
        )
        
        return json.loads(response)
    
    async def _run_mitigator(self, supplier: Supplier, evidence: List[Evidence], risk_factors: List[Dict]) -> Dict[str, Any]:
        """Run mitigator agent"""
        risk_str = json.dumps(risk_factors, indent=2)
        
        prompt = f"""You are the Mitigator agent in SentinelChain. Given identified risk factors for supplier "{supplier.name}", generate mitigation actions and suggest alternative suppliers.

## Risk Factors
{risk_str}

## Instructions
1. For each HIGH, SEVERE, and CRITICAL risk factor, generate 1-3 specific mitigation actions
2. Mitigation actions must include: title, description, estimated_cost_usd, estimated_timeline_days, priority (HIGH/MEDIUM/LOW)
3. Suggest 3 alternative suppliers (real or plausible industry peers) with:
   - name, country, industry, estimated_risk_score, cost_advantage_pct, lead_time_days

## Output Format (STRICT JSON)
{{
  "mitigation_actions": [
    {{
      "id": "ma-<uuid>",
      "risk_factor_id": "<rf_id>",
      "title": "<action title>",
      "description": "<detailed description>",
      "action_type": "<type>",
      "estimated_cost_usd": <number|null>,
      "estimated_timeline_days": <number|null>,
      "priority": "HIGH|MEDIUM|LOW",
      "status": "PROPOSED"
    }}
  ],
  "alternative_suppliers": [
    {{
      "id": "as-<uuid>",
      "name": "<supplier name>",
      "country": "<country>",
      "industry": "<industry>",
      "estimated_risk_score": <0-100>,
      "cost_advantage_pct": <number|null>,
      "lead_time_days": <number|null>,
      "quality_rating": <number|null>,
      "certifications": []
    }}
  ],
  "summary": "<1 paragraph summary>"
}}
"""
        
        response = await self.llm_gateway.complete(
            messages=[{"role": "user", "content": prompt}],
            role=ProviderRole.PRIMARY,
            temperature=0.1
        )
        
        return json.loads(response)
    
    async def _run_scout(self, supplier: Supplier, evidence: List[Evidence], query: str) -> Dict[str, Any]:
        """Run scout agent - returns evidence gathered"""
        # For evaluation, we just return the input evidence
        return {
            "evidence_count": len(evidence),
            "evidence_types": [e.type.value for e in evidence],
            "sources": list(set(e.source for e in evidence))
        }
    
    def _expected_to_dict(self, expected: ExpectedOutput) -> Dict[str, Any]:
        """Convert ExpectedOutput to dict for scoring"""
        return {
            "risk_factors": [
                {
                    "category": rf.category.value,
                    "level": rf.level.value,
                    "title_contains": rf.title_contains,
                    "description_contains": rf.description_contains,
                    "min_confidence": rf.min_confidence,
                    "required_evidence_types": [et.value for et in rf.required_evidence_types]
                }
                for rf in expected.risk_factors
            ],
            "mitigations": [
                {
                    "risk_factor_title_contains": m.risk_factor_title_contains,
                    "title_contains": m.title_contains,
                    "priority": m.priority,
                    "action_type": m.action_type
                }
                for m in expected.mitigations
            ],
            "alternatives": [
                {
                    "name_contains": a.name_contains,
                    "country": a.country,
                    "max_risk_score": a.max_risk_score
                }
                for a in expected.alternatives
            ],
            "hitl_required": expected.hitl_required,
            "hitl_recommendation": expected.hitl_recommendation
        }
    
    async def _score_output(self, output: Dict[str, Any], expected: Dict[str, Any], agent: str) -> Dict[str, Any]:
        """Score output against expected using multiple metrics"""
        scores = {}
        
        # Risk Factor F1 Score
        pred_factors = output.get("risk_factors", [])
        exp_factors = expected.get("risk_factors", [])
        
        if exp_factors:
            matched = 0
            for exp in exp_factors:
                for pred in pred_factors:
                    if pred.get("category") == exp.get("category") and pred.get("level") == exp.get("level"):
                        matched += 1
                        break
            
            precision = matched / len(pred_factors) if pred_factors else 0
            recall = matched / len(exp_factors) if exp_factors else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            scores["risk_factor_f1"] = {
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "matched": matched,
                "total_pred": len(pred_factors),
                "total_expected": len(exp_factors)
            }
        else:
            scores["risk_factor_f1"] = {"f1": 1.0 if not pred_factors else 0.0}
        
        # Evidence Citation Rate
        if pred_factors:
            cited = sum(1 for f in pred_factors if f.get("evidence_ids") and len(f["evidence_ids"]) > 0)
            scores["evidence_citation_rate"] = cited / len(pred_factors)
        else:
            scores["evidence_citation_rate"] = 0.0
        
        # HITL Accuracy (for auditor)
        if agent == "auditor":
            hitl_pred = output.get("hitl_required", False)
            hitl_exp = expected.get("hitl_required", False)
            rec_pred = output.get("hitl_recommendation", "")
            rec_exp = expected.get("hitl_recommendation", "")
            
            scores["hitl_accuracy"] = 1.0 if hitl_pred == hitl_exp else 0.0
            scores["recommendation_accuracy"] = 1.0 if rec_pred == rec_exp else 0.0
        
        # Mitigation Coverage (for mitigator)
        if agent == "mitigator":
            pred_mit = output.get("mitigation_actions", [])
            exp_mit = expected.get("mitigations", [])
            
            if exp_mit:
                covered = 0
                for exp in exp_mit:
                    for pred in pred_mit:
                        if pred.get("risk_factor_id") == exp.get("risk_factor_title_contains"):
                            covered += 1
                            break
                scores["mitigation_coverage"] = covered / len(exp_mit)
            else:
                scores["mitigation_coverage"] = 1.0 if not pred_mit else 0.5
            
            # Alternative quality
            pred_alts = output.get("alternative_suppliers", [])
            exp_alts = expected.get("alternatives", [])
            
            if exp_alts:
                valid_risk = sum(1 for a in pred_alts if a.get("risk_score", 100) < 40)
                scores["alternative_risk_rate"] = valid_risk / len(pred_alts) if pred_alts else 0
                scores["alternative_count_coverage"] = min(len(pred_alts) / len(exp_alts), 1.0)
        
        return scores
    
    def _check_pass(self, scores: Dict[str, Any], agent: str) -> bool:
        """Check if scores meet minimum thresholds"""
        thresholds = {
            "risk_factor_f1": 0.85,
            "evidence_citation_rate": 1.0,
            "hitl_accuracy": 0.95,
            "recommendation_accuracy": 0.95,
            "mitigation_coverage": 0.80,
            "alternative_risk_rate": 0.90,
            "alternative_count_coverage": 0.75
        }
        
        for metric, threshold in thresholds.items():
            if metric in scores:
                value = scores[metric]
                if isinstance(value, dict) and "f1" in value:
                    value = value["f1"]
                if value < threshold:
                    return False
        return True
    
    async def run_suite(self, cases: List[EvaluationCase], agents: List[str] = None) -> Dict[str, Any]:
        """Run evaluation suite on multiple cases"""
        if agents is None:
            agents = ["analyst", "auditor", "mitigator"]
        
        all_results = {}
        
        for agent in agents:
            logger.info(f"Running evaluation for {agent} agent", case_count=len(cases))
            agent_results = []
            
            for case in cases:
                try:
                    result = await self.run_case(case, agent)
                    agent_results.append(result)
                    logger.info(f"Case {case.case_id} {agent}: {'PASS' if result.passed else 'FAIL'}")
                except Exception as e:
                    logger.error(f"Case {case.case_id} {agent} failed", error=str(e))
                    agent_results.append(EvaluationResult(
                        case_id=case.case_id,
                        agent=agent,
                        scores={"error": str(e)},
                        output={},
                        latency_ms=0,
                        timestamp=datetime.utcnow().isoformat(),
                        passed=False
                    ))
            
            all_results[agent] = agent_results
        
        # Aggregate summary
        summary = self._generate_summary(all_results)
        return {"results": all_results, "summary": summary}
    
    def _generate_summary(self, all_results: Dict[str, List[EvaluationResult]]) -> Dict[str, Any]:
        """Generate evaluation summary"""
        summary = {}
        
        for agent, results in all_results.items():
            passed = sum(1 for r in results if r.passed)
            total = len(results)
            avg_latency = sum(r.latency_ms for r in results) / total if total > 0 else 0
            
            summary[agent] = {
                "passed": passed,
                "total": total,
                "pass_rate": passed / total if total > 0 else 0,
                "avg_latency_ms": avg_latency
            }
        
        overall_passed = sum(s["passed"] for s in summary.values())
        overall_total = sum(s["total"] for s in summary.values())
        summary["overall"] = {
            "passed": overall_passed,
            "total": overall_total,
            "pass_rate": overall_passed / overall_total if overall_total > 0 else 0
        }
        
        return summary
    
    def save_results(self, filepath: str):
        """Save results to JSON file"""
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "project": self.project,
            "results": [asdict(r) for r in self.results]
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)


# Convenience function for running evaluation
async def run_evaluation(
    cases: List[EvaluationCase] = None,
    agents: List[str] = None,
    project: str = "sentinelchain-eval"
) -> Dict[str, Any]:
    """Run complete evaluation suite"""
    if cases is None:
        cases = golden_cases
    if agents is None:
        agents = ["analyst", "auditor", "mitigator"]
    
    runner = EvaluationRunner(project)
    await runner.initialize()
    
    return await runner.run_suite(cases, agents)