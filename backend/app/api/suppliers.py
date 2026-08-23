"""
Supplier management endpoints: CRUD, seed, risk factors.
"""
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.api.deps import get_db
from app.memory import get_memory_manager
from app.models import (
    Supplier, SupplierTier, RiskLevel, RiskCategory,
)
from app.schemas import (
    SupplierCreate, SupplierUpdate, SupplierResponse, SupplierListResponse,
    RiskFactorResponse,
)
from app.services.database import DatabaseService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/suppliers", tags=["Suppliers"])


async def save_supplier_to_vector_store(supplier: Supplier):
    """Background task to save supplier to vector store"""
    try:
        memory_manager = await get_memory_manager()
        await memory_manager.save_supplier_profile(supplier)
    except Exception as e:
        logger.error("Failed to save supplier to vector store", supplier_id=str(supplier.id), error=str(e))


def _to_domain(db_supplier) -> Supplier:
    return Supplier(
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


@router.post("", response_model=SupplierResponse, status_code=201)
async def create_supplier(
    supplier: SupplierCreate,
    background_tasks: BackgroundTasks,
    db: DatabaseService = Depends(get_db)
):
    """Create a new supplier"""
    existing = await db.get_supplier_by_name(supplier.name)
    if existing:
        raise HTTPException(status_code=409, detail="Supplier already exists")

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

    created = _to_domain(db_supplier)
    background_tasks.add_task(save_supplier_to_vector_store, created)

    logger.info("Supplier created", supplier_id=str(created.id), name=supplier.name)
    return SupplierResponse(**created.model_dump())


@router.get("", response_model=SupplierListResponse)
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

    suppliers = [_to_domain(s) for s in db_suppliers]

    return SupplierListResponse(
        suppliers=[SupplierResponse(**s.model_dump()) for s in suppliers],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(supplier_id: UUID, db: DatabaseService = Depends(get_db)):
    """Get supplier by ID"""
    db_supplier = await db.get_supplier(supplier_id)
    if not db_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return SupplierResponse(**_to_domain(db_supplier).model_dump())


@router.get("/{supplier_id}/risk-factors", response_model=List[RiskFactorResponse])
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


@router.patch("/{supplier_id}", response_model=SupplierResponse)
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

    supplier = _to_domain(db_supplier)
    background_tasks.add_task(save_supplier_to_vector_store, supplier)

    return SupplierResponse(**supplier.model_dump())


@router.delete("/{supplier_id}", status_code=204)
async def delete_supplier(supplier_id: UUID, db: DatabaseService = Depends(get_db)):
    """Delete supplier (soft delete)"""
    result = await db.delete_supplier(supplier_id)
    if not result:
        raise HTTPException(status_code=404, detail="Supplier not found")

    memory_manager = await get_memory_manager()
    await memory_manager.vector_store.delete_supplier(supplier_id)
