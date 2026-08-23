"""
Investigation endpoints: start (background), list, status, HITL resume,
SSE + WebSocket streaming.
"""
import asyncio
import json
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import structlog
from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, Query,
    WebSocket, WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse

from app.agents import OrchestratorAgent  # noqa: F401 - re-exported for deps typing
from app.api.deps import get_db, get_workflow_runner
from app.graph import SentinelWorkflowRunner
from app.memory import get_memory_manager
from app.models import WorkflowType
from app.schemas import (
    InvestigationRequestSchema, InvestigationResponseSchema,
    HITLResponseSchema, WorkflowStatusResponse,
    InvestigationSummaryResponse, InvestigationListResponse,
    RiskAlertResponse, AlertListResponse,
)
from app.services.database import DatabaseService, get_database_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/investigations", tags=["Investigations"])
alert_router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts"])

# Workflow statuses that end an SSE/WebSocket stream
TERMINAL_WORKFLOW_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "ESCALATED", "WAITING_HITL"}


async def _resolve_or_create_supplier(
    db: DatabaseService,
    supplier_id: Optional[UUID],
    supplier_name: Optional[str],
    fallback_query: str,
) -> UUID:
    """Resolve a supplier for an investigation, creating a placeholder when needed."""
    if supplier_id:
        return supplier_id

    name = (supplier_name or "").strip() or fallback_query.strip()[:80]
    if supplier_name and supplier_name.strip():
        existing = await db.get_supplier_by_name(supplier_name.strip())
        if existing:
            return existing.id

    created = await db.create_supplier(
        name=name,
        tier="UNKNOWN",
        country="UNKNOWN",
        supplier_metadata={"placeholder": True},
    )
    logger.info("Placeholder supplier created for investigation",
                supplier_id=str(created.id), name=name)
    return created.id


