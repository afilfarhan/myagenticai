"""Investigation list/start/HITL-validation endpoints and recent alerts."""
from uuid import uuid4

import pytest

from app.services.database import get_database_service


@pytest.mark.asyncio
async def test_start_investigation_runs_in_background(client, fake_runner, db):
    supplier = await db.create_supplier(
        name=f"Probe Corp {uuid4().hex[:8]}", country="US"
    )

    res = await client.post("/api/v1/investigations", json={
        "supplier_id": str(supplier.id),
        "query": "Investigate the financial stability of this supplier",
        "workflow_type": "DEEP_DIVE_INVESTIGATION",
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "RUNNING"

    # Background task executed before the response completed.
    assert len(fake_runner.calls) == 1
    assert fake_runner.calls[0]["workflow_id"] is not None

    # The RUNNING row exists and shows up in listings.
    listed = await client.get("/api/v1/investigations", params={
        "supplier_id": str(supplier.id),
    })
    assert listed.status_code == 200
    ids = [i["workflow_id"] for i in listed.json()["investigations"]]
    assert body["workflow_id"] in ids


@pytest.mark.asyncio
async def test_start_investigation_creates_placeholder_supplier(client, fake_runner):
    res = await client.post("/api/v1/investigations", json={
        "supplier_name": f"Placeholder Industries {uuid4().hex[:6]}",
        "query": "Investigate sanctions exposure for this new entity",
        "workflow_type": "DEEP_DIVE_INVESTIGATION",
    })
    assert res.status_code == 200
    workflow_id = res.json()["workflow_id"]

    status = await client.get(f"/api/v1/investigations/{workflow_id}")
    assert status.status_code in (200, 404)  # 404 acceptable: Redis-less status store

    listed = await client.get("/api/v1/investigations", params={"limit": 100})
    names = [i["supplier_name"] for i in listed.json()["investigations"]]
    assert any(n and n.startswith("Placeholder Industries") for n in names)


@pytest.mark.asyncio
async def test_autonomous_discovery_requires_supplier_id(client, fake_runner):
    res = await client.post("/api/v1/investigations", json={
        "query": "Autonomous discovery without a target supplier",
        "workflow_type": "AUTONOMOUS_DISCOVERY",
    })
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_hitl_rejects_workflow_id_mismatch(client, fake_runner):
    res = await client.post(f"/api/v1/investigations/{uuid4()}/hitl", json={
        "workflow_id": str(uuid4()),
        "action": "APPROVE",
    })
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_hitl_rejects_invalid_action(client, fake_runner):
    wid = uuid4()
    res = await client.post(f"/api/v1/investigations/{wid}/hitl", json={
        "workflow_id": str(wid),
        "action": "MAYBE",
    })
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_recent_alerts_endpoint(client):
    db = get_database_service()

    supplier = await db.create_supplier(
        name=f"Alert Co {uuid4().hex[:8]}", country="CN"
    )
    investigation = await db.create_investigation(
        workflow_id=uuid4(),
        supplier_id=supplier.id,
        workflow_type="AUTONOMOUS_DISCOVERY",
        status="COMPLETED",
    )
    await db.add_risk_factor(
        supplier_id=supplier.id,
        investigation_id=investigation.id,
        category="GEOPOLITICAL",
        level="SEVERE",
        title="Port strike risk",
        description="Strike action expected to disrupt shipments.",
    )

    res = await client.get("/api/v1/alerts/recent", params={"limit": 5})
    assert res.status_code == 200
    alerts = res.json()["alerts"]
    match = [a for a in alerts if a["title"] == "Port strike risk"]
    assert match, "expected the seeded alert in recent alerts"
    assert match[0]["level"] == "SEVERE"
    assert match[0]["supplier_name"] == supplier.name


@pytest.mark.asyncio
async def test_supplier_risk_factors_endpoint(client):
    db = get_database_service()

    supplier = await db.create_supplier(
        name=f"RiskFactor Co {uuid4().hex[:8]}", country="TW"
    )
    investigation = await db.create_investigation(
        workflow_id=uuid4(),
        supplier_id=supplier.id,
        workflow_type="COMPLIANCE_CHECK",
        status="COMPLETED",
    )
    await db.add_risk_factor(
        supplier_id=supplier.id,
        investigation_id=investigation.id,
        category="ESG",
        level="MEDIUM",
        title="Reporting gap",
        description="Minor ESG reporting gap.",
        evidence_ids=[],
    )

    res = await client.get(f"/api/v1/suppliers/{supplier.id}/risk-factors")
    assert res.status_code == 200
    factors = res.json()
    assert any(f["title"] == "Reporting gap" and f["level"] == "MEDIUM" for f in factors)

    missing = await client.get(f"/api/v1/suppliers/{uuid4()}/risk-factors")
    assert missing.status_code == 404
