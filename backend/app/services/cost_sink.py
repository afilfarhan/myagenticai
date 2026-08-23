"""
Cost tracking sink - persists LLM usage reported by the gateway to the
CostTrackingDB table so budget metrics (`/metrics` cost_last_30_days) and the
per-supplier cost target reflect reality.
"""
from typing import Any, Callable, Dict, Optional
from uuid import UUID

import structlog

from app.services.database import get_database_service

logger = structlog.get_logger(__name__)


async def db_cost_sink(
    *,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist one LLM usage record. Registered via
    ``LLMGateway.register_cost_callback`` at application startup."""
    meta = metadata or {}
    workflow_id = _as_uuid(meta.get("workflow_id"))
    supplier_id = _as_uuid(meta.get("supplier_id"))

    try:
        await get_database_service().track_cost(
            provider=provider,
            model=model,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            cost_usd=float(cost_usd or 0.0),
            operation=str(meta.get("operation", "llm.complete")),
            workflow_id=workflow_id,
            supplier_id=supplier_id,
        )
    except Exception as exc:
        logger.warning("Failed to persist cost record",
                       model=model, provider=provider, error=str(exc))


def _as_uuid(value: Any) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(str(value))
    except (ValueError, AttributeError):
        return None


def register_cost_sink(gateway) -> Callable:
    """Attach :func:`db_cost_sink` to a gateway instance (returns the sink)."""
    gateway.register_cost_callback(db_cost_sink)
    return db_cost_sink
