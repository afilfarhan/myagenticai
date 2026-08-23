"""CrewAI deep-dive crew: output parsing and engine selection logic."""
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.crews import DeepDiveCrew
from app.graph import SentinelWorkflowRunner
from app.models import WorkflowType


def test_parse_output_extracts_valid_json():
    raw = 'Noise before {"risk_factors": [{"level": "HIGH"}], "summary": "ok"} noise after'
    parsed = DeepDiveCrew._parse_output(raw)
    assert parsed["summary"] == "ok"
    assert parsed["risk_factors"][0]["level"] == "HIGH"


def test_parse_output_returns_empty_for_prose():
    assert DeepDiveCrew._parse_output("The crew produced no structured output.") == {}


@pytest.mark.asyncio
async def test_crew_disabled_by_default(monkeypatch):
    """Without crewai.enabled the runner must not touch the crew engine."""
    monkeypatch.setattr(
        "app.graph.get_config",
        lambda: SimpleNamespace(crewai={"enabled": False}),
    )
    runner = SentinelWorkflowRunner.__new__(SentinelWorkflowRunner)  # skip Redis init
    executed = {}

    async def fake_run_graph(initial_state):
        executed["workflow_type"] = initial_state.workflow_type
        return initial_state

    monkeypatch.setattr(runner, "_run_graph", fake_run_graph)

    state = await runner.run_deep_dive_investigation(
        query="investigate this supplier", workflow_id=uuid4()
    )
    assert state.state_data.get("engine") != "crewai"
    assert executed["workflow_type"] == WorkflowType.DEEP_DIVE_INVESTIGATION


@pytest.mark.asyncio
async def test_crew_failure_falls_back_to_langgraph(monkeypatch):
    import sys
    import types as _types

    monkeypatch.setattr(
        "app.graph.get_config",
        lambda: SimpleNamespace(crewai={"enabled": True}),
    )

    class FailingCrew:
        def __init__(self, *args, **kwargs):
            pass

        async def run(self):
            raise RuntimeError("litellm unavailable")

    failing_module = _types.ModuleType("app.crews")
    failing_module.DeepDiveCrew = FailingCrew
    monkeypatch.setitem(sys.modules, "app.crews", failing_module)

    runner = SentinelWorkflowRunner.__new__(SentinelWorkflowRunner)
    import structlog

    runner.logger = structlog.get_logger("test")

    async def fake_run_graph(initial_state):
        return initial_state

    monkeypatch.setattr(runner, "_run_graph", fake_run_graph)

    state = await runner.run_deep_dive_investigation(
        query="investigate this supplier", workflow_id=uuid4()
    )
    # The LangGraph path ran instead of the failed crew.
    assert state.status == "RUNNING"
