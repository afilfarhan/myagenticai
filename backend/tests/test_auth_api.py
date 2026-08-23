"""Auth primitives and scope-protected endpoints."""
import pytest

from app.api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)


def _access_token(scopes=None):
    return create_access_token({
        "sub": "user-1",
        "tenant_id": "tenant-1",
        "tier": "pro",
        "scopes": scopes or [],
    })


def test_password_hash_roundtrip():
    hashed = get_password_hash("s3cret-password")
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_access_token_roundtrip():
    payload = decode_token(_access_token(scopes=["audit.read"]))
    assert payload is not None
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"
    assert payload["scopes"] == ["audit.read"]


def test_decode_invalid_token_returns_none():
    assert decode_token("not-a-real-jwt") is None


def test_refresh_token_has_refresh_type():
    payload = decode_token(create_refresh_token({"sub": "user-1", "tenant_id": "t"}))
    assert payload["type"] == "refresh"


@pytest.mark.asyncio
async def test_audit_endpoint_requires_auth(client):
    res = await client.get("/api/v1/audit/events")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_audit_endpoint_rejects_missing_scope(client):
    res = await client.get(
        "/api/v1/audit/events",
        headers={"Authorization": f"Bearer {_access_token()}"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_audit_endpoint_allows_audit_read_scope(client):
    res = await client.get(
        "/api/v1/audit/events",
        headers={"Authorization": f"Bearer {_access_token(['audit.read'])}"},
    )
    assert res.status_code == 200
    assert res.json() == []
