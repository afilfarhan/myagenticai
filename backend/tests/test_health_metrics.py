"""Health, metrics and config endpoints."""
from uuid import uuid4

from app.services.database import get_database_service

import pytest


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "healthy"
    assert "database" in body["services"]


@pytest.mark.asyncio
async def test_metrics_reflect_database_state(client):
    db = get_database_service()

    supplier = await db.create_supplier(
        name=f"Metrics Supplier {uuid4().hex[:8]}",
        country="US",
        tier="TIER_1",
        risk_score=42.0,
    )
    investigation = await db.create_investigation(
        workflow_id=uuid4(),
        supplier_id=supplier.id,
        workflow_type="DEEP_DIVE_INVESTIGATION",
        status="RUNNING",
        query="metrics test",
    )
    await db.add_risk_factor(
        supplier_id=supplier.id,
        investigation_id=investigation.id,
        category="FINANCIAL",
        level="HIGH",
        title="Metrics test factor",
        description="desc",
    )

    res = await client.get("/metrics")
    assert res.status_code == 200
    metrics = res.json()
    assert metrics["total_suppliers"] >= 1
    assert metrics["active_workflows"] >= 1
    assert metrics["risk_alerts_24h"] >= 1


@pytest.mark.asyncio
async def test_config_endpoint_lists_features(client):
    res = await client.get("/api/v1/config")
    assert res.status_code == 200
    features = res.json()["features"]
    assert features["deep_dive_investigation"] is True
