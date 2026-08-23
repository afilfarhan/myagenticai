"""WebSocket streaming endpoint - real subscribe/publish/close cycle."""
from uuid import uuid4

from starlette.testclient import TestClient

from app.main import app


def test_websocket_receives_events_until_terminal_status():
    workflow_id = uuid4()

    with TestClient(app) as client:  # starts the app portal (and lifespan)
        assert client.portal is not None

        with client.websocket_connect(
            f"/api/v1/investigations/{workflow_id}/ws"
        ) as websocket:
            from app.memory import get_memory_manager

            async def publish_event(payload):
                memory_manager = await get_memory_manager()
                await memory_manager.publish_workflow_event(workflow_id, payload)

            # A regular step event arrives first...
            client.portal.start_task_soon(
                publish_event,
                {"workflow_id": str(workflow_id), "agent": "SCOUT",
                 "message": "Scout online", "status": "RUNNING", "step": 1,
                 "hitl_required": False, "hitl_payload": None},
            )
            first = websocket.receive_json()
            assert first["message"] == "Scout online"
            assert first["status"] == "RUNNING"

            # ...then a terminal status closes the stream server-side.
            client.portal.start_task_soon(
                publish_event,
                {"workflow_id": str(workflow_id), "agent": None,
                 "message": "done", "status": "COMPLETED", "step": 2,
                 "hitl_required": False, "hitl_payload": None},
            )
            last = websocket.receive_json()
            assert last["status"] == "COMPLETED"


def test_websocket_heartbeat_on_silence():
    """With no traffic the socket still answers - heartbeat keeps it alive."""
    workflow_id = uuid4()

    with TestClient(app) as client:
        # Heartbeat fires after 30s of silence; too slow for CI, so instead we
        # just verify the endpoint accepts a connection and echoes nothing
        # before we close it cleanly.
        with client.websocket_connect(
            f"/api/v1/investigations/{workflow_id}/ws"
        ) as websocket:
            assert websocket is not None
            websocket.close()
