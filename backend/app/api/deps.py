"""
Shared FastAPI dependencies reading shared services from app.state.
"""
from fastapi import HTTPException, Request

from app.services.database import DatabaseService, get_database_service


def get_db() -> DatabaseService:
    return get_database_service()


def get_workflow_runner(request: Request):
    runner = getattr(request.app.state, "workflow_runner", None)
    if runner is None:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")
    return runner


def get_orchestrator(request: Request):
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return orchestrator
