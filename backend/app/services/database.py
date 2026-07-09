"""
Database service for SentinelChain - SQLAlchemy async models and session management
"""
from datetime import datetime
from typing import Optional, AsyncGenerator
from uuid import UUID, uuid4

from sqlalchemy import (
    String, Text, Float, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum,
    Index, UniqueConstraint
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine, AsyncEngine
)
from sqlalchemy.pool import NullPool

from app.config import get_config


class Base(DeclarativeBase):
    pass


class SupplierDB(Base):
    __tablename__ = "suppliers"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    legal_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tier: Mapped[str] = mapped_column(
        SQLEnum("TIER_1", "TIER_2", "TIER_3", "UNKNOWN", name="supplier_tier"),
        default="UNKNOWN", nullable=False
    )
    country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    website: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_assessed: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    supplier_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    investigations: Mapped[list["InvestigationDB"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")
    risk_factors: Mapped[list["RiskFactorDB"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")
    evidence: Mapped[list["EvidenceDB"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_supplier_country_industry", "country", "industry"),
        Index("ix_supplier_tier_active", "tier", "is_active"),
    )


class InvestigationDB(Base):
    __tablename__ = "investigations"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(unique=True, nullable=False, index=True)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_type: Mapped[str] = mapped_column(
        SQLEnum("AUTONOMOUS_DISCOVERY", "DEEP_DIVE_INVESTIGATION", "COMPLIANCE_CHECK", "ALTERNATIVE_SOURCING", name="workflow_type"),
        nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False, index=True)
    query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    investigation_result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    hitl_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hitl_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hitl_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    max_steps: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    supplier: Mapped["SupplierDB"] = relationship(back_populates="investigations")
    risk_factors: Mapped[list["RiskFactorDB"]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    mitigation_actions: Mapped[list["MitigationActionDB"]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    alternative_suppliers: Mapped[list["AlternativeSupplierDB"]] = relationship(back_populates="investigation", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_investigation_supplier_status", "supplier_id", "status"),
    )


class EvidenceDB(Base):
    __tablename__ = "evidence"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    investigation_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(
        SQLEnum(
            "NEWS_ARTICLE", "FINANCIAL_REPORT", "SANCTIONS_LIST", "SATELLITE_IMAGERY",
            "GOVERNMENT_REGISTRY", "SUPPLIER_COMMUNICATION", "SOCIAL_MEDIA", "INTERNAL_DOCUMENT",
            name="evidence_type"
        ),
        nullable=False
    )
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    credibility_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    evidence_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    # Relationships
    supplier: Mapped["SupplierDB"] = relationship(back_populates="evidence")
    investigation: Mapped[Optional["InvestigationDB"]] = relationship()
    
    __table_args__ = (
        Index("ix_evidence_supplier_type", "supplier_id", "type"),
        Index("ix_evidence_published_at", "published_at"),
    )


class RiskFactorDB(Base):
    __tablename__ = "risk_factors"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    investigation_id: Mapped[UUID] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(
        SQLEnum(
            "GEOPOLITICAL", "FINANCIAL", "ESG", "REGULATORY", "OPERATIONAL",
            "CYBER", "NATURAL_DISASTER", "SUPPLIER_VIABILITY",
            name="risk_category"
        ),
        nullable=False
    )
    level: Mapped[str] = mapped_column(
        SQLEnum("LOW", "MEDIUM", "HIGH", "SEVERE", "CRITICAL", name="risk_level"),
        nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    impact_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    likelihood_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    risk_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    # Relationships
    supplier: Mapped["SupplierDB"] = relationship(back_populates="risk_factors")
    investigation: Mapped["InvestigationDB"] = relationship(back_populates="risk_factors")
    mitigation_actions: Mapped[list["MitigationActionDB"]] = relationship(back_populates="risk_factor", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_risk_factor_supplier_category", "supplier_id", "category"),
        Index("ix_risk_factor_level", "level"),
    )


class MitigationActionDB(Base):
    __tablename__ = "mitigation_actions"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    risk_factor_id: Mapped[UUID] = mapped_column(ForeignKey("risk_factors.id", ondelete="CASCADE"), nullable=False, index=True)
    investigation_id: Mapped[UUID] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    estimated_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_timeline_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PROPOSED", nullable=False)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    action_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    # Relationships
    risk_factor: Mapped["RiskFactorDB"] = relationship(back_populates="mitigation_actions")
    investigation: Mapped["InvestigationDB"] = relationship(back_populates="mitigation_actions")


class AlternativeSupplierDB(Base):
    __tablename__ = "alternative_suppliers"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    original_supplier_id: Mapped[UUID] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    investigation_id: Mapped[UUID] = mapped_column(ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cost_difference_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    quality_rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    certifications: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    alt_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    
    # Relationships
    investigation: Mapped["InvestigationDB"] = relationship(back_populates="alternative_suppliers")


class AgentMessageDB(Base):
    __tablename__ = "agent_messages"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    from_agent: Mapped[str] = mapped_column(
        SQLEnum("SCOUT", "ANALYST", "AUDITOR", "MITIGATOR", "ORCHESTRATOR", name="agent_role"),
        nullable=False
    )
    to_agent: Mapped[Optional[str]] = mapped_column(
        SQLEnum("SCOUT", "ANALYST", "AUDITOR", "MITIGATOR", "ORCHESTRATOR", name="agent_role_to"),
        nullable=True
    )
    message_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_agent_message_workflow_timestamp", "workflow_id", "timestamp"),
    )


class CostTrackingDB(Base):
    __tablename__ = "cost_tracking"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workflow_id: Mapped[Optional[UUID]] = mapped_column(index=True, nullable=True)
    supplier_id: Mapped[Optional[UUID]] = mapped_column(index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    cost_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    __table_args__ = (
        Index("ix_cost_workflow_created", "workflow_id", "created_at"),
        Index("ix_cost_supplier_created", "supplier_id", "created_at"),
    )


# Database Engine and Session Management
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_database_url() -> str:
    """Get database URL from config"""
    config = get_config()
    return config.database.url


async def init_database() -> None:
    """Initialize database engine and create tables"""
    global _engine, _session_factory
    
    database_url = get_database_url()
    
    # Configure engine based on database type
    if database_url.startswith("sqlite"):
        _engine = create_async_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
    else:
        _engine = create_async_engine(
            database_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
    
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # Create tables
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_database() -> None:
    """Close database engine"""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get session factory"""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session (for FastAPI dependency injection)"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


class DatabaseService:
    """High-level database operations"""
    
    def __init__(self):
        self._factory = get_session_factory()
    
    async def create_supplier(self, **kwargs) -> SupplierDB:
        async with self._factory() as session:
            supplier = SupplierDB(**kwargs)
            session.add(supplier)
            await session.commit()
            await session.refresh(supplier)
            return supplier
    
    async def get_supplier(self, supplier_id: UUID) -> Optional[SupplierDB]:
        async with self._factory() as session:
            return await session.get(SupplierDB, supplier_id)
    
    async def get_supplier_by_name(self, name: str) -> Optional[SupplierDB]:
        from sqlalchemy import select
        async with self._factory() as session:
            result = await session.execute(
                select(SupplierDB).where(SupplierDB.name == name)
            )
            return result.scalar_one_or_none()
    
    async def list_suppliers(
        self,
        tier: Optional[str] = None,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        risk_level: Optional[str] = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SupplierDB], int]:
        from sqlalchemy import select, func, case
        async with self._factory() as session:
            query = select(SupplierDB).where(SupplierDB.is_active == is_active)
            
            if tier:
                query = query.where(SupplierDB.tier == tier)
            if country:
                query = query.where(SupplierDB.country == country)
            if industry:
                query = query.where(SupplierDB.industry == industry)
            
            # Count total
            count_query = select(func.count()).select_from(query.subquery())
            total = await session.scalar(count_query) or 0
            
            # Apply pagination
            query = query.order_by(SupplierDB.updated_at.desc()).limit(limit).offset(offset)
            result = await session.execute(query)
            suppliers = list(result.scalars().all())
            
            return suppliers, total
    
    async def update_supplier(self, supplier_id: UUID, **kwargs) -> Optional[SupplierDB]:
        async with self._factory() as session:
            supplier = await session.get(SupplierDB, supplier_id)
            if not supplier:
                return None
            
            for key, value in kwargs.items():
                if hasattr(supplier, key):
                    setattr(supplier, key, value)
            
            supplier.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(supplier)
            return supplier
    
    async def delete_supplier(self, supplier_id: UUID) -> bool:
        async with self._factory() as session:
            supplier = await session.get(SupplierDB, supplier_id)
            if not supplier:
                return False
            supplier.is_active = False
            supplier.updated_at = datetime.utcnow()
            await session.commit()
            return True
    
    # Investigation operations
    async def create_investigation(self, **kwargs) -> InvestigationDB:
        async with self._factory() as session:
            investigation = InvestigationDB(**kwargs)
            session.add(investigation)
            await session.commit()
            await session.refresh(investigation)
            return investigation
    
    async def get_investigation(self, workflow_id: UUID) -> Optional[InvestigationDB]:
        from sqlalchemy import select
        async with self._factory() as session:
            result = await session.execute(
                select(InvestigationDB).where(InvestigationDB.workflow_id == workflow_id)
            )
            return result.scalar_one_or_none()
    
    async def update_investigation(self, workflow_id: UUID, **kwargs) -> Optional[InvestigationDB]:
        async with self._factory() as session:
            investigation = await self.get_investigation(workflow_id)
            if not investigation:
                return None
            
            for key, value in kwargs.items():
                if hasattr(investigation, key):
                    setattr(investigation, key, value)
            
            investigation.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(investigation)
            return investigation
    
    async def add_evidence(self, **kwargs) -> EvidenceDB:
        async with self._factory() as session:
            evidence = EvidenceDB(**kwargs)
            session.add(evidence)
            await session.commit()
            await session.refresh(evidence)
            return evidence
    
    async def add_risk_factor(self, **kwargs) -> RiskFactorDB:
        async with self._factory() as session:
            risk_factor = RiskFactorDB(**kwargs)
            session.add(risk_factor)
            await session.commit()
            await session.refresh(risk_factor)
            return risk_factor
    
    async def add_mitigation_action(self, **kwargs) -> MitigationActionDB:
        async with self._factory() as session:
            action = MitigationActionDB(**kwargs)
            session.add(action)
            await session.commit()
            await session.refresh(action)
            return action
    
    async def add_alternative_supplier(self, **kwargs) -> AlternativeSupplierDB:
        async with self._factory() as session:
            alt = AlternativeSupplierDB(**kwargs)
            session.add(alt)
            await session.commit()
            await session.refresh(alt)
            return alt
    
    async def track_cost(self, **kwargs) -> CostTrackingDB:
        async with self._factory() as session:
            cost = CostTrackingDB(**kwargs)
            session.add(cost)
            await session.commit()
            await session.refresh(cost)
            return cost
    
    async def get_investigations_by_supplier(self, supplier_id: UUID) -> list[InvestigationDB]:
        from sqlalchemy import select
        async with self._factory() as session:
            result = await session.execute(
                select(InvestigationDB)
                .where(InvestigationDB.supplier_id == supplier_id)
                .order_by(InvestigationDB.created_at.desc())
            )
            return list(result.scalars().all())


# Global service instance
_database_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
    return _database_service