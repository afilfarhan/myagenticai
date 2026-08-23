"""Sprint 1 features: LangGraph findings persistence + LLM cost tracking."""
import structlog
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.graph import SentinelWorkflowRunner, create_initial_state
from app.agents import AgentContext
from app.models import (
    AlternativeSupplier, Evidence, EvidenceType, MitigationAction,
    RiskCategory, RiskFactor, RiskLevel,
)
from app.services.database import get_database_service, MitigationActionDB, EvidenceDB
from app.services.cost_sink import db_cost_sink


def _runner_with_db(db):
    runner = SentinelWorkflowRunner.__new__(SentinelWorkflowRunner)
    runner.memory = SimpleNamespace(db=db)
    runner.logger = structlog.get_logger("test")
    return runner


@pytest.mark.asyncio
async def test_langgraph_findings_are_persisted():
    db = get_database_service()

    supplier = await db.create_supplier(
        name=f"Persist Co {uuid4().hex[:8]}", country="TW", industry="Semiconductors"
    )
    investigation = await db.create_investigation(
        workflow_id=uuid4(),
        supplier_id=supplier.id,
        workflow_type="DEEP_DIVE_INVESTIGATION",
        status="COMPLETED",
    )

    wid = investigation.workflow_id
    evidence = Evidence(
        supplier_id=supplier.id,
        type=EvidenceType.NEWS_ARTICLE,
        source="https://news.example.com/article",
        title="Factory disruption reported",
        content="A fire halted production lines at the primary fab.",
        credibility_score=0.8,
        relevance_score=0.9,
    )
    risk_factor = RiskFactor(
        supplier_id=supplier.id,
        category=RiskCategory.OPERATIONAL,
        level=RiskLevel.HIGH,
        title="Production halt",
        description="Fire stopped output at the main fab.",
        evidence_ids=[evidence.id],
        confidence=0.85,
        impact_score=70,
        likelihood_score=60,
    )
    mitigation = MitigationAction(
        risk_factor_id=risk_factor.id,
        title="Qualify second-source fab",
        description="Onboard an alternate foundry within 90 days.",
        action_type="DUAL_SOURCING",
        estimated_timeline_days=90,
    )
    alternative = AlternativeSupplier(
        original_supplier_id=supplier.id,
        name="Backup Fab Ltd",
        country="JP",
        risk_score=25.0,
    )

    context = AgentContext(
        workflow_id=wid,
        supplier_id=supplier.id,
        evidence=[evidence],
        risk_factors=[risk_factor],
        mitigation_actions=[mitigation],
        alternative_suppliers=[alternative],
    )
    state = create_initial_state(
        "DEEP_DIVE_INVESTIGATION", supplier_id=supplier.id, query="q" * 12, workflow_id=wid
    )
    state.agent_context = context
    state.risk_factors_identified = [risk_factor]

    runner = _runner_with_db(db)
    await runner._persist_langgraph_findings(state)

    factors = await db.list_risk_factors_for_supplier(supplier.id)
    persisted_rf = next(f for f in factors if f.title == "Production halt")
    assert persisted_rf.level == "HIGH"
    assert persisted_rf.risk_metadata.get("engine") == "langgraph"

    # Stored evidence_ids reference the persisted EvidenceDB rows
    from sqlalchemy import select
    async with db._factory() as session:
        ev_rows = (await session.execute(
            select(EvidenceDB).where(EvidenceDB.supplier_id == supplier.id)
        )).scalars().all()
    assert any(ev.title == "Factory disruption reported" for ev in ev_rows)
    stored_ids = {str(e) for e in (persisted_rf.evidence_ids or [])}
    assert stored_ids and stored_ids.issubset({str(ev.id) for ev in ev_rows})


    # Mitigation was attached to the persisted factor row
    async with db._factory() as session:
        ma_rows = (await session.execute(select(MitigationActionDB))).scalars().all()
    match = [m for m in ma_rows if m.title == "Qualify second-source fab"]
    assert match and str(match[0].risk_factor_id) == str(persisted_rf.id)

    # Alternative supplier row persisted with correct linkage
    from app.services.database import AlternativeSupplierDB
    async with db._factory() as session:
        alt_rows = (await session.execute(
            select(AlternativeSupplierDB).where(
                AlternativeSupplierDB.original_supplier_id == supplier.id)
        )).scalars().all()
    assert any(a.name == "Backup Fab Ltd" and str(a.investigation_id) == str(investigation.id)
               for a in alt_rows)


@pytest.mark.asyncio
async def test_persistence_noops_without_rows():
    db = get_database_service()
    runner = _runner_with_db(db)

    state = create_initial_state("DEEP_DIVE_INVESTIGATION", query="q" * 12)
    # No investigation row for this workflow id -> must not raise
    await runner._persist_langgraph_findings(state)


@pytest.mark.asyncio
async def test_cost_sink_persists_usage_record():
    db = get_database_service()
    wf_id = uuid4()
    await db_cost_sink(
        model="claude-3-5-sonnet",
        provider="primary",
        input_tokens=1200,
        output_tokens=340,
        cost_usd=0.0123,
        metadata={"workflow_id": str(wf_id)},
    )

    from sqlalchemy import select
    from app.services.database import CostTrackingDB
    async with db._factory() as session:
        rows = (await session.execute(select(CostTrackingDB))).scalars().all()
    match = [r for r in rows if r.input_tokens == 1200 and r.model == "claude-3-5-sonnet"]
    assert match, "expected a persisted cost record"
    assert str(match[0].workflow_id) == str(wf_id)
    assert match[0].cost_usd == pytest.approx(0.0123)


@pytest.mark.asyncio
async def test_gateway_cost_callback_receives_metadata():
    from app.services.llm_gateway import LLMGateway, ProviderRole

    gateway = LLMGateway(config={})
    captured = []

    async def spy(**kwargs):
        captured.append(kwargs)

    gateway.register_cost_callback(spy)

    class FakeUsage:
        prompt_tokens = 100
        completion_tokens = 50

    class FakeResponse:
        usage = FakeUsage()

    await gateway._track_cost(
        FakeResponse(), "gpt-4o", ProviderRole.MULTIMODAL,
        metadata={"workflow_id": "abc", "supplier_id": None},
    )

    assert captured, "callback should have fired"
    assert captured[0]["input_tokens"] == 100
    assert captured[0]["metadata"]["workflow_id"] == "abc"


@pytest.mark.asyncio
async def test_metrics_include_llm_cost(client):
    db = get_database_service()
    await db.track_cost(
        provider="primary", model="test-model",
        input_tokens=10, output_tokens=5, cost_usd=0.25, operation="llm.complete",
    )
    res = await client.get("/metrics")
    assert res.status_code == 200
    assert res.json()["cost_last_30_days"] >= 0.25
