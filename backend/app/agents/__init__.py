"""
Core agent implementations for SentinelChain with real tool integrations
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID
import structlog
import json
import os

from app.models import (
    AgentRole, WorkflowState, Evidence, RiskFactor, 
    MitigationAction, AlternativeSupplier, Supplier,
    RiskLevel, RiskCategory, EvidenceType, WorkflowType
)
from app.tools import get_tool_registry, ToolResult
from app.memory import get_memory_manager, MemoryManager
from app.services.guardrails import get_guardrails, GuardrailsValidator
from app.services.pii_masking import get_pii_masker, PIIMasker
from app.services.embeddings import get_embedding_service, EmbeddingService
from app.services.llm_gateway import get_llm_gateway, LLMGateway, ProviderRole
from app.config import get_config

# LangSmith tracing
try:
    from langsmith import traceable
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

logger = structlog.get_logger(__name__)


class AgentContext(BaseModel):
    """Context passed between agents in the workflow"""
    workflow_id: UUID
    supplier: Optional[Supplier] = None
    supplier_id: Optional[UUID] = None
    query: Optional[str] = None
    evidence: List[Evidence] = Field(default_factory=list)
    risk_factors: List[RiskFactor] = Field(default_factory=list)
    mitigation_actions: List[MitigationAction] = Field(default_factory=list)
    alternative_suppliers: List[AlternativeSupplier] = Field(default_factory=list)
    state_data: Dict[str, Any] = Field(default_factory=dict)
    hitl_required: bool = False
    hitl_payload: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    step_count: int = 0
    max_steps: int = 10


class AgentResult(BaseModel):
    """Result returned by an agent after processing"""
    success: bool
    context: AgentContext
    messages: List[str] = Field(default_factory=list)
    next_agent: Optional[AgentRole] = None
    should_continue: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseAgent(ABC):
    """Base class for all SentinelChain agents"""
    
    def __init__(self, role: AgentRole, config: Dict[str, Any] = None):
        self.role = role
        self.config = config or {}
        self.logger = logger.bind(agent_role=role.value)
        
        # Initialize services
        self.tool_registry = None
        self.memory_manager = None
        self.guardrails = None
        self.pii_masker = None
        self.embeddings = None
        self.llm_gateway = None
    
    async def _initialize_services(self):
        """Lazy initialization of services"""
        if self.tool_registry is None:
            self.tool_registry = get_tool_registry()
        if self.memory_manager is None:
            self.memory_manager = await get_memory_manager()
        if self.guardrails is None:
            self.guardrails = await get_guardrails()
        if self.pii_masker is None:
            self.pii_masker = get_pii_masker()
        if self.embeddings is None:
            self.embeddings = await get_embedding_service()
        if self.llm_gateway is None:
            self.llm_gateway = await get_llm_gateway()
    
    @abstractmethod
    async def process(self, context: AgentContext) -> AgentResult:
        """Process the context and return results"""
        pass
    
    @abstractmethod
    async def get_capabilities(self) -> List[str]:
        """Return list of capabilities this agent provides"""
        pass
    
    async def _emit_message(self, context: AgentContext, message: str, metadata: Dict[str, Any] = None):
        """Emit a message for logging/tracing"""
        self.logger.info(message, workflow_id=str(context.workflow_id), metadata=metadata or {})
        context.state_data.setdefault("agent_messages", []).append({
            "agent": self.role.value,
            "message": message,
            "metadata": metadata or {}
        })
        
        # Send to Redis pub/sub for SSE streaming
        if self.memory_manager and self.memory_manager.redis:
            await self.memory_manager.send_agent_message(
                self.role.value,
                AgentMessage(
                    workflow_id=context.workflow_id,
                    from_agent=self.role,
                    to_agent=None,
                    message_type="info",
                    content=message,
                    metadata=metadata or {}
                )
            )
    
    def _increment_step(self, context: AgentContext) -> bool:
        """Increment step counter and check if we should continue"""
        context.step_count += 1
        if context.step_count >= context.max_steps:
            self.logger.warning("Max steps reached", workflow_id=str(context.workflow_id), step_count=context.step_count)
            context.error = "Max steps exceeded"
            return False
        return True
    
    async def _execute_tool(self, tool_name: str, params: Dict[str, Any]) -> ToolResult:
        """Execute a tool via the registry"""
        await self._initialize_services()
        return await self.tool_registry.execute_tool(tool_name, params)
    
    async def _call_llm(
        self, 
        messages: List[Dict[str, str]], 
        role: ProviderRole = ProviderRole.PRIMARY,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        **kwargs
    ) -> str:
        """Call LLM via gateway with automatic failover"""
        await self._initialize_services()
        return await self.llm_gateway.complete(
            messages=messages,
            role=role,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    @traceable(run_type="llm", name="agent_llm_call")
    async def _traced_llm_call(
        self,
        messages: List[Dict[str, str]],
        role: ProviderRole = ProviderRole.PRIMARY,
        workflow_id: UUID = None,
        step_name: str = "llm_call",
        **kwargs
    ) -> str:
        """Traced LLM call with LangSmith metadata"""
        return await self._call_llm(messages, role, **kwargs)


class ScoutAgent(BaseAgent):
    """Scout Agent - Data Acquisition specialist"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(AgentRole.SCOUT, config)
    
    async def get_capabilities(self) -> List[str]:
        return [
            "sanctions_list_monitoring",
            "news_monitoring",
            "financial_report_retrieval",
            "satellite_imagery_analysis",
            "government_registry_search",
            "supplier_relationship_mapping",
            "dark_web_monitoring"
        ]
    
    @traceable(run_type="chain", name="ScoutAgent.process")
    async def process(self, context: AgentContext) -> AgentResult:
        await self._initialize_services()
        await self._emit_message(context, "Scout agent starting data acquisition")
        
        if not self._increment_step(context):
            return AgentResult(success=False, context=context, error="Max steps exceeded")
        
        if not context.supplier_id and not context.supplier:
            return AgentResult(
                success=False, 
                context=context, 
                error="No supplier specified",
                next_agent=None
            )
        
        supplier_id = context.supplier_id or context.supplier.id
        supplier_name = context.supplier.name if context.supplier else "Unknown"
        
        # Gather evidence from multiple sources
        evidence = await self._gather_evidence(context, supplier_id, supplier_name)
        
        context.evidence.extend(evidence)
        await self._emit_message(context, f"Scout gathered {len(evidence)} pieces of evidence")
        
        # Store evidence in memory
        for ev in evidence:
            await self.memory_manager.store_evidence(ev, supplier_id)
        
        return AgentResult(
            success=True,
            context=context,
            next_agent=AgentRole.ANALYST,
            messages=[f"Found {len(evidence)} relevant data points from multiple sources"]
        )
    
    async def _gather_evidence(self, context: AgentContext, supplier_id: UUID, supplier_name: str) -> List[Evidence]:
        """Gather evidence from various sources"""
        evidence = []
        
        # 1. Tavily - News search
        news_results = await self._execute_tool("tavily_search", {
            "query": f"{supplier_name} supply chain risk financial news",
            "max_results": 10,
            "search_depth": "advanced"
        })
        
        if news_results.success and news_results.data:
            for item in news_results.data:
                ev = Evidence(
                    supplier_id=supplier_id,
                    type=EvidenceType.NEWS_ARTICLE,
                    source="tavily",
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    url=item.get("url"),
                    credibility_score=0.7,
                    relevance_score=0.8
                )
                evidence.append(ev)
        
        # 2. Exa - Semantic search for financial reports
        financial_results = await self._execute_tool("exa_search", {
            "query": f"{supplier_name} financial report 10-K 10-Q earnings",
            "max_results": 5,
            "category": "financial"
        })
        
        if financial_results.success and financial_results.data:
            for item in financial_results.data:
                ev = Evidence(
                    supplier_id=supplier_id,
                    type=EvidenceType.FINANCIAL_REPORT,
                    source="exa",
                    title=item.get("title", ""),
                    content=item.get("text", "")[:5000],
                    url=item.get("url"),
                    credibility_score=0.85,
                    relevance_score=0.75
                )
                evidence.append(ev)
        
        # 3. Apify - Sanctions list check
        sanctions_results = await self._execute_tool("apify_scraper", {
            "actor_id": "apify/eu-sanctions-list",
            "run_input": {"entity_name": supplier_name}
        })
        
        if sanctions_results.success and sanctions_results.data:
            for item in sanctions_results.data:
                ev = Evidence(
                    supplier_id=supplier_id,
                    type=EvidenceType.SANCTIONS_LIST,
                    source="apify_eu_sanctions",
                    title=f"Sanctions check: {item.get('entity_name', 'Unknown')}",
                    content=json.dumps(item),
                    url=item.get("source_url"),
                    credibility_score=0.95,
                    relevance_score=0.9
                )
                evidence.append(ev)
        
        # 4. Vector search - Similar suppliers with risk history
        if self.memory_manager.vector_store.is_ready():
            supplier_text = f"{supplier_name} {context.supplier.country if context.supplier else ''} {context.supplier.industry if context.supplier else ''}"
            supplier_embedding = await self.embeddings.embed(supplier_text)
            similar = await self.memory_manager.vector_store.search_similar_suppliers(
                supplier_embedding, top_k=5
            )
            
            for match in similar:
                if match.get("metadata", {}).get("risk_score", 0) > 50:
                    ev = Evidence(
                        supplier_id=supplier_id,
                        type=EvidenceType.GOVERNMENT_REGISTRY,
                        source="vector_search",
                        title=f"Similar high-risk supplier: {match['metadata'].get('name', 'Unknown')}",
                        content=f"Found similar supplier with risk score {match['metadata'].get('risk_score', 0)}",
                        credibility_score=0.6,
                        relevance_score=match.get("score", 0)
                    )
                    evidence.append(ev)
        
        # 5. MCP - Internal CRM/ERP data
        mcp_results = await self._execute_tool("mcp_call", {
            "server_name": "crm",
            "tool_name": "query_database",
            "arguments": {"query": f"SELECT * FROM suppliers WHERE name = '{supplier_name}'"}
        })
        
        if mcp_results.success and mcp_results.data:
            ev = Evidence(
                supplier_id=supplier_id,
                type=EvidenceType.INTERNAL_DOCUMENT,
                source="mcp_crm",
                title="Internal supplier data",
                content=json.dumps(mcp_results.data),
                credibility_score=0.9,
                relevance_score=0.85
            )
            evidence.append(ev)
        
        return evidence


