"""
Core agent interfaces and base classes for SentinelChain
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, AsyncGenerator
from pydantic import BaseModel, Field
from uuid import UUID
import structlog

from app.models import (
    AgentRole, WorkflowState, Evidence, RiskFactor, 
    MitigationAction, AlternativeSupplier, Supplier
)

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
    
    def _increment_step(self, context: AgentContext) -> bool:
        """Increment step counter and check if we should continue"""
        context.step_count += 1
        if context.step_count >= context.max_steps:
            self.logger.warning("Max steps reached", workflow_id=str(context.workflow_id), step_count=context.step_count)
            context.error = "Max steps exceeded"
            return False
        return True


class ScoutAgent(BaseAgent):
    """Scout Agent - Data Acquisition specialist"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(AgentRole.SCOUT, config)
        self.tools = config.get("tools", {}) if config else {}
    
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
    
    async def process(self, context: AgentContext) -> AgentResult:
        await self._emit_message(context, "Scout agent starting data acquisition")
        
        if not self._increment_step(context):
            return AgentResult(success=False, context=context, error="Max steps exceeded")
        
        # In a real implementation, this would call actual tools
        # For now, we'll simulate the behavior
        evidence = await self._gather_evidence(context)
        
        context.evidence.extend(evidence)
        await self._emit_message(context, f"Scout gathered {len(evidence)} pieces of evidence")
        
        return AgentResult(
            success=True,
            context=context,
            next_agent=AgentRole.ANALYST,
            messages=[f"Found {len(evidence)} relevant data points"]
        )
    
    async def _gather_evidence(self, context: AgentContext) -> List[Evidence]:
        """Gather evidence from various sources"""
        evidence = []
        
        # Simulate tool calls
        if context.supplier_id:
            # In production, this would call:
            # - Tavily for news search
            # - Apify for sanctions lists
            # - Exa for semantic search
            # - E2B for satellite imagery analysis
            pass
        
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
    
    async def process(self, context: AgentContext) -> AgentResult:
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
        
        risk_factors = await self._analyze_evidence(context)
        context.risk_factors.extend(risk_factors)
        
        await self._emit_message(context, f"Analyst identified {len(risk_factors)} risk factors")
        
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
        """Analyze evidence and identify risk factors"""
        risk_factors = []
        
        # In production, this would use LLM to:
        # - Cross-reference evidence
        # - Calculate risk scores
        # - Identify patterns
        # - Run Monte Carlo simulations via E2B
        
        return risk_factors
    
    def _needs_more_evidence(self, risk_factors: List[RiskFactor]) -> bool:
        """Determine if more evidence is needed"""
        if not risk_factors:
            return True
        # Check if any high-severity risks have low confidence
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
    
    async def process(self, context: AgentContext) -> AgentResult:
        await self._emit_message(context, "Auditor agent starting compliance verification")
        
        if not self._increment_step(context):
            return AgentResult(success=False, context=context, error="Max steps exceeded")
        
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
                next_agent=None,  # Wait for HITL
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
        
        # In production, this would check:
        # - OFAC sanctions lists
        # - EU CSDDD requirements
        # - ESG frameworks
        # - Export controls
        # - Anti-corruption laws
        
        return results
    
    def _check_hitl_required(self, risk_factors: List[RiskFactor]) -> bool:
        """Check if human-in-the-loop approval is required"""
        for rf in risk_factors:
            if rf.level in ["SEVERE", "CRITICAL"]:
                return True
            if rf.category in ["REGULATORY"] and rf.level == "HIGH":
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
    
    async def process(self, context: AgentContext) -> AgentResult:
        await self._emit_message(context, "Mitigator agent generating remediation actions")
        
        if not self._increment_step(context):
            return AgentResult(success=False, context=context, error="Max steps exceeded")
        
        mitigation_actions = await self._generate_mitigations(context)
        context.mitigation_actions.extend(mitigation_actions)
        
        alternative_suppliers = await self._find_alternatives(context)
        context.alternative_suppliers.extend(alternative_suppliers)
        
        await self._emit_message(context, f"Mitigator generated {len(mitigation_actions)} actions and found {len(alternative_suppliers)} alternatives")
        
        return AgentResult(
            success=True,
            context=context,
            next_agent=None,  # End of workflow
            should_continue=False,
            messages=[f"Generated {len(mitigation_actions)} mitigation actions and {len(alternative_suppliers)} alternative suppliers"]
        )
    
    async def _generate_mitigations(self, context: AgentContext) -> List[MitigationAction]:
        """Generate mitigation actions for identified risks"""
        actions = []
        
        for rf in context.risk_factors:
            # In production, this would use LLM to:
            # - Generate specific, actionable mitigations
            # - Calculate financial impact
            # - Draft procurement tickets
            # - Create supplier communication templates
            pass
        
        return actions
    
    async def _find_alternatives(self, context: AgentContext) -> List[AlternativeSupplier]:
        """Find alternative suppliers"""
        alternatives = []
        
        # In production, this would:
        # - Query supplier database
        # - Run risk assessments on alternatives
        # - Calculate cost/lead time differences
        # - Check certifications
        
        return alternatives


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
        # Orchestrator doesn't process directly, it coordinates
        return AgentResult(success=True, context=context, messages=["Orchestrator coordinating workflow"])
    
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