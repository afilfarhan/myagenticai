"""
FastAPI application for SentinelChain
"""
from contextlib import asynccontextmanager
from typing import Optional, List
from uuid import UUID, uuid4
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import structlog
import uvicorn
import asyncio
import json

from app.services.config import get_config, get_settings
from app.services.database import init_database, close_database, get_database_service, DatabaseService
from app.memory import get_memory_manager, close_memory_manager, MemoryManager
from app.graph import SentinelWorkflowRunner
from app.agents import (
    OrchestratorAgent, ScoutAgent, AnalystAgent, AuditorAgent, MitigatorAgent
)
from app.models import (
    Supplier, WorkflowType, RiskLevel, RiskCategory, SupplierTier,
    InvestigationRequest, InvestigationResponse, HITLStatus, Evidence,
    RiskFactor, MitigationAction, AlternativeSupplier
)
from app.schemas import (
    SupplierCreate, SupplierUpdate, SupplierResponse, SupplierListResponse,
    InvestigationRequestSchema, InvestigationResponseSchema,
    HITLResponseSchema, HealthCheckResponse, MetricsResponse,
    WorkflowStatusResponse,
    InvestigationSummaryResponse, InvestigationListResponse,
    RiskAlertResponse, AlertListResponse, RiskFactorResponse,
)
from app.api.audit import router as audit_router
from app.api.auth import get_current_user, get_current_user_optional

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Global instances
workflow_runner: Optional[SentinelWorkflowRunner] = None
orchestrator: Optional[OrchestratorAgent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global workflow_runner, orchestrator
    
    logger.info("Starting SentinelChain API")
    
    # Initialize database
    await init_database()
    
    # Initialize memory manager (Redis, Pinecone, Embeddings)
    memory_manager = await get_memory_manager()
    
    # Initialize agents
    scout = ScoutAgent()
    analyst = AnalystAgent()
    auditor = AuditorAgent()
    mitigator = MitigatorAgent()
    
    # Create orchestrator and register agents
    orchestrator = OrchestratorAgent()
    orchestrator.register_agent(scout)
    orchestrator.register_agent(analyst)
    orchestrator.register_agent(auditor)
    orchestrator.register_agent(mitigator)
    
    # Initialize workflow runner
    workflow_runner = SentinelWorkflowRunner()
    await workflow_runner.initialize()
    
    logger.info("SentinelChain API started successfully")
    
    yield
    
    logger.info("Shutting down SentinelChain API")
    await workflow_runner.close()
    await close_memory_manager()
    await close_database()
    logger.info("SentinelChain API shutdown complete")


app = FastAPI(
    title="SentinelChain API",
    description="An Agentic Supply Chain Risk & Compliance Engine",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(audit_router)


# Dependencies
def get_workflow_runner() -> SentinelWorkflowRunner:
    if workflow_runner is None:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")
    return workflow_runner


def get_orchestrator() -> OrchestratorAgent:
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return orchestrator


async def get_db() -> DatabaseService:
    return get_database_service()


# Health Check
@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """Health check endpoint"""
    config = get_config()
    return HealthCheckResponse(
        status="healthy",
        version=config.version,
        environment=config.environment,
        timestamp=__import__('datetime').datetime.utcnow(),
        services={
            "api": "healthy",
            "database": "healthy",
            "memory": "healthy",
            "workflow": "healthy" if workflow_runner else "unavailable"
        }
    )


# Metrics
@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics(db: DatabaseService = Depends(get_db)):
    """Get system metrics"""
    metrics = await db.get_dashboard_metrics()
    # false_positive_rate requires labeled feedback data; no source yet.
    return MetricsResponse(false_positive_rate=0.0, **metrics)


# Supplier Management - Real Implementation
@app.post("/api/v1/suppliers", response_model=SupplierResponse, status_code=201)
async def create_supplier(
    supplier: SupplierCreate,
    background_tasks: BackgroundTasks,
    db: DatabaseService = Depends(get_db)
):
    """Create a new supplier"""
    # Check if supplier already exists
    existing = await db.get_supplier_by_name(supplier.name)
    if existing:
        raise HTTPException(status_code=409, detail="Supplier already exists")
    
    # Create in database
    db_supplier = await db.create_supplier(
        name=supplier.name,
        legal_name=supplier.legal_name,
        tier=supplier.tier.value,
        country=supplier.country,
        region=supplier.region,
        industry=supplier.industry,
        website=supplier.website,
        contact_email=supplier.contact_email,
        contact_phone=supplier.contact_phone,
        is_active=True,
        supplier_metadata=supplier.metadata,
    )
    
    # Convert to Pydantic model
    created = Supplier(
        id=db_supplier.id,
        name=db_supplier.name,
        legal_name=db_supplier.legal_name,
        tier=SupplierTier(db_supplier.tier),
        country=db_supplier.country,
        region=db_supplier.region,
        industry=db_supplier.industry,
        website=db_supplier.website,
        contact_email=db_supplier.contact_email,
        contact_phone=db_supplier.contact_phone,
        risk_score=db_supplier.risk_score,
        last_assessed=db_supplier.last_assessed,
        is_active=db_supplier.is_active,
        metadata=db_supplier.supplier_metadata,
        created_at=db_supplier.created_at,
        updated_at=db_supplier.updated_at,
    )

    # Generate embedding and store in vector store (background task)
    background_tasks.add_task(save_supplier_to_vector_store, created)
    
    logger.info("Supplier created", supplier_id=str(created.id), name=supplier.name)
    return SupplierResponse(**created.model_dump())


async def save_supplier_to_vector_store(supplier: Supplier):
    """Background task to save supplier to vector store"""
    try:
        memory_manager = await get_memory_manager()
        await memory_manager.save_supplier_profile(supplier)
    except Exception as e:
        logger.error("Failed to save supplier to vector store", supplier_id=str(supplier.id), error=str(e))


@app.get("/api/v1/suppliers", response_model=SupplierListResponse)
async def list_suppliers(
    query: Optional[str] = None,
    tier: Optional[SupplierTier] = None,
    country: Optional[str] = None,
    industry: Optional[str] = None,
    risk_level: Optional[RiskLevel] = None,
    is_active: bool = True,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: DatabaseService = Depends(get_db)
):
    """List suppliers with filters"""
    db_suppliers, total = await db.list_suppliers(
        tier=tier.value if tier else None,
        country=country,
        industry=industry,
        is_active=is_active,
        limit=limit,
        offset=offset
    )
    
    suppliers = [
        Supplier(
            id=s.id,
            name=s.name,
            legal_name=s.legal_name,
            tier=SupplierTier(s.tier),
            country=s.country,
            region=s.region,
            industry=s.industry,
            website=s.website,
            contact_email=s.contact_email,
            contact_phone=s.contact_phone,
            risk_score=s.risk_score,
            last_assessed=s.last_assessed,
            is_active=s.is_active,
            metadata=s.supplier_metadata,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in db_suppliers
    ]
    
    return SupplierListResponse(
        suppliers=[SupplierResponse(**s.model_dump()) for s in suppliers],
        total=total,
        limit=limit,
        offset=offset
    )


@app.get("/api/v1/suppliers/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(supplier_id: UUID, db: DatabaseService = Depends(get_db)):
    """Get supplier by ID"""
    db_supplier = await db.get_supplier(supplier_id)
    if not db_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    supplier = Supplier(
        id=db_supplier.id,
        name=db_supplier.name,
        legal_name=db_supplier.legal_name,
        tier=SupplierTier(db_supplier.tier),
        country=db_supplier.country,
        region=db_supplier.region,
        industry=db_supplier.industry,
        website=db_supplier.website,
        contact_email=db_supplier.contact_email,
        contact_phone=db_supplier.contact_phone,
        risk_score=db_supplier.risk_score,
        last_assessed=db_supplier.last_assessed,
        is_active=db_supplier.is_active,
        metadata=db_supplier.supplier_metadata,
        created_at=db_supplier.created_at,
        updated_at=db_supplier.updated_at,
    )

    return SupplierResponse(**supplier.model_dump())


@app.get("/api/v1/suppliers/{supplier_id}/risk-factors", response_model=List[RiskFactorResponse])
async def list_supplier_risk_factors(supplier_id: UUID, db: DatabaseService = Depends(get_db)):
    """List risk factors detected for a supplier"""
    if not await db.get_supplier(supplier_id):
        raise HTTPException(status_code=404, detail="Supplier not found")

    factors = await db.list_risk_factors_for_supplier(supplier_id)
    return [
        RiskFactorResponse(
            id=f.id,
            supplier_id=f.supplier_id,
            category=RiskCategory(f.category),
            level=RiskLevel(f.level),
            title=f.title,
            description=f.description,
            evidence_ids=f.evidence_ids or [],
            confidence=f.confidence,
            impact_score=f.impact_score,
            likelihood_score=f.likelihood_score,
            detected_at=f.detected_at,
            acknowledged_at=f.acknowledged_at,
            resolved_at=f.resolved_at,
            metadata=f.risk_metadata or {},
        )
        for f in factors
    ]


@app.patch("/api/v1/suppliers/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: UUID,
    supplier_update: SupplierUpdate,
    background_tasks: BackgroundTasks,
    db: DatabaseService = Depends(get_db)
):
    """Update supplier"""
    update_data = supplier_update.model_dump(exclude_unset=True)

    # Map API field names to database column names
    if "tier" in update_data and hasattr(update_data["tier"], "value"):
        update_data["tier"] = update_data["tier"].value
    if "metadata" in update_data:
        update_data["supplier_metadata"] = update_data.pop("metadata")
    if "risk_score" in update_data:
        update_data["last_assessed"] = __import__('datetime').datetime.utcnow()
    
    db_supplier = await db.update_supplier(supplier_id, **update_data)
    if not db_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    # Update vector store in background
    supplier = Supplier(
        id=db_supplier.id,
        name=db_supplier.name,
        legal_name=db_supplier.legal_name,
        tier=SupplierTier(db_supplier.tier),
        country=db_supplier.country,
        region=db_supplier.region,
        industry=db_supplier.industry,
        website=db_supplier.website,
        contact_email=db_supplier.contact_email,
        contact_phone=db_supplier.contact_phone,
        risk_score=db_supplier.risk_score,
        last_assessed=db_supplier.last_assessed,
        is_active=db_supplier.is_active,
        metadata=db_supplier.supplier_metadata,
        created_at=db_supplier.created_at,
        updated_at=db_supplier.updated_at,
    )
    background_tasks.add_task(save_supplier_to_vector_store, supplier)
    
    return SupplierResponse(**supplier.model_dump())


@app.delete("/api/v1/suppliers/{supplier_id}", status_code=204)
async def delete_supplier(supplier_id: UUID, db: DatabaseService = Depends(get_db)):
    """Delete supplier (soft delete)"""
    result = await db.delete_supplier(supplier_id)
    if not result:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    # Also delete from vector store
    memory_manager = await get_memory_manager()
    await memory_manager.vector_store.delete_supplier(supplier_id)


# Dev-only seed endpoint
@app.post("/api/v1/seed")
async def seed_data(db: DatabaseService = Depends(get_db)):
    """Generate 50 dummy suppliers for development"""
    config = get_config()
    if config.environment == "production":
        raise HTTPException(status_code=403, detail="Not available in production")
    
    import random
    from faker import Faker
    fake = Faker()
    
    industries = ["Semiconductors", "Automotive", "Electronics", "Logistics", "Chemicals", "Textiles", "Machinery", "Food & Beverage"]
    countries = ["US", "DE", "CN", "TW", "JP", "KR", "IN", "VN", "MX", "BR", "GB", "FR", "IT", "NL", "PL"]
    tiers = ["TIER_1", "TIER_2", "TIER_3"]
    
    created = 0
    for _ in range(50):
        name = f"{fake.company()} {fake.company_suffix()}"
        supplier = await db.create_supplier(
            name=name,
            legal_name=f"{name}, Inc.",
            tier=random.choice(tiers),
            country=random.choice(countries),
            industry=random.choice(industries),
            risk_score=round(random.uniform(0, 100), 1),
            is_active=True,
        )
        created += 1
    
    return {"created": created, "message": f"Created {created} dummy suppliers"}


# Workflow Endpoints
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
    existing = await db.get_supplier_by_name(supplier_name.strip()) if supplier_name and supplier_name.strip() else None
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
                "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
            })
        except Exception:
            pass
        try:
            await get_database_service().update_investigation(
                workflow_id,
                status="FAILED",
                error=str(exc),
                completed_at=__import__('datetime').datetime.utcnow(),
            )
        except Exception:
            pass


@app.get("/api/v1/investigations", response_model=InvestigationListResponse)
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


@app.post("/api/v1/investigations", response_model=InvestigationResponseSchema)
async def start_investigation(
    request: InvestigationRequestSchema,
    background_tasks: BackgroundTasks,
    db: DatabaseService = Depends(get_db),
    runner: SentinelWorkflowRunner = Depends(get_workflow_runner)
):
    """Start a new investigation workflow.

    The workflow runs in the background; clients receive progress via the
    SSE stream at `/api/v1/investigations/{workflow_id}/stream`.
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


@app.get("/api/v1/investigations/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    workflow_id: UUID,
    runner: SentinelWorkflowRunner = Depends(get_workflow_runner)
):
    """Get workflow status"""
    state = await runner.get_workflow_status(workflow_id)
    if not state:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return WorkflowStatusResponse(**state.model_dump())


@app.post("/api/v1/investigations/{workflow_id}/hitl", response_model=WorkflowStatusResponse)
async def submit_hitl_response(
    workflow_id: UUID,
    response: HITLResponseSchema,
    runner: SentinelWorkflowRunner = Depends(get_workflow_runner)
):
    """Submit HITL response to resume workflow"""
    if response.workflow_id != workflow_id:
        raise HTTPException(status_code=400, detail="Workflow ID mismatch")
    
    result = await runner.resume_after_hitl(workflow_id, response.model_dump())
    
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return WorkflowStatusResponse(**result.model_dump())


# Recent Risk Alerts
@app.get("/api/v1/alerts/recent", response_model=AlertListResponse)
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


# Streaming endpoint for real-time updates
@app.get("/api/v1/investigations/{workflow_id}/stream")
async def stream_workflow_updates(workflow_id: UUID):
    """Stream real-time workflow updates via Server-Sent Events"""
    
    memory_manager = await get_memory_manager()
    
    async def event_generator():
        # Subscribe to Redis channel for this workflow
        channel = f"workflow:{workflow_id}:events"
        queue = await memory_manager.redis.subscribe(channel)
        
        try:
            while True:
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(message)}\n\n"
                    
                    # Check if workflow completed
                    if message.get("status") in ["COMPLETED", "FAILED", "CANCELLED", "ESCALATED", "WAITING_HITL"]:
                        break
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"data: {{\"type\": \"heartbeat\"}}\n\n"
        finally:
            await memory_manager.redis.unsubscribe(channel, queue)
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Agent Status
@app.get("/api/v1/agents/status")
async def get_agents_status(orch: OrchestratorAgent = Depends(get_orchestrator)):
    """Get status of all agents"""
    status = {}
    for role, agent in orch.agents.items():
        status[role.value.lower()] = {
            "status": "ready",
            "capabilities": await agent.get_capabilities()
        }
    return status


# Configuration
@app.get("/api/v1/config")
async def get_config_endpoint():
    """Get public configuration"""
    config = get_config()
    return {
        "version": config.version,
        "environment": config.environment,
        "features": {
            "autonomous_discovery": True,
            "deep_dive_investigation": True,
            "hitl_enabled": True,
            "streaming_updates": True
        }
    }


if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_config=None
    )