class AnalystAgent(BaseAgent):
    """Analyst Agent - Reasoning & Synthesis specialist"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(AgentRole.ANALYST, config)
        self.llm_config = config.get("llm", {}) if config else {}
    
    async def get_capabilities(self) -> List[str]:
        return [
            "risk_synthesis",
            "cross_reference_analysis",
            "probabilistic_modeling",
            "financial_analysis",
            "monte_carlo_simulation",
            "pattern_recognition",
            "trend_analysis"
        ]
    
    @traceable(run_type="chain", name="AnalystAgent.process")
    async def process(self, context: AgentContext) -> AgentResult:
        await self._initialize_services()
        await self._emit_message(context, "Analyst agent starting risk synthesis")
        
        if not self._increment_step(context):
            return AgentResult(success=False, context=context, error="Max steps exceeded")
        
        if not context.evidence:
            await self._emit_message(context, "No evidence to analyze, requesting more from Scout")
            return AgentResult(
                success=True,
                context=context,
                next_agent=AgentRole.SCOUT,
                messages=["No evidence available, requesting Scout to gather more data"]
            )
        
        # Analyze evidence with LLM
        risk_factors = await self._analyze_evidence(context)
        context.risk_factors.extend(risk_factors)
        
        await self._emit_message(context, f"Analyst identified {len(risk_factors)} risk factors")
        
        # Store risk assessments in vector store for historical tracking
        for rf in risk_factors:
            await self.memory_manager.store_risk_assessment(rf)
        
        # Check if we need more evidence
        if self._needs_more_evidence(risk_factors):
            return AgentResult(
                success=True,
                context=context,
                next_agent=AgentRole.SCOUT,
                messages=["Evidence insufficient for high-confidence assessment, requesting more data"]
            )
        
        return AgentResult(
            success=True,
            context=context,
            next_agent=AgentRole.AUDITOR,
            messages=[f"Identified {len(risk_factors)} risk factors with sufficient confidence"]
        )
    
    async def _analyze_evidence(self, context: AgentContext) -> List[RiskFactor]:
        """Analyze evidence and identify risk factors using LLM"""
        await self._initialize_services()
        
        # Prepare evidence summary for LLM
        evidence_summary = self._prepare_evidence_summary(context.evidence)
        supplier_name = context.supplier.name if context.supplier else "Unknown"
        
        # Build prompt
        prompt = f"""You are the Analyst agent in SentinelChain, a supply chain risk analysis system.

