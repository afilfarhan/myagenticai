"""
API Schemas for SentinelChain
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID

from app.models import (
    Supplier, Evidence, RiskFactor, MitigationAction,
    AlternativeSupplier, WorkflowState, AgentMessage,
    InvestigationRequest, InvestigationResponse,
    SupplierTier, RiskLevel, RiskCategory, WorkflowType, AgentRole
)


# Request Schemas
class SupplierCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    legal_name: Optional[str] = None
    tier: SupplierTier = SupplierTier.UNKNOWN
    country: str = Field(..., min_length=2, max_length=2)
    region: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    tier: Optional[SupplierTier] = None
    country: Optional[str] = None
    region: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    is_active: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None


class InvestigationRequestSchema(BaseModel):
    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    query: str = Field(..., min_length=10)
    workflow_type: WorkflowType = WorkflowType.DEEP_DIVE_INVESTIGATION
    priority: int = Field(default=1, ge=1, le=5)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HITLResponseSchema(BaseModel):
    workflow_id: UUID
    action: str = Field(..., pattern="^(APPROVE|DENY|ESCALATE)$")
    comment: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SupplierSearchSchema(BaseModel):
    query: Optional[str] = None
    tier: Optional[SupplierTier] = None
    country: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    is_active: Optional[bool] = True
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


# Response Schemas
class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    legal_name: Optional[str]
    tier: SupplierTier
    country: str
    region: Optional[str]
    industry: Optional[str]
    website: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    risk_score: float
    last_assessed: Optional[datetime]
    is_active: bool
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SupplierListResponse(BaseModel):
    suppliers: List[SupplierResponse]
    total: int
    limit: int
    offset: int


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    supplier_id: UUID
    type: str
    source: str
    title: str
    content: str
    url: Optional[str]
    published_at: Optional[datetime]
    retrieved_at: datetime
    credibility_score: float
    relevance_score: float
    metadata: Dict[str, Any]


class RiskFactorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    supplier_id: UUID
    category: RiskCategory
    level: RiskLevel
    title: str
    description: str
    evidence_ids: List[UUID]
    confidence: float
    impact_score: float
    likelihood_score: float
    detected_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    metadata: Dict[str, Any]


class MitigationActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    risk_factor_id: UUID
    title: str
    description: str
    action_type: str
    estimated_cost: Optional[float]
    estimated_timeline_days: Optional[int]
    priority: int
    status: str
    assigned_to: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    metadata: Dict[str, Any]


class AlternativeSupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    original_supplier_id: UUID
    name: str
    country: str
    risk_score: float
    cost_difference_pct: Optional[float]
    lead_time_days: Optional[int]
    quality_rating: Optional[float]
    certifications: List[str]
    metadata: Dict[str, Any]


class WorkflowStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    workflow_id: UUID
    workflow_type: WorkflowType
    supplier_id: Optional[UUID]
    current_agent: Optional[AgentRole]
    status: str
    state_data: Dict[str, Any]
    evidence_collected: List[UUID]
    risk_factors_identified: List[UUID]
    mitigation_actions: List[UUID]
    hitl_required: bool
    hitl_status: Optional[str]
    hitl_payload: Optional[Dict[str, Any]]
    error: Optional[str]
    step_count: int
    max_steps: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


class InvestigationResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    workflow_id: UUID
    status: str
    summary: Optional[str]
    risk_factors: List[RiskFactorResponse]
    mitigation_actions: List[MitigationActionResponse]
    alternative_suppliers: List[AlternativeSupplierResponse]
    evidence: List[EvidenceResponse]
    hitl_required: bool
    hitl_payload: Optional[Dict[str, Any]]
    processing_time_seconds: float


class HealthCheckResponse(BaseModel):
    status: str
    version: str
    environment: str
    timestamp: datetime
    services: Dict[str, str]


class MetricsResponse(BaseModel):
    total_suppliers: int
    active_workflows: int
    risk_alerts_24h: int
    avg_risk_score: float
    cost_last_30_days: float
    false_positive_rate: float