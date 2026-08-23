"""Supplier CRUD API including the metadata round-trip regression."""
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_supplier_crud_and_metadata_roundtrip(client):
    name = f"Roundtrip Corp {uuid4().hex[:8]}"
    res = await client.post("/api/v1/suppliers", json={
        "name": name,
        "country": "DE",
        "tier": "TIER_2",
        "industry": "Automotive",
        "metadata": {"contract_id": "CT-42"},
    })
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["metadata"] == {"contract_id": "CT-42"}

    # Freshly loaded from the database (not the in-request instance).
    fetched = await client.get(f"/api/v1/suppliers/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["metadata"]["contract_id"] == "CT-42"

    listed = await client.get("/api/v1/suppliers", params={"query": name})
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    patched = await client.patch(f"/api/v1/suppliers/{created['id']}", json={"risk_score": 61.5})
    assert patched.status_code == 200
    assert patched.json()["risk_score"] == 61.5


@pytest.mark.asyncio
async def test_create_duplicate_supplier_conflicts(client):
    name = f"Dup Corp {uuid4().hex[:8]}"
    first = await client.post("/api/v1/suppliers", json={"name": name, "country": "US"})
    assert first.status_code == 201
    second = await client.post("/api/v1/suppliers", json={"name": name, "country": "US"})
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_create_supplier_validates_country(client):
    res = await client.post("/api/v1/suppliers", json={"name": "X", "country": "TOOLONG"})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_get_unknown_supplier_404(client):
    res = await client.get(f"/api/v1/suppliers/{uuid4()}")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_seed_endpoint_creates_suppliers(client):
    before = (await client.get("/api/v1/suppliers?limit=1")).json()["total"]
    res = await client.post("/api/v1/seed")
    assert res.status_code == 200
    after = (await client.get("/api/v1/suppliers?limit=1")).json()["total"]
    assert after - before >= 50
