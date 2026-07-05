"""
FastAPI application for SentinelChain
"""
from contextlib import asynccontextmanager
from typing import Optional, List
from uuid import UUID
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import structlog
import uvicorn

from app.config import get_config
from app.memory import MemoryManager
from app.graph import SentinelWorkflowRunner
from app.models import (
    Supplier, WorkflowType, RiskLevel, RiskCategory, SupplierTier,
    InvestigationRequest, InvestigationResponse, HITLStatus
)
from app.schemas import (
    SupplierCreate, SupplierUpdate, SupplierResponse, SupplierListResponse,
    InvestigationRequestSchema, InvestigationResponseSchema,
    HITLResponseSchema, HealthCheckResponse, MetricsResponse,
    WorkflowStatusResponse
)
from app.agents import OrchestratorAgent, ScoutAgent, AnalystAgent, AuditorAgent, MitigatorAgent

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
memory_manager: Optional[MemoryManager] = None
workflow_runner: Optional[SentinelWorkflowRunner] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global memory_manager, workflow_runner
    
    logger.info("Starting SentinelChain API")
    
    # Initialize memory
    config = get_config()
    memory_manager = MemoryManager(config.memory.model_dump() if hasattr(config.memory, 'model_dump') else {})
    await memory_manager.initialize()
    
    # Initialize workflow runner
    workflow_runner = SentinelWorkflowRunner()
    await workflow_runner.initialize()
    
    logger.info("SentinelChain API started successfully")
    
    yield
    
    logger.info("Shutting down SentinelChain API")
    await workflow_runner.close()
    await memory_manager.close()
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
    allow_origins=["*"] if config.environment == "development" else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency to get workflow runner
def get_workflow_runner() -> SentinelWorkflowRunner:
    if workflow_runner is None:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")
    return workflow_runner


def get_memory_manager() -> MemoryManager:
    if memory_manager is None:
        raise HTTPException(status_code=503, detail="Memory manager not initialized")
    return memory_manager


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
            "memory": "healthy" if memory_manager else "unavailable",
            "workflow": "healthy" if workflow_runner else "unavailable"
        }
    )


# Metrics
@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics(runner: SentinelWorkflowRunner = Depends(get_workflow_runner)):
    """Get system metrics"""
    # In production, query actual metrics from monitoring systems
    return MetricsResponse(
        total_suppliers=0,
        active_workflows=0,
        risk_alerts_24h=0,
        avg_risk_score=0.0,
        cost_last_30_days=0.0,
        false_positive_rate=0.0
    )


# Supplier Management
@app.post("/api/v1/suppliers", response_model=SupplierResponse, status_code=201)
async def create_supplier(
    supplier: SupplierCreate,
    background_tasks: BackgroundTasks,
    mem: MemoryManager = Depends(get_memory_manager)
):
    """Create a new supplier"""
    # In production, save to database
    new_supplier = Supplier(**supplier.model_dump())
    
    # Generate embedding and store in Pinecone
    # embedding = await generate_embedding(f"{supplier.name} {supplier.country} {supplier.industry or ''}")
    # await mem.save_supplier_profile(new_supplier, embedding)
    
    logger.info("Supplier created", supplier_id=str(new_supplier.id), name=supplier.name)
    return SupplierResponse(**new_supplier.model_dump())


@app.get("/api/v1/suppliers", response_model=SupplierListResponse)
async def list_suppliers(
    query: Optional[str] = None,
    tier: Optional[SupplierTier] = None,
    country: Optional[str] = None,
    risk_level: Optional[RiskLevel] = None,
    is_active: bool = True,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    mem: MemoryManager = Depends(get_memory_manager)
):
    """List suppliers with filters"""
    # In production, query database with filters
    suppliers = []
    total = 0
    
    return SupplierListResponse(
        suppliers=[SupplierResponse(**s.model_dump()) for s in suppliers],
        total=total,
        limit=limit,
        offset=offset
    )


@app.get("/api/v1/suppliers/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(supplier_id: UUID, mem: MemoryManager = Depends(get_memory_manager)):
    """Get supplier by ID"""
    # In production, query database
    raise HTTPException(status_code=404, detail="Supplier not found")


@app.patch("/api/v1/suppliers/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: UUID,
    supplier_update: SupplierUpdate,
    mem: MemoryManager = Depends(get_memory_manager)
):
    """Update supplier"""
    # In production, update database and Pinecone
    raise HTTPException(status_code=404, detail="Supplier not found")


@app.delete("/api/v1/suppliers/{supplier_id}", status_code=204)
async def delete_supplier(supplier_id: UUID, mem: MemoryManager = Depends(get_memory_manager)):
    """Delete supplier (soft delete)"""
    # In production, soft delete in database
    raise HTTPException(status_code=404, detail="Supplier not found")


# Workflow Endpoints
@app.post("/api/v1/investigations", response_model=InvestigationResponseSchema)
async def start_investigation(
    request: InvestigationRequestSchema,
    background_tasks: BackgroundTasks,
    runner: SentinelWorkflowRunner = Depends(get_workflow_runner)
):
    """Start a new investigation workflow"""
    
    if request.workflow_type == WorkflowType.AUTONOMOUS_DISCOVERY:
        if not request.supplier_id:
            raise HTTPException(status_code=400, detail="supplier_id required for autonomous discovery")
        result = await runner.run_autonomous_discovery(request.supplier_id)
    else:
        result = await runner.run_deep_dive_investigation(
            supplier_id=request.supplier_id,
            supplier_name=request.supplier_name,
            query=request.query
        )
    
    if isinstance(result, dict):
        # Handle error case
        raise HTTPException(status_code=500, detail=result.get("error", "Workflow failed"))
    
    # Convert to response schema
    return InvestigationResponseSchema(
        workflow_id=result.workflow_id,
        status=result.status,
        summary=result.state_data.get("summary"),
        risk_factors=[],  # Would convert from result.risk_factors_identified
        mitigation_actions=[],
        alternative_suppliers=[],
        evidence=[],
        hitl_required=result.hitl_required,
        hitl_payload=result.hitl_payload,
        processing_time_seconds=0.0
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


# Streaming endpoint for real-time updates
@app.get("/api/v1/investigations/{workflow_id}/stream")
async def stream_workflow_updates(workflow_id: UUID):
    """Stream real-time workflow updates via Server-Sent Events"""
    
    async def event_generator():
        # In production, subscribe to Redis pub/sub for this workflow
        import asyncio
        for i in range(10):
            yield f"data: {{\"step\": {i}, \"message\": \"Processing...\"}}\n\n"
            await asyncio.sleep(1)
        yield f"data: {{\"step\": 10, \"message\": \"Complete\", \"status\": \"COMPLETED\"}}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Agent Status
@app.get("/api/v1/agents/status")
async def get_agents_status():
    """Get status of all agents"""
    return {
        "scout": {"status": "ready", "capabilities": ["sanctions_monitoring", "news_search", "financial_reports"]},
        "analyst": {"status": "ready", "capabilities": ["risk_synthesis", "financial_analysis", "monte_carlo"]},
        "auditor": {"status": "ready", "capabilities": ["sanctions_screening", "esg_compliance", "regulatory_check"]},
        "mitigator": {"status": "ready", "capabilities": ["alternative_sourcing", "cost_calculation", "procurement_tickets"]},
    }


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