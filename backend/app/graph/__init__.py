"""
LangGraph workflow for SentinelChain multi-agent orchestration
"""
from typing import Dict, Any, List, Optional, Literal, Annotated
from uuid import UUID, uuid4
from datetime import datetime
import operator
import structlog

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from app.models import (
    WorkflowState, WorkflowType, AgentRole, RiskLevel, RiskCategory,
    Supplier, Evidence, RiskFactor, MitigationAction, AlternativeSupplier,
    HITLStatus
)
from app.agents import (
    ScoutAgent, AnalystAgent, AuditorAgent, MitigatorAgent, OrchestratorAgent,
    AgentContext, AgentResult
)
from app.tools import ToolRegistry
from app.memory import MemoryManager
from app.config import get_config

logger = structlog.get_logger(__name__)


# Extended state for LangGraph
class GraphState(WorkflowState):
    """Extended state for LangGraph with additional fields"""
    agent_context: Optional[AgentContext] = None
    current_agent: Optional[str] = None
    messages: Annotated[List[Dict[str, Any]], operator.add] = []
    hitl_response: Optional[Dict[str, Any]] = None
    config: Dict[str, Any] = {}


def create_initial_state(workflow_type: WorkflowType, supplier_id: UUID = None, query: str = None, config: Dict = None) -> GraphState:
    """Create initial graph state"""
    return GraphState(
        workflow_id=uuid4(),
        workflow_type=workflow_type,
        supplier_id=supplier_id,
        status="RUNNING",
        state_data={},
        evidence_collected=[],
        risk_factors_identified=[],
        mitigation_actions=[],
        hitl_required=False,
        step_count=0,
        max_steps=10,
        config=config or {},
        messages=[],
        current_agent=None
    )


