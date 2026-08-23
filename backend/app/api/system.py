"""
System endpoints: health, metrics, public config, agent status.
"""
from fastapi import APIRouter, Depends, Request

from app.api.deps import get_db, get_orchestrator
from app.schemas import HealthCheckResponse, MetricsResponse
from app.services.config import get_config
from app.services.database import DatabaseService
from app.memory import get_memory_manager

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(request: Request):
    """Health check endpoint"""
    config = get_config()
    memory_manager = await get_memory_manager()
    return HealthCheckResponse(
        status="healthy",
        version=config.version,
        environment=config.environment,
        timestamp=__import__('datetime').datetime.utcnow(),
        services={
            "api": "healthy",
            "database": "healthy",
            **memory_manager.get_status(),
            "workflow": "healthy" if getattr(request.app.state, "workflow_runner", None) else "unavailable",
        }
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(db: DatabaseService = Depends(get_db)):
    """Get system metrics"""
    metrics = await db.get_dashboard_metrics()
    # Share of HITL escalations denied by a human reviewer.
    metrics["false_positive_rate"] = await db.get_false_positive_rate()
    return MetricsResponse(**metrics)


@router.get("/api/v1/agents/status")
async def get_agents_status(orch=Depends(get_orchestrator)):
    """Get status of all agents"""
    status = {}
    for role, agent in orch.agents.items():
        status[role.value.lower()] = {
            "status": "ready",
            "capabilities": await agent.get_capabilities()
        }
    return status


@router.get("/api/v1/config")
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
            "streaming_updates": True,
            "crewai_engine": bool((getattr(config, "crewai", {}) or {}).get("enabled")),
        }
    }


# Dev-only seed endpoint
@router.post("/api/v1/seed")
async def seed_data(db: DatabaseService = Depends(get_db)):
    """Generate 50 dummy suppliers for development"""
    config = get_config()
    if config.environment == "production":
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Not available in production")

    import random
    from faker import Faker
    fake = Faker()

    industries = ["Semiconductors", "Automotive", "Electronics", "Logistics",
                  "Chemicals", "Textiles", "Machinery", "Food & Beverage"]
    countries = ["US", "DE", "CN", "TW", "JP", "KR", "IN", "VN", "MX", "BR", "GB", "FR", "IT", "NL", "PL"]
    tiers = ["TIER_1", "TIER_2", "TIER_3"]

    created = 0
    for _ in range(50):
        name = f"{fake.company()} {fake.company_suffix()}"
        await db.create_supplier(
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