async def _execute_workflow(
    runner: SentinelWorkflowRunner,
    workflow_type: WorkflowType,
    supplier_id: UUID,
    supplier_name: Optional[str],
    query: str,
    workflow_id: UUID,
) -> None:
    """Background task that runs a workflow to completion."""
    try:
        if workflow_type == WorkflowType.AUTONOMOUS_DISCOVERY:
            await runner.run_autonomous_discovery(supplier_id, workflow_id=workflow_id)
        else:
            await runner.run_deep_dive_investigation(
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                query=query,
                workflow_id=workflow_id,
            )
    except Exception as exc:
        logger.error("Workflow execution failed",
                     workflow_id=str(workflow_id), error=str(exc))
        try:
            memory_manager = await get_memory_manager()
            await memory_manager.publish_workflow_event(workflow_id, {
                "workflow_id": str(workflow_id),
                "agent": None,
                "message": f"Workflow failed: {exc}",
                "status": "FAILED",
                "step": 0,
                "hitl_required": False,
                "hitl_payload": None,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception:
            pass
        try:
            await get_database_service().update_investigation(
                workflow_id,
                status="FAILED",
                error=str(exc),
                completed_at=datetime.utcnow(),
            )
        except Exception:
            pass


@router.get("", response_model=InvestigationListResponse)
async def list_investigations(
    supplier_id: Optional[UUID] = None,
    status: Optional[str] = None,
    workflow_type: Optional[WorkflowType] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: DatabaseService = Depends(get_db),
):
    """List investigations with optional filters (newest first)"""
    rows, total = await db.list_investigations(
        supplier_id=supplier_id,
        status=status,
        workflow_type=workflow_type.value if workflow_type else None,
        limit=limit,
        offset=offset,
    )

    investigations = [
        InvestigationSummaryResponse(
            workflow_id=inv.workflow_id,
            supplier_id=inv.supplier_id,
            supplier_name=supplier_name,
            workflow_type=WorkflowType(inv.workflow_type),
            status=inv.status,
            query=inv.query,
            hitl_required=inv.hitl_required,
            hitl_status=inv.hitl_status,
            error=inv.error,
            step_count=inv.step_count,
            created_at=inv.created_at,
            updated_at=inv.updated_at,
            completed_at=inv.completed_at,
        )
        for inv, supplier_name in rows
    ]

    return InvestigationListResponse(
        investigations=investigations,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=InvestigationResponseSchema)
async def start_investigation(
    request: InvestigationRequestSchema,
    background_tasks: BackgroundTasks,
    db: DatabaseService = Depends(get_db),
    runner: SentinelWorkflowRunner = Depends(get_workflow_runner),
):
    """Start a new investigation workflow.

    The workflow runs in the background; clients receive progress via the
    SSE stream at `/api/v1/investigations/{workflow_id}/stream` or the
    WebSocket at `/api/v1/investigations/{workflow_id}/ws`.
    """
    if request.workflow_type == WorkflowType.AUTONOMOUS_DISCOVERY and not request.supplier_id:
        raise HTTPException(status_code=400, detail="supplier_id required for autonomous discovery")

    supplier_id = await _resolve_or_create_supplier(
        db, request.supplier_id, request.supplier_name, request.query
    )

    workflow_id = uuid4()

    # Create a RUNNING row up front so the investigation is visible in
    # listings/metrics while executing (final state is upserted by the runner).
    await db.create_investigation(
        workflow_id=workflow_id,
        supplier_id=supplier_id,
        workflow_type=request.workflow_type.value,
        status="RUNNING",
        query=request.query,
    )

    background_tasks.add_task(
        _execute_workflow,
        runner,
        request.workflow_type,
        supplier_id,
        request.supplier_name,
        request.query,
        workflow_id,
    )

    return InvestigationResponseSchema(
        workflow_id=workflow_id,
        status="RUNNING",
        summary=None,
        risk_factors=[],
        mitigation_actions=[],
        alternative_suppliers=[],
        evidence=[],
        hitl_required=False,
        hitl_payload=None,
        processing_time_seconds=0.0,
    )


@router.get("/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    workflow_id: UUID,
    runner: SentinelWorkflowRunner = Depends(get_workflow_runner),
):
    """Get workflow status"""
    state = await runner.get_workflow_status(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return WorkflowStatusResponse(**state.model_dump())


@router.post("/{workflow_id}/hitl", response_model=WorkflowStatusResponse)
async def submit_hitl_response(
    workflow_id: UUID,
    response: HITLResponseSchema,
    runner: SentinelWorkflowRunner = Depends(get_workflow_runner),
):
    """Submit HITL response to resume workflow"""
    if response.workflow_id != workflow_id:
        raise HTTPException(status_code=400, detail="Workflow ID mismatch")

    result = await runner.resume_after_hitl(workflow_id, response.model_dump())

    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return WorkflowStatusResponse(**result.model_dump())


@router.get("/{workflow_id}/stream")
async def stream_workflow_updates(workflow_id: UUID):
    """Stream real-time workflow updates via Server-Sent Events"""
    memory_manager = await get_memory_manager()

    async def event_generator():
        channel = f"workflow:{workflow_id}:events"
        queue = await memory_manager.redis.subscribe(channel)

        try:
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(message)}\n\n"

                    if message.get("status") in TERMINAL_WORKFLOW_STATUSES:
                        break
                except asyncio.TimeoutError:
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
        finally:
            await memory_manager.redis.unsubscribe(channel, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.websocket("/{workflow_id}/ws")
async def ws_workflow_updates(websocket: WebSocket, workflow_id: UUID):
    """Stream real-time workflow updates over a WebSocket.

    Message frames mirror the SSE events (JSON objects); heartbeats are sent
    every 30s of silence, and the socket closes after a terminal status.
    """
    await websocket.accept()
    memory_manager = await get_memory_manager()
    channel = f"workflow:{workflow_id}:events"
    queue = await memory_manager.redis.subscribe(channel)

    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(message)
                if message.get("status") in TERMINAL_WORKFLOW_STATUSES:
                    break
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "heartbeat"})
    except WebSocketDisconnect:
        pass
    finally:
        await memory_manager.redis.unsubscribe(channel, queue)
        try:
            await websocket.close()
        except Exception:
            pass


@alert_router.get("/recent", response_model=AlertListResponse)
async def list_recent_alerts(
    hours: Optional[int] = Query(None, ge=1, le=720),
    level: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: DatabaseService = Depends(get_db),
):
    """List recent risk alerts (risk factors), newest first.

    Pass `hours` to restrict to a detection window; omit for all history.
    """
    rows = await db.list_recent_risk_factors(hours=hours, level=level, limit=limit)

    alerts = [
        RiskAlertResponse(
            id=rf.id,
            supplier_id=rf.supplier_id,
            supplier_name=supplier_name,
            category=str(rf.category),
            level=str(rf.level),
            title=rf.title,
            description=rf.description,
            confidence=rf.confidence,
            impact_score=rf.impact_score,
            likelihood_score=rf.likelihood_score,
            detected_at=rf.detected_at,
        )
        for rf, supplier_name in rows
    ]

    return AlertListResponse(alerts=alerts, total=len(alerts))