# Node Functions
async def scout_node(state: GraphState) -> GraphState:
    """Scout agent node - Data acquisition"""
    logger.info("Executing Scout node", workflow_id=str(state.workflow_id))
    
    # Initialize agent context if not exists
    if not state.agent_context:
        state.agent_context = AgentContext(
            workflow_id=state.workflow_id,
            supplier_id=state.supplier_id,
            query=state.state_data.get("query"),
            max_steps=state.max_steps
        )
    
    # Load supplier if available
    if state.supplier_id and not state.agent_context.supplier:
        # In production: load from database
        pass
    
    # Create Scout agent with tools
    config = get_config()
    tool_registry = ToolRegistry(config.tools)
    
    scout = ScoutAgent(config={
        "tools": tool_registry.tools,
        "llm": config.llm.primary.model_dump() if hasattr(config.llm.primary, 'model_dump') else {}
    })
    
    # Process
    result = await scout.process(state.agent_context)
    state.agent_context = result.context
    
    # Update state
    state.evidence_collected = state.agent_context.evidence
    state.current_agent = AgentRole.SCOUT.value
    state.step_count = state.agent_context.step_count
    state.state_data = state.agent_context.state_data
    
    # Add message
    state.messages.append({
        "agent": AgentRole.SCOUT.value,
        "content": f"Scout gathered {len(result.context.evidence)} pieces of evidence",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Determine next agent
    if result.next_agent:
        state.current_agent = result.next_agent.value
    
    return state


async def analyst_node(state: GraphState) -> GraphState:
    """Analyst agent node - Reasoning & synthesis"""
    logger.info("Executing Analyst node", workflow_id=str(state.workflow_id))
    
    config = get_config()
    tool_registry = ToolRegistry(config.tools)
    
    analyst = AnalystAgent(config={
        "tools": tool_registry.tools,
        "llm": config.llm.primary.model_dump() if hasattr(config.llm.primary, 'model_dump') else {}
    })
    
    result = await analyst.process(state.agent_context)
    state.agent_context = result.context
    
    # Update state
    state.risk_factors_identified = state.agent_context.risk_factors
    state.current_agent = AgentRole.ANALYST.value
    state.step_count = state.agent_context.step_count
    state.state_data = state.agent_context.state_data
    
    state.messages.append({
        "agent": AgentRole.ANALYST.value,
        "content": f"Analyst identified {len(result.context.risk_factors)} risk factors",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    if result.next_agent:
        state.current_agent = result.next_agent.value
    
    return state


async def auditor_node(state: GraphState) -> GraphState:
    """Auditor agent node - Compliance verification"""
    logger.info("Executing Auditor node", workflow_id=str(state.workflow_id))
    
    config = get_config()
    
    auditor = AuditorAgent(config={
        "compliance_rules": config.config.get("compliance_rules", {}),
        "llm": config.llm.secure.model_dump() if hasattr(config.llm.secure, 'model_dump') else {}
    })
    
    result = await auditor.process(state.agent_context)
    state.agent_context = result.context
    
    # Update state
    state.hitl_required = state.agent_context.hitl_required
    state.hitl_payload = state.agent_context.hitl_payload
    state.current_agent = AgentRole.AUDITOR.value
    state.step_count = state.agent_context.step_count
    state.state_data = state.agent_context.state_data
    
    state.messages.append({
        "agent": AgentRole.AUDITOR.value,
        "content": f"Auditor completed compliance check. HITL required: {state.hitl_required}",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    if result.next_agent:
        state.current_agent = result.next_agent.value
    elif state.hitl_required:
        # Pause for HITL
        state.status = "WAITING_HITL"
    
    return_interrupt(state)


async def mitigator_node(state: GraphState) -> GraphState:
    """Mitigator agent node - Action & remediation"""
    logger.info("Executing Mitigator node", workflow_id=str(state.workflow_id))
    
    config = get_config()
    tool_registry = ToolRegistry(config.tools)
    
    mitigator = MitigatorAgent(config={
        "tools": tool_registry.tools,
        "action_templates": config.config.get("action_templates", {}),
        "llm": config.llm.primary.model_dump() if hasattr(config.llm.primary, 'model_dump') else {}
    })
    
    result = await mitigator.process(state.agent_context)
    state.agent_context = result.context
    
    # Update state
    state.mitigation_actions = state.agent_context.mitigation_actions
    state.state_data["alternative_suppliers"] = [s.model_dump() for s in state.agent_context.alternative_suppliers]
    state.current_agent = AgentRole.MITIGATOR.value
    state.step_count = state.agent_context.step_count
    state.state_data = state.agent_context.state_data
    state.status = "COMPLETED"
    state.completed_at = datetime.utcnow()
    
    state.messages.append({
        "agent": AgentRole.MITIGATOR.value,
        "content": f"Mitigator generated {len(result.context.mitigation_actions)} actions and {len(result.context.alternative_suppliers)} alternatives",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return state


# HITL Interrupt Handler
def return_interrupt(state: GraphState) -> Command:
    """Return interrupt for HITL"""
    return Command(
        interrupt={
            "workflow_id": str(state.workflow_id),
            "hitl_payload": state.hitl_payload,
            "message": "Human approval required for compliance action"
        }
    )


async def hitl_resume_node(state: GraphState) -> GraphState:
    """Resume after HITL response"""
    logger.info("Resuming after HITL", workflow_id=str(state.workflow_id))
    
    hitl_response = state.hitl_response
    if not hitl_response:
        state.error = "No HITL response received"
        state.status = "FAILED"
        return state
    
    action = hitl_response.get("action")
    if action == "APPROVE":
        state.hitl_status = HITLStatus.APPROVED
        state.messages.append({
            "agent": "HITL",
            "content": "Human approved - proceeding with mitigation",
            "timestamp": datetime.utcnow().isoformat()
        })
        # Continue to mitigator
        state.current_agent = AgentRole.MITIGATOR.value
        state.status = "RUNNING"
    elif action == "DENY":
        state.hitl_status = HITLStatus.DENIED
        state.status = "CANCELLED"
        state.messages.append({
            "agent": "HITL",
            "content": "Human denied - workflow cancelled",
            "timestamp": datetime.utcnow().isoformat()
        })
    elif action == "ESCALATE":
        state.hitl_status = HITLStatus.ESCALATED
        state.status = "ESCALATED"
        state.messages.append({
            "agent": "HITL",
            "content": "Escalated to senior compliance officer",
            "timestamp": datetime.utcnow().isoformat()
        })
    
    return state


# Routing Functions
def route_after_scout(state: GraphState) -> Literal["analyst", "scout", "end"]:
    """Route after Scout agent"""
    if state.agent_context and state.agent_context.step_count >= state.max_steps:
        return "end"
    if state.current_agent == AgentRole.ANALYST.value:
        return "analyst"
    if state.current_agent == AgentRole.SCOUT.value:
        return "scout"
    return "end"


def route_after_analyst(state: GraphState) -> Literal["auditor", "scout", "end"]:
    """Route after Analyst agent"""
    if state.agent_context and state.agent_context.step_count >= state.max_steps:
        return "end"
    if state.current_agent == AgentRole.AUDITOR.value:
        return "auditor"
    if state.current_agent == AgentRole.SCOUT.value:
        return "scout"
    return "end"


def route_after_auditor(state: GraphState) -> Literal["mitigator", "hitl_resume", "end"]:
    """Route after Auditor agent"""
    if state.agent_context and state.agent_context.step_count >= state.max_steps:
        return "end"
    if state.hitl_required:
        return "hitl_resume"
    if state.current_agent == AgentRole.MITIGATOR.value:
        return "mitigator"
    return "end"


def route_after_mitigator(state: GraphState) -> Literal["end"]:
    """Route after Mitigator agent"""
    return "end"


def route_after_hitl(state: GraphState) -> Literal["mitigator", "end"]:
    """Route after HITL response"""
    if state.hitl_status == HITLStatus.APPROVED:
        return "mitigator"
    return "end"


# Build the Graph
def create_sentinel_graph() -> StateGraph:
    """Create the SentinelChain LangGraph workflow"""
    
    # Create graph with state
    graph = StateGraph(GraphState)
    
    # Add nodes
    graph.add_node("scout", scout_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("auditor", auditor_node)
    graph.add_node("mitigator", mitigator_node)
    graph.add_node("hitl_resume", hitl_resume_node)
    
    # Add edges
    graph.add_edge(START, "scout")
    
    # Conditional edges
    graph.add_conditional_edges(
        "scout",
        route_after_scout,
        {
            "analyst": "analyst",
            "scout": "scout",
            "end": END
        }
    )
    
    graph.add_conditional_edges(
        "analyst",
        route_after_analyst,
        {
            "auditor": "auditor",
            "scout": "scout",
            "end": END
        }
    )
    
    graph.add_conditional_edges(
        "auditor",
        route_after_auditor,
        {
            "mitigator": "mitigator",
            "hitl_resume": "hitl_resume",
            "end": END
        }
    )
    
    graph.add_conditional_edges(
        "mitigator",
        route_after_mitigator,
        {
            "end": END
        }
    )
    
    graph.add_conditional_edges(
        "hitl_resume",
        route_after_hitl,
        {
            "mitigator": "mitigator",
            "end": END
        }
    )
    
    # Compile with checkpointer
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# High-level workflow runner
class SentinelWorkflowRunner:
    """High-level interface for running SentinelChain workflows"""
    
    def __init__(self):
        self.graph = create_sentinel_graph()
        self.memory = MemoryManager()
        self.logger = logger.bind(component="workflow_runner")
    
    async def initialize(self):
        await self.memory.initialize()
    
    async def close(self):
        await self.memory.close()
    
    async def run_autonomous_discovery(self, supplier_id: UUID) -> GraphState:
        """Run autonomous risk discovery workflow (Workflow 1)"""
        initial_state = create_initial_state(
            workflow_type=WorkflowType.AUTONOMOUS_DISCOVERY,
            supplier_id=supplier_id
        )
        
        config = {"thread_id": str(initial_state.workflow_id)}
        result = await self.graph.ainvoke(initial_state, config=config)
        
        # Save final state
        if isinstance(result, GraphState):
            await self.memory.save_workflow_state(result)
        
        return result
    
    async def run_deep_dive_investigation(self, supplier_id: UUID = None, supplier_name: str = None, query: str = "") -> GraphState:
        """Run deep-dive investigation workflow (Workflow 2)"""
        initial_state = create_initial_state(
            workflow_type=WorkflowType.DEEP_DIVE_INVESTIGATION,
            supplier_id=supplier_id,
            query=query
        )
        initial_state.state_data["supplier_name"] = supplier_name
        
        config = {"thread_id": str(initial_state.workflow_id)}
        result = await self.graph.ainvoke(initial_state, config=config)
        
        if isinstance(result, GraphState):
            await self.memory.save_workflow_state(result)
        
        return result
    
    async def resume_after_hitl(self, workflow_id: UUID, hitl_response: Dict[str, Any]) -> GraphState:
        """Resume workflow after HITL response"""
        config = {"thread_id": str(workflow_id)}
        
        # Get current state
        current_state = await self.memory.get_workflow_state(workflow_id)
        if not current_state:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        # Add HITL response to state
        current_state.hitl_response = hitl_response
        
        # Resume graph
        result = await self.graph.ainvoke(current_state, config=config)
        
        if isinstance(result, GraphState):
            await self.memory.save_workflow_state(result)
        
        return result
    
    async def get_workflow_status(self, workflow_id: UUID) -> Optional[GraphState]:
        """Get current workflow status"""
        return await self.memory.get_workflow_state(workflow_id)