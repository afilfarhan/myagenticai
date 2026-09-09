"""
LangGraph workflow for SentinelChain multi-agent orchestration
"""
from typing import Dict, Any, List, Optional, Literal, Annotated
from uuid import UUID, uuid4
from datetime import datetime
import asyncio
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
from app.memory import MemoryManager, get_memory_manager
from app.config import get_config

logger = structlog.get_logger(__name__)


async def publish_workflow_step(state: "GraphState", message: str) -> None:
    """Publish a real-time workflow event to the SSE channel (best effort)."""
    try:
        memory_manager = await get_memory_manager()
        await memory_manager.publish_workflow_event(state.workflow_id, {
            "workflow_id": str(state.workflow_id),
            "agent": state.current_agent,
            "message": message,
            "status": state.status,
            "step": state.step_count,
            "hitl_required": state.hitl_required,
            "hitl_payload": state.hitl_payload,
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as exc:
        logger.warning(
            "Failed to publish workflow event",
            workflow_id=str(state.workflow_id),
            error=str(exc),
        )


# Extended state for LangGraph
class GraphState(WorkflowState):
    """Extended state for LangGraph with additional fields"""
    agent_context: Optional[AgentContext] = None
    current_agent: Optional[str] = None
    messages: Annotated[List[Dict[str, Any]], operator.add] = []
    hitl_response: Optional[Dict[str, Any]] = None
    config: Dict[str, Any] = {}


def create_initial_state(
    workflow_type: WorkflowType,
    supplier_id: UUID = None,
    query: str = None,
    config: Dict = None,
    workflow_id: UUID = None,
) -> GraphState:
    """Create initial graph state"""
    return GraphState(
        workflow_id=workflow_id or uuid4(),
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
    tool_registry = ToolRegistry(config.tools.model_dump() if hasattr(config.tools, 'model_dump') else config.tools)
    
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
    await publish_workflow_step(
        state, f"Scout gathered {len(state.agent_context.evidence)} pieces of evidence"
    )

    # Determine next agent
    if result.next_agent:
        state.current_agent = result.next_agent.value
    
    return state


async def analyst_node(state: GraphState) -> GraphState:
    """Analyst agent node - Reasoning & synthesis"""
    logger.info("Executing Analyst node", workflow_id=str(state.workflow_id))
    
    config = get_config()
    tools_config = config.tools.model_dump() if hasattr(config.tools, 'model_dump') else config.tools
    tool_registry = ToolRegistry(tools_config)
    
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
    await publish_workflow_step(
        state, f"Analyst identified {len(state.risk_factors_identified)} risk factors"
    )

    if result.next_agent:
        state.current_agent = result.next_agent.value
    
    return state


async def auditor_node(state: GraphState) -> GraphState:
    """Auditor agent node - Compliance verification"""
    logger.info("Executing Auditor node", workflow_id=str(state.workflow_id))
    
    config = get_config()
    
    auditor = AuditorAgent(config={
        "compliance_rules": {},
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
    await publish_workflow_step(
        state, f"Auditor completed compliance check. HITL required: {state.hitl_required}"
    )

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
    tools_config = config.tools.model_dump() if hasattr(config.tools, 'model_dump') else config.tools
    tool_registry = ToolRegistry(tools_config)
    
    mitigator = MitigatorAgent(config={
        "tools": tool_registry.tools,
        "action_templates": {},
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
    await publish_workflow_step(
        state, f"Mitigator generated {len(state.mitigation_actions)} mitigation actions"
    )

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

    await publish_workflow_step(state, f"HITL response received: {action}")

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
    
    async def _run_graph(self, initial_state: GraphState) -> GraphState:
        """Execute the graph and persist/publish the terminal event."""
        config = {"thread_id": str(initial_state.workflow_id)}
        result = await self.graph.ainvoke(initial_state, config=config)

        if isinstance(result, GraphState):
            await self.memory.save_workflow_state(result)
            await self._persist_langgraph_findings(result)
            await self._publish_terminal_event(result)

        return result

    async def _persist_langgraph_findings(self, state: GraphState) -> None:
        """Persist structured findings (evidence, risks, mitigations,
        alternatives) produced by the LangGraph pipeline.

        Mirrors ``_persist_crew_risk_factors`` so both engines feed the same
        database-backed surfaces (alerts feed, supplier detail, metrics).
        """
        try:
            investigation = await self.memory.db.get_investigation(state.workflow_id)
            if not (investigation and state.supplier_id):
                return

            context = state.agent_context
            evidence_items = list(getattr(context, "evidence", []) or []) if context else []
            risk_factors = [
                rf for rf in (state.risk_factors_identified or [])
                if isinstance(rf, RiskFactor)
            ]
            mitigation_actions = list(getattr(context, "mitigation_actions", []) or []) if context else []
            alternative_suppliers = list(getattr(context, "alternative_suppliers", []) or []) if context else []

            # --- Evidence ---
            evidence_id_map: Dict[str, Any] = {}
            for ev in evidence_items[:50]:
                try:
                    row = await self.memory.db.add_evidence(
                        supplier_id=state.supplier_id,
                        investigation_id=investigation.id,
                        type=ev.type.value,
                        source=str(ev.source)[:500],
                        title=str(ev.title)[:500],
                        content=ev.content,
                        url=ev.url,
                        credibility_score=ev.credibility_score,
                        relevance_score=ev.relevance_score,
                        evidence_metadata=ev.metadata or {},
                    )
                    evidence_id_map[str(ev.id)] = row.id
                except Exception as exc:
                    self.logger.warning("Failed to persist evidence item",
                                        workflow_id=str(state.workflow_id), error=str(exc))

            # --- Risk factors ---
            factor_row_ids: Dict[str, Any] = {}
            for rf in risk_factors[:20]:
                try:
                    row = await self.memory.db.add_risk_factor(
                        supplier_id=state.supplier_id,
                        investigation_id=investigation.id,
                        category=rf.category.value,
                        level=rf.level.value,
                        title=str(rf.title)[:255],
                        description=rf.description,
                        evidence_ids=[
                            str(evidence_id_map.get(str(eid), eid))
                            for eid in (rf.evidence_ids or [])
                        ],
                        confidence=rf.confidence,
                        impact_score=rf.impact_score,
                        likelihood_score=rf.likelihood_score,
                        risk_metadata={**(rf.metadata or {}), "engine": "langgraph"},
                    )
                    factor_row_ids[str(rf.id)] = row.id
                except Exception as exc:
                    self.logger.warning("Failed to persist risk factor",
                                        workflow_id=str(state.workflow_id), error=str(exc))

            # --- Mitigation actions (require an existing risk_factor FK) ---
            default_factor_id = next(iter(factor_row_ids.values()), None)
            for ma in mitigation_actions[:20]:
                target_factor = factor_row_ids.get(str(getattr(ma, "risk_factor_id", "")), default_factor_id)
                if not target_factor:
                    break
                try:
                    await self.memory.db.add_mitigation_action(
                        risk_factor_id=target_factor,
                        investigation_id=investigation.id,
                        title=str(ma.title)[:255],
                        description=ma.description,
                        action_type=str(ma.action_type),
                        estimated_cost=ma.estimated_cost,
                        estimated_timeline_days=ma.estimated_timeline_days,
                        priority=ma.priority,
                        status="PROPOSED",
                        action_metadata=ma.metadata or {},
                    )
                except Exception as exc:
                    self.logger.warning("Failed to persist mitigation action",
                                        workflow_id=str(state.workflow_id), error=str(exc))

            # --- Alternative suppliers ---
            for alt in alternative_suppliers[:10]:
                try:
                    await self.memory.db.add_alternative_supplier(
                        original_supplier_id=state.supplier_id,
                        investigation_id=investigation.id,
                        name=str(alt.name)[:255],
                        country=str(alt.country)[:100],
                        risk_score=alt.risk_score,
                        cost_difference_pct=alt.cost_difference_pct,
                        lead_time_days=alt.lead_time_days,
                        quality_rating=alt.quality_rating,
                        certifications=alt.certifications or [],
                        alt_metadata=alt.metadata or {},
                    )
                except Exception as exc:
                    self.logger.warning("Failed to persist alternative supplier",
                                        workflow_id=str(state.workflow_id), error=str(exc))

            persisted = len(evidence_id_map) + len(factor_row_ids)
            if persisted:
                self.logger.info("LangGraph findings persisted",
                                 workflow_id=str(state.workflow_id),
                                 evidence=len(evidence_id_map),
                                 risk_factors=len(factor_row_ids))

            # Keep the supplier's roll-up score in sync with new findings
            if state.supplier_id and (factor_row_ids or evidence_id_map):
                try:
                    new_score = await self.memory.db.recalculate_supplier_risk(state.supplier_id)
                    self.logger.info("Supplier risk score recalculated",
                                     workflow_id=str(state.workflow_id),
                                     supplier_id=str(state.supplier_id),
                                     risk_score=new_score)
                except Exception as exc:
                    self.logger.warning("Risk score recalculation failed",
                                        workflow_id=str(state.workflow_id), error=str(exc))
        except Exception as exc:
            self.logger.warning("Failed to persist LangGraph findings",
                                workflow_id=str(state.workflow_id), error=str(exc))

    async def _publish_terminal_event(self, state: GraphState) -> None:
        """Publish the terminal workflow event so SSE clients stop listening."""
        try:
            await self.memory.publish_workflow_event(state.workflow_id, {
                "workflow_id": str(state.workflow_id),
                "agent": state.current_agent,
                "message": f"Workflow finished with status {state.status}",
                "status": state.status,
                "step": state.step_count,
                "hitl_required": state.hitl_required,
                "hitl_payload": state.hitl_payload,
                "summary": state.state_data.get("summary"),
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception as exc:
            self.logger.warning(
                "Failed to publish terminal workflow event",
                workflow_id=str(state.workflow_id),
                error=str(exc),
            )

        # Human-in-the-loop follow-ups
        if state.status == "WAITING_HITL":
            self._notify_hitl_required(state)
            self._schedule_hitl_timeout(str(state.workflow_id))
        elif state.status == "ESCALATED":
            from app.services.notifications import send_slack_message
            import asyncio as _asyncio

            _asyncio.get_running_loop().create_task(
                send_slack_message(
                    f":rotating_light: SentinelChain workflow `{state.workflow_id}` "
                    f"was ESCALATED and needs senior compliance review."
                )
            )

    def _notify_hitl_required(self, state: GraphState) -> None:
        """Best-effort Slack ping that human approval is needed."""
        import asyncio as _asyncio

        from app.services.notifications import send_slack_message

        supplier = state.state_data.get("supplier_name") or str(state.supplier_id or "unknown")
        _asyncio.get_running_loop().create_task(
            send_slack_message(
                f":warning: SentinelChain HITL approval required for workflow "
                f"`{state.workflow_id}` (supplier: {supplier}). "
                f"It will auto-escalate if unanswered."
            )
        )

    def _schedule_hitl_timeout(self, workflow_id: str, timeout_seconds: int = None) -> None:
        """Start the escalation countdown for a WAITING_HITL workflow."""
        import asyncio as _asyncio

        from app.services.notifications import hitl_timeout_seconds

        if not hasattr(self, "_hitl_tasks"):
            self._hitl_tasks = {}
        self._cancel_hitl_timeout(workflow_id)
        seconds = timeout_seconds if timeout_seconds is not None else hitl_timeout_seconds()
        self._hitl_tasks[workflow_id] = _asyncio.get_running_loop().create_task(
            self._hitl_timeout_worker(workflow_id, seconds)
        )

    def _cancel_hitl_timeout(self, workflow_id: str) -> None:
        tasks = getattr(self, "_hitl_tasks", None)
        if tasks and workflow_id in tasks:
            task = tasks.pop(workflow_id)
            if not task.done():
                task.cancel()

    async def _hitl_timeout_worker(self, workflow_id: str, timeout_seconds: int) -> None:
        """Escalate a still-waiting workflow once the approval window lapses."""
        try:
            await asyncio.sleep(timeout_seconds)
        except asyncio.CancelledError:
            return

        try:
            state = await self.memory.get_workflow_state(UUID(workflow_id))
        except Exception as exc:
            self.logger.warning("HITL escalation check failed",
                                workflow_id=workflow_id, error=str(exc))
            return

        if not state or state.status != "WAITING_HITL":
            return  # already resolved

        self.logger.warning("HITL approval window lapsed - escalating",
                            workflow_id=workflow_id)
        state.hitl_status = HITLStatus.ESCALATED
        state.status = "ESCALATED"
        state.updated_at = datetime.utcnow()
        await self.memory.save_workflow_state(state)
        await self._publish_terminal_event(state)

    async def resume_after_hitl(self, workflow_id: UUID, hitl_response: Dict[str, Any]) -> GraphState:
        """Resume workflow after HITL response"""
        self._cancel_hitl_timeout(str(workflow_id))

        # Get current state
        current_state = await self.memory.get_workflow_state(workflow_id)
        if not current_state:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Add HITL response to state
        current_state.hitl_response = hitl_response

        return await self._run_graph(current_state)

    async def run_autonomous_discovery(self, supplier_id: UUID, workflow_id: UUID = None) -> GraphState:
        """Run autonomous risk discovery workflow (Workflow 1)"""
        initial_state = create_initial_state(
            workflow_type=WorkflowType.AUTONOMOUS_DISCOVERY,
            supplier_id=supplier_id,
            workflow_id=workflow_id
        )

        return await self._run_graph(initial_state)

    async def run_deep_dive_investigation(self, supplier_id: UUID = None, supplier_name: str = None, query: str = "", workflow_id: UUID = None) -> GraphState:
        """Run deep-dive investigation workflow (Workflow 2).

        Uses the CrewAI engine when `crewai.enabled` is set in config, falling
        back to the LangGraph pipeline transparently on any crew failure.
        """
        cfg = get_config()
        if (getattr(cfg, "crewai", {}) or {}).get("enabled"):
            try:
                return await self._run_deep_dive_crew(
                    supplier_id=supplier_id,
                    supplier_name=supplier_name,
                    query=query,
                    workflow_id=workflow_id,
                )
            except Exception as exc:
                self.logger.error(
                    "Deep-dive crew failed; falling back to LangGraph",
                    workflow_id=str(workflow_id) if workflow_id else None,
                    error=str(exc),
                )

        initial_state = create_initial_state(
            workflow_type=WorkflowType.DEEP_DIVE_INVESTIGATION,
            supplier_id=supplier_id,
            query=query,
            workflow_id=workflow_id
        )
        initial_state.state_data["supplier_name"] = supplier_name

        return await self._run_graph(initial_state)

    async def _run_deep_dive_crew(self, supplier_id: UUID = None, supplier_name: str = None, query: str = "", workflow_id: UUID = None) -> GraphState:
        """Execute the deep dive with the CrewAI engine."""
        from app.crews import DeepDiveCrew

        wf_id = workflow_id or uuid4()
        state = create_initial_state(
            workflow_type=WorkflowType.DEEP_DIVE_INVESTIGATION,
            supplier_id=supplier_id,
            query=query,
            workflow_id=wf_id,
        )
        state.state_data["supplier_name"] = supplier_name

        supplier_context: Dict[str, Any] = {}
        if supplier_id:
            try:
                supplier = await self.memory.db.get_supplier(supplier_id)
                if supplier:
                    supplier_context = {
                        "name": supplier.name,
                        "country": supplier.country,
                        "industry": supplier.industry,
                        "risk_score": supplier.risk_score,
                    }
            except Exception as exc:
                self.logger.warning("Could not load supplier context for crew",
                                    workflow_id=str(wf_id), error=str(exc))

        crew = DeepDiveCrew(
            workflow_id=wf_id,
            supplier_name=supplier_name,
            query=query,
            supplier_context=supplier_context,
        )
        result = await crew.run()

        state.state_data["crew_result"] = {k: v for k, v in result.items() if k != "summary"}
        summary = result.get("summary")
        if isinstance(summary, str):
            state.state_data["summary"] = summary
        state.status = "COMPLETED"
        state.completed_at = datetime.utcnow()
        state.current_agent = AgentRole.MITIGATOR.value

        await self.memory.save_workflow_state(state)
        await self._persist_crew_risk_factors(state, result)
        await self._publish_terminal_event(state)
        return state

    async def _persist_crew_risk_factors(self, state: GraphState, result: Dict[str, Any]) -> None:
        """Best-effort persistence of structured risk factors from the crew output."""
        factors = result.get("risk_factors")
        if not isinstance(factors, list) or not factors:
            return
        try:
            investigation = await self.memory.db.get_investigation(state.workflow_id)
            if not (investigation and state.supplier_id):
                return
            for factor in factors[:20]:
                if not isinstance(factor, dict):
                    continue
                try:
                    category = RiskCategory(str(factor.get("category", "")).upper())
                    level = RiskLevel(str(factor.get("level", "")).upper())
                except ValueError:
                    continue
                await self.memory.db.add_risk_factor(
                    supplier_id=state.supplier_id,
                    investigation_id=investigation.id,
                    category=category.value,
                    level=level.value,
                    title=str(factor.get("title", "Untitled risk"))[:255],
                    description=str(factor.get("description", "")),
                    confidence=float(factor.get("confidence", 0.5) or 0.5),
                    risk_metadata={"engine": "crewai"},
                )
        except Exception as exc:
            self.logger.warning("Failed to persist crew risk factors",
                                workflow_id=str(state.workflow_id), error=str(exc))

        # Keep the supplier's roll-up score in sync with new findings
        if state.supplier_id:
            try:
                await self.memory.db.recalculate_supplier_risk(state.supplier_id)
            except Exception as exc:
                self.logger.warning("Risk score recalculation failed",
                                    workflow_id=str(state.workflow_id), error=str(exc))

    async def resume_after_hitl(self, workflow_id: UUID, hitl_response: Dict[str, Any]) -> GraphState:
        """Resume workflow after HITL response"""
        self._cancel_hitl_timeout(str(workflow_id))

        # Get current state
        current_state = await self.memory.get_workflow_state(workflow_id)
        if not current_state:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Add HITL response to state
        current_state.hitl_response = hitl_response

        return await self._run_graph(current_state)
    
    async def get_workflow_status(self, workflow_id: UUID) -> Optional[GraphState]:
        """Get current workflow status"""
        return await self.memory.get_workflow_state(workflow_id)