Your task: analyze the following evidence about supplier "{supplier_name}" and identify risk factors.

## Evidence
{evidence_summary}

## Instructions
1. Review each piece of evidence carefully.
2. Identify risk factors across these categories:
   - FINANCIAL (cash flow, debt, credit rating)
   - GEOPOLITICAL (trade wars, sanctions, port strikes, political instability)
   - REGULATORY (sanctions lists, export controls, new laws)
   - ESG (environmental violations, labor disputes, carbon footprint)
   - OPERATIONAL (factory fires, shipping delays, quality failures)
   - REPUTATIONAL (scandals, negative press, lawsuits)
3. Assign a RiskLevel to each: LOW, MEDIUM, HIGH, SEVERE, or CRITICAL
4. Assign a confidence score (0.0 to 1.0) based on evidence quality
5. For each risk factor, cite at least one evidence URL/document ID as the source
6. If evidence is insufficient to reach a confident assessment, say so explicitly and request more data from Scout.

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
      "evidence_ids": ["<evidence_id>"],
      "metadata": {{}}
    }}
  ],
  "needs_more_evidence": <bool>,
  "summary": "<1 paragraph summary>"
}}
"""
        
        # Check cache first
        cached = await self.memory_manager.get_cached_llm_call(prompt, self.llm_config.get("model", "claude-3-5-sonnet"), str(context.supplier_id) if context.supplier_id else "")
        if cached:
            return self._parse_risk_factors(cached, context)
        
        # Call LLM (using Anthropic via LangChain)
        try:
            from langchain_anthropic import ChatAnthropic
            from langchain_core.messages import HumanMessage
            
            llm = ChatAnthropic(
                model=self.llm_config.get("model", "claude-3-5-sonnet-20241022"),
                temperature=self.llm_config.get("temperature", 0.1),
                max_tokens=self.llm_config.get("max_tokens", 8192)
            )
            
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            raw_output = response.content
            
            # Validate with Guardrails
            validated = await self.guardrails.validate_risk_output(raw_output)
            
            # Cache successful result
            await self.memory_manager.cache_llm_call(prompt, validated, self.llm_config.get("model", "claude-3-5-sonnet"), str(context.supplier_id) if context.supplier_id else "")
            
            return self._parse_risk_factors(validated, context)
            
        except Exception as e:
            self.logger.error("LLM analysis failed", error=str(e))
            # Return fallback - request more evidence
            return []
    
    def _prepare_evidence_summary(self, evidence: List[Evidence]) -> str:
        """Prepare evidence for LLM prompt"""
        summary = []
        for i, ev in enumerate(evidence):
            summary.append(f"""
