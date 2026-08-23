"""
Shared pytest fixtures for the SentinelChain core test suite.

The suite runs without external services (Redis, Pinecone, LLM APIs): the app
is exercised through httpx's ASGI transport without the lifespan handler, and
only the database layer is initialised manually against a temporary SQLite
file. Workflow execution is covered with a fake runner via dependency override.
"""
import asyncio
import os
import tempfile
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

# Point the app at a throwaway database before anything imports app config.
_tmp_db = os.path.join(tempfile.gettempdir(), f"sentinelchain-test-{uuid4().hex}.db")
os.environ["DATABASE__URL"] = f"sqlite+aiosqlite:///{_tmp_db}"

from app.services.config import reset_config  # noqa: E402

reset_config()

from app.main import app  # noqa: E402
from app.services.database import (  # noqa: E402
    close_database,
    get_database_service,
    init_database,
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _database():
    await init_database()
    yield
    await close_database()


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class FakeWorkflowRunner:
    """Records workflow starts instead of executing agents."""

    def __init__(self):
        self.calls = []

    async def run_deep_dive_investigation(self, supplier_id=None, supplier_name=None, query="", workflow_id=None):
        self.calls.append({
            "type": "deep_dive",
            "supplier_id": supplier_id,
            "supplier_name": supplier_name,
            "query": query,
            "workflow_id": workflow_id,
        })
        return SimpleNamespace(
            workflow_id=workflow_id or uuid4(),
            status="COMPLETED",
            hitl_required=False,
            hitl_payload=None,
            state_data={"summary": "fake"},
        )

    async def run_autonomous_discovery(self, supplier_id, workflow_id=None):
        self.calls.append({"type": "autonomous", "supplier_id": supplier_id, "workflow_id": workflow_id})
        return SimpleNamespace(
            workflow_id=workflow_id or uuid4(),
            status="COMPLETED",
            hitl_required=False,
            hitl_payload=None,
            state_data={},
        )

    async def get_workflow_status(self, workflow_id):
        return None

    async def resume_after_hitl(self, workflow_id, hitl_response):
        return SimpleNamespace(
            workflow_id=workflow_id,
            status="COMPLETED",
            hitl_required=False,
            hitl_payload=None,
            state_data={},
        )


@pytest_asyncio.fixture
async def fake_runner():
    runner = FakeWorkflowRunner()
    from app.main import get_workflow_runner

    app.dependency_overrides[get_workflow_runner] = lambda: runner
    yield runner
    app.dependency_overrides.pop(get_workflow_runner, None)


@pytest.fixture
def db():
    return get_database_service()
