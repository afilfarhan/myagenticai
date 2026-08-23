"""
FastAPI application for SentinelChain.

Route modules live in app/api/*; this module wires the app together:
lifespan (service bootstrapping), CORS, and router registration.
"""
from contextlib import asynccontextmanager
from typing import Optional

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.services.config import get_config, get_settings
from app.services.database import init_database, close_database
from app.services.llm_gateway import get_llm_gateway
from app.memory import get_memory_manager, close_memory_manager
from app.graph import SentinelWorkflowRunner
from app.agents import OrchestratorAgent, ScoutAgent, AnalystAgent, AuditorAgent, MitigatorAgent

# Re-export dependencies so tests/clients can override them via a stable path.
from app.api.deps import get_db, get_workflow_runner, get_orchestrator  # noqa: F401
from app.api.system import router as system_router
from app.api.suppliers import router as suppliers_router
from app.api.investigations import router as investigations_router, alert_router
from app.api.audit import router as audit_router

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting SentinelChain API")

    # Initialize database
    await init_database()

    # Initialize memory manager (Redis, Pinecone, Embeddings)
    await get_memory_manager()

    # Initialize agents
    orchestrator = OrchestratorAgent()
    orchestrator.register_agent(ScoutAgent())
    orchestrator.register_agent(AnalystAgent())
    orchestrator.register_agent(AuditorAgent())
    orchestrator.register_agent(MitigatorAgent())

    # Initialize workflow runner
    workflow_runner = SentinelWorkflowRunner()
    await workflow_runner.initialize()

    # Expose shared services via app.state (consumed by api.deps)
    app.state.orchestrator = orchestrator
    app.state.workflow_runner = workflow_runner

    # Persist LLM usage to CostTrackingDB (feeds /metrics cost_last_30_days)
    from app.services.cost_sink import register_cost_sink
    register_cost_sink(get_llm_gateway())

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

# CORS middleware - origins are config-driven (config.yaml / CORS_ORIGINS env)
config = get_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(system_router)
app.include_router(suppliers_router)
app.include_router(investigations_router)
app.include_router(alert_router)
app.include_router(audit_router)


if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_config=None
    )
