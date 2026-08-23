"""Pure-logic tests for the LangGraph workflow module (no services required)."""
from app.graph import (
    GraphState,
    create_initial_state,
    route_after_analyst,
    route_after_auditor,
    route_after_hitl,
    route_after_scout,
)
from app.models import AgentRole, HITLStatus, WorkflowType


def _state(**kwargs) -> GraphState:
    state = create_initial_state(WorkflowType.DEEP_DIVE_INVESTIGATION, query="test query")
    for key, value in kwargs.items():
        setattr(state, key, value)
    return state


def test_initial_state_defaults():
    state = create_initial_state(
        WorkflowType.AUTONOMOUS_DISCOVERY, supplier_id=None, workflow_id=None
    )
    assert state.status == "RUNNING"
    assert state.workflow_type == WorkflowType.AUTONOMOUS_DISCOVERY
    assert state.max_steps == 10


def test_explicit_workflow_id_is_honoured():
    from uuid import uuid4

    wid = uuid4()
    state = create_initial_state(WorkflowType.COMPLIANCE_CHECK, workflow_id=wid)
    assert state.workflow_id == wid


def test_route_after_scout_proceeds_to_analyst():
    state = _state(current_agent=AgentRole.ANALYST.value)
    assert route_after_scout(state) == "analyst"


def test_route_after_scout_ends_on_step_budget():
    context = SimpleNamespaceLike(step_count=10)
    state = _state(agent_context=context, current_agent=AgentRole.ANALYST.value)
    assert route_after_scout(state) == "end"


def test_route_after_analyst_goes_to_auditor():
    state = _state(current_agent=AgentRole.AUDITOR.value)
    assert route_after_analyst(state) == "auditor"


def test_route_after_auditor_requests_hitl_when_required():
    state = _state(hitl_required=True)
    assert route_after_auditor(state) == "hitl_resume"


def test_route_after_auditor_proceeds_to_mitigator():
    state = _state(hitl_required=False, current_agent=AgentRole.MITIGATOR.value)
    assert route_after_auditor(state) == "mitigator"


def test_route_after_hitl_only_approve_continues():
    approved = _state(hitl_status=HITLStatus.APPROVED)
    denied = _state(hitl_status=HITLStatus.DENIED)
    assert route_after_hitl(approved) == "mitigator"
    assert route_after_hitl(denied) == "end"


class SimpleNamespaceLike:
    """Duck-typed stand-in for AgentContext in routing checks."""

    def __init__(self, step_count: int):
        self.step_count = step_count