Evidence {i+1}:
- Type: {ev.type.value}
- Source: {ev.source}
- Title: {ev.title}
- Content: {ev.content[:1000]}
- URL: {ev.url or 'N/A'}
- Credibility: {ev.credibility_score}
- Relevance: {ev.relevance_score}
""")
        return "\n".join(summary)
    
    def _parse_risk_factors(self, validated: Dict[str, Any], context: AgentContext) -> List[RiskFactor]:
        """Parse validated output into RiskFactor objects"""
        risk_factors = []
        
        for rf_data in validated.get("risk_factors", []):
            try:
                rf = RiskFactor(
                    supplier_id=context.supplier_id or context.supplier.id,
                    category=RiskCategory(rf_data["category"]),
                    level=RiskLevel(rf_data["level"]),
                    title=rf_data["title"],
                    description=rf_data["description"],
                    evidence_ids=[UUID(eid) for eid in rf_data.get("evidence_ids", [])],
                    confidence=rf_data["confidence"],
                    impact_score=rf_data.get("impact_score", 50.0),
                    likelihood_score=rf_data.get("likelihood_score", 50.0),
                )
                risk_factors.append(rf)
            except Exception as e:
                self.logger.error("Failed to parse risk factor", error=str(e), data=rf_data)
        
        return risk_factors
    
    def _needs_more_evidence(self, risk_factors: List[RiskFactor]) -> bool:
        """Determine if more evidence is needed"""
        if not risk_factors:
            return True
        for rf in risk_factors:
            if rf.level in ["HIGH", "SEVERE", "CRITICAL"] and rf.confidence < 0.7:
                return True
        return False


class AuditorAgent(BaseAgent):
    """Auditor Agent - Compliance & Rules specialist"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(AgentRole.AUDITOR, config)
        self.compliance_rules = config.get("compliance_rules", {}) if config else {}
    
    async def get_capabilities(self) -> List[str]:
        return [
            "sanctions_screening",
            "regulatory_compliance_check",
            "esg_compliance_verification",
            "export_control_screening",
            "anti_money_laundering_check",
            "forced_labor_screening",
            "environmental_regulation_check"
        ]
    
    @traceable(run_type="chain", name="AuditorAgent.process")
    async def process(self, context: AgentContext) -> AgentResult:
        await self._initialize_services()
        await self._emit_message(context, "Auditor agent starting compliance verification")
        
        if not self._increment_step(context):
            return AgentResult(success=False, context=context, error="Max steps exceeded")
        
        # Verify compliance for each risk factor
        compliance_results = await self._verify_compliance(context)
        
        # Update risk factors with compliance findings
        for rf in context.risk_factors:
            if rf.category.value in compliance_results:
                rf.metadata["compliance_verified"] = compliance_results[rf.category.value]
        
        # Check if HITL is required
        hitl_required = self._check_hitl_required(context.risk_factors)
        context.hitl_required = hitl_required
        
        if hitl_required:
            context.hitl_payload = self._prepare_hitl_payload(context)
            await self._emit_message(context, "HITL required - severe compliance violation detected")
            return AgentResult(
                success=True,
                context=context,
                next_agent=None,
                should_continue=False,
                messages=["Compliance violation requires human approval"]
            )
        
        return AgentResult(
            success=True,
            context=context,
            next_agent=AgentRole.MITIGATOR,
            messages=["Compliance verification complete, no HITL required"]
        )
    
    async def _verify_compliance(self, context: AgentContext) -> Dict[str, bool]:
        """Verify compliance against regulatory frameworks"""
        results = {}
        
        for rf in context.risk_factors:
            category = rf.category.value
            
            if category == "REGULATORY":
                # Check sanctions lists via Apify
                sanctions_check = await self._execute_tool("apify_scraper", {
                    "actor_id": "apify/ofac-sdn-list",
                    "run_input": {"search_term": context.supplier.name if context.supplier else ""}
                })
                results[category] = sanctions_check.success and len(sanctions_check.data or []) == 0
                
                # Check export controls via MCP
                export_check = await self._execute_tool("mcp_call", {
                    "server_name": "compliance",
                    "tool_name": "check_export_controls",
                    "arguments": {"supplier_name": context.supplier.name if context.supplier else ""}
                })
                if export_check.success:
                    results[f"{category}_export"] = export_check.data.get("compliant", True)
            
            elif category == "ESG":
                # ESG compliance via MCP
                esg_check = await self._execute_tool("mcp_call", {
                    "server_name": "esg",
                    "tool_name": "check_esg_compliance",
                    "arguments": {"supplier_id": str(context.supplier_id) if context.supplier_id else ""}
                })
                results[category] = esg_check.success and esg_check.data.get("compliant", True)
            
            elif category == "FINANCIAL":
                # Financial health check via E2B
                financial_check = await self._execute_tool("e2b_code", {
                    "code": f"""
import json
# Mock financial health assessment
supplier_data = {{"revenue": 100000000, "debt": 50000000, "cash": 20000000}}
debt_to_equity = supplier_data["debt"] / max(supplier_data["revenue"] - supplier_data["debt"], 1)
current_ratio = supplier_data["cash"] / max(supplier_data["debt"] * 0.1, 1)
print(json.dumps({{"debt_to_equity": debt_to_equity, "current_ratio": current_ratio, "healthy": debt_to_equity < 2 and current_ratio > 1}}))
"""
                })
                results[category] = financial_check.success
            
            else:
                results[category] = True
        
        return results
    
    def _check_hitl_required(self, risk_factors: List[RiskFactor]) -> bool:
        """Check if human-in-the-loop approval is required"""
        for rf in risk_factors:
            if rf.level in ["SEVERE", "CRITICAL"]:
                return True
            if rf.category == RiskCategory.REGULATORY and rf.level == "HIGH":
                return True
        return False
    
    def _prepare_hitl_payload(self, context: AgentContext) -> Dict[str, Any]:
        """Prepare payload for HITL review"""
        return {
            "workflow_id": str(context.workflow_id),
            "supplier_name": context.supplier.name if context.supplier else "Unknown",
            "risk_factors": [
                {
                    "id": str(rf.id),
                    "category": rf.category.value,
                    "level": rf.level.value,
                    "title": rf.title,
                    "description": rf.description,
                    "confidence": rf.confidence,
                    "evidence_count": len(rf.evidence_ids)
                }
                for rf in context.risk_factors
            ],
            "recommendation": "FREEZE_PAYMENTS" if any(rf.level == "CRITICAL" for rf in context.risk_factors) else "INVESTIGATE_FURTHER"
        }


class MitigatorAgent(BaseAgent):
    """Mitigator Agent - Action & Remediation specialist"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(AgentRole.MITIGATOR, config)
        self.action_templates = config.get("action_templates", {}) if config else {}
    
    async def get_capabilities(self) -> List[str]:
        return [
            "alternative_sourcing",
            "financial_impact_calculation",
            "procurement_ticket_generation",
            "supplier_communication_drafting",
            "contingency_planning",
            "cost_optimization",
            "risk_mitigation_strategy"
        ]
    
    @traceable(run_type="chain", name="MitigatorAgent.process")
    async def process(self, context: AgentContext) -> AgentResult:
        await self._initialize_services()
        await self._emit_message(context, "Mitigator agent generating remediation actions")
        
        if not self._increment_step(context):
            return AgentResult(success=False, context=context, error="Max steps exceeded")
        
        # Generate mitigations for each risk factor
        mitigation_actions = await self._generate_mitigations(context)
        context.mitigation_actions.extend(mitigation_actions)
        
        # Find alternative suppliers
        alternative_suppliers = await self._find_alternatives(context)
        context.alternative_suppliers.extend(alternative_suppliers)
        
        await self._emit_message(context, f"Mitigator generated {len(mitigation_actions)} actions and found {len(alternative_suppliers)} alternatives")
        
        return AgentResult(
            success=True,
            context=context,
            next_agent=None,
            should_continue=False,
            messages=[f"Generated {len(mitigation_actions)} mitigation actions and {len(alternative_suppliers)} alternative suppliers"]
        )
    
    async def _generate_mitigations(self, context: AgentContext) -> List[MitigationAction]:
        """Generate mitigation actions for identified risks using LLM"""
        await self._initialize_services()
        
        if not context.risk_factors:
            return []
        
        # Prepare risk factors for LLM
        risk_summary = []
        for rf in context.risk_factors:
            risk_summary.append({
                "id": str(rf.id),
                "category": rf.category.value,
                "level": rf.level.value,
                "title": rf.title,
                "description": rf.description,
                "confidence": rf.confidence
            })
        
        supplier_name = context.supplier.name if context.supplier else "Unknown"
        
        prompt = f"""You are the Mitigator agent in SentinelChain. Given the following identified risk factors for supplier "{supplier_name}", generate mitigation actions and suggest alternative suppliers.

## Risk Factors
{json.dumps(risk_summary, indent=2)}

## Instructions
1. For each HIGH, SEVERE, and CRITICAL risk factor, generate 1-3 specific mitigation actions.
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
      "priority": <1-5>,
      "status": "PROPOSED"
    }}
  ],
  "alternative_suppliers": [
    {{
      "id": "as-<uuid>",
      "original_supplier_id": "<supplier_id>",
      "name": "<supplier name>",
      "country": "<country>",
      "risk_score": <0-100>,
      "cost_difference_pct": <number|null>,
      "lead_time_days": <number|null>,
      "quality_rating": <number|null>,
      "certifications": []
    }}
  ],
  "summary": "<1 paragraph summary>"
}}
"""
        
        try:
            from langchain_anthropic import ChatAnthropic
            from langchain_core.messages import HumanMessage
            
            llm = ChatAnthropic(
                model=self.llm_config.get("model", "claude-3-5-sonnet-20241022"),
                temperature=0.1,
                max_tokens=8192
            )
            
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            validated = await self.guardrails.validate_mitigation_output(response.content)
            
            # Parse into objects
            actions = []
            for ma_data in validated.get("mitigation_actions", []):
                try:
                    actions.append(MitigationAction(
                        risk_factor_id=UUID(ma_data["risk_factor_id"]),
                        title=ma_data["title"],
                        description=ma_data["description"],
                        action_type=ma_data["action_type"],
                        estimated_cost=ma_data.get("estimated_cost_usd"),
                        estimated_timeline_days=ma_data.get("estimated_timeline_days"),
                        priority=ma_data.get("priority", 3)
                    ))
                except Exception as e:
                    self.logger.error("Failed to parse mitigation action", error=str(e))
            
            alternatives = []
            for alt_data in validated.get("alternative_suppliers", []):
                try:
                    alternatives.append(AlternativeSupplier(
                        original_supplier_id=context.supplier_id or UUID(alt_data["original_supplier_id"]),
                        name=alt_data["name"],
                        country=alt_data["country"],
                        risk_score=alt_data["risk_score"],
                        cost_difference_pct=alt_data.get("cost_difference_pct"),
                        lead_time_days=alt_data.get("lead_time_days"),
                        quality_rating=alt_data.get("quality_rating"),
                        certifications=alt_data.get("certifications", [])
                    ))
                except Exception as e:
                    self.logger.error("Failed to parse alternative supplier", error=str(e))
            
            # Store in vector store for future reference
            for alt in alternatives:
                text = f"{alt.name} {alt.country} {alt.risk_score}"
                embedding = await self.embeddings.embed(text)
                await self.memory_manager.vector_store.upsert_evidence(alt.id, embedding, alt.metadata)
            
            return actions
            
        except Exception as e:
            self.logger.error("LLM mitigation generation failed", error=str(e))
            return []
    
    async def _find_alternatives(self, context: AgentContext) -> List[AlternativeSupplier]:
        """Find alternative suppliers using vector search"""
        if not context.supplier:
            return []
        
        try:
            # Search vector store for similar suppliers with lower risk
            supplier_text = f"{context.supplier.name} {context.supplier.country} {context.supplier.industry}"
            embedding = await self.embeddings.embed(supplier_text)
            
            results = await self.memory_manager.vector_store.search_similar_suppliers(
                embedding, top_k=10, filter_dict={"risk_score": {"$lt": 40}}
            )
            
            alternatives = []
            for match in results[:3]:
                meta = match.get("metadata", {})
                alt = AlternativeSupplier(
                    original_supplier_id=context.supplier.id,
                    name=meta.get("name", "Unknown"),
                    country=meta.get("country", "Unknown"),
                    risk_score=meta.get("risk_score", 0),
                    cost_difference_pct=None,  # Would need ERP data
                    lead_time_days=None,
                    quality_rating=meta.get("quality_rating"),
                    certifications=meta.get("certifications", [])
                )
                alternatives.append(alt)
            
            return alternatives
            
        except Exception as e:
            self.logger.error("Alternative supplier search failed", error=str(e))
            return []


class OrchestratorAgent(BaseAgent):
    """Orchestrator Agent - Workflow coordination"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(AgentRole.ORCHESTRATOR, config)
        self.agents = {}
    
    def register_agent(self, agent: BaseAgent):
        self.agents[agent.role] = agent
    
    async def get_capabilities(self) -> List[str]:
        return [
            "workflow_coordination",
            "agent_routing",
            "state_management",
            "hitl_coordination",
            "error_recovery",
            "cost_tracking"
        ]
    
    async def process(self, context: AgentContext) -> AgentResult:
        return AgentResult(success=True, context=context, messages=["Orchestrator coordinating workflow"])

    async def run_deep_dive_crew(self, supplier_id=None, supplier_name=None, query=""):
        """Delegate a deep-dive investigation to the CrewAI engine."""
        import uuid as _uuid

        from app.crews import DeepDiveCrew

        crew = DeepDiveCrew(
            workflow_id=_uuid.uuid4(),
            supplier_name=supplier_name,
            query=query,
        )
        return await crew.run()

    async def run_workflow(self, context: AgentContext) -> AgentContext:
        """Run the complete agent workflow"""
        current_agent_role = AgentRole.SCOUT
        
        while context.step_count < context.max_steps:
            if current_agent_role not in self.agents:
                context.error = f"Agent {current_agent_role} not registered"
                break
            
            agent = self.agents[current_agent_role]
            result = await agent.process(context)
            context = result.context
            
            if not result.should_continue:
                break
            
            if result.next_agent:
                current_agent_role = result.next_agent
            else:
                break
        
        return context


from app.models import AgentMessage