"""
Core data models for SentinelChain
"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from uuid import UUID, uuid4


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    SEVERE = "SEVERE"
    CRITICAL = "CRITICAL"


class RiskCategory(str, Enum):
    GEOPOLITICAL = "GEOPOLITICAL"
    FINANCIAL = "FINANCIAL"
    ESG = "ESG"
    REGULATORY = "REGULATORY"
    OPERATIONAL = "OPERATIONAL"
    CYBER = "CYBER"
    NATURAL_DISASTER = "NATURAL_DISASTER"
    SUPPLIER_VIABILITY = "SUPPLIER_VIABILITY"


class SupplierTier(str, Enum):
    TIER_1 = "TIER_1"
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"
    UNKNOWN = "UNKNOWN"


class WorkflowType(str, Enum):
    AUTONOMOUS_DISCOVERY = "AUTONOMOUS_DISCOVERY"
    DEEP_DIVE_INVESTIGATION = "DEEP_DIVE_INVESTIGATION"
    COMPLIANCE_CHECK = "COMPLIANCE_CHECK"
    ALTERNATIVE_SOURCING = "ALTERNATIVE_SOURCING"


class AgentRole(str, Enum):
    SCOUT = "SCOUT"
    ANALYST = "ANALYST"
    AUDITOR = "AUDITOR"
    MITIGATOR = "MITIGATOR"
    ORCHESTRATOR = "ORCHESTRATOR"


class EvidenceType(str, Enum):
    NEWS_ARTICLE = "NEWS_ARTICLE"
    FINANCIAL_REPORT = "FINANCIAL_REPORT"
    SANCTIONS_LIST = "SANCTIONS_LIST"
    SATELLITE_IMAGERY = "SATELLITE_IMAGERY"
    GOVERNMENT_REGISTRY = "GOVERNMENT_REGISTRY"
    SUPPLIER_COMMUNICATION = "SUPPLIER_COMMUNICATION"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    INTERNAL_DOCUMENT = "INTERNAL_DOCUMENT"


class HITLStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    ESCALATED = "ESCALATED"
    TIMEOUT = "TIMEOUT"


class Supplier(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    name: str
    legal_name: Optional[str] = None
    tier: SupplierTier = SupplierTier.UNKNOWN
    country: str
    region: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    last_assessed: Optional[datetime] = None
    is_active: bool = Field(default=True)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Evidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    supplier_id: UUID
    type: EvidenceType
    source: str
    title: str
    content: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    credibility_score: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RiskFactor(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    supplier_id: UUID
    category: RiskCategory
    level: RiskLevel
    title: str
    description: str
    evidence_ids: List[UUID] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    impact_score: float = Field(default=0.0, ge=0.0, le=100.0)
    likelihood_score: float = Field(default=0.0, ge=0.0, le=100.0)
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MitigationAction(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    risk_factor_id: UUID
    title: str
    description: str
    action_type: str
    estimated_cost: Optional[float] = None
    estimated_timeline_days: Optional[int] = None
    priority: int = Field(default=1, ge=1, le=5)
    status: str = Field(default="PROPOSED")
    assigned_to: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AlternativeSupplier(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    original_supplier_id: UUID
    name: str
    country: str
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    cost_difference_pct: Optional[float] = None
    lead_time_days: Optional[int] = None
    quality_rating: Optional[float] = None
    certifications: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowState(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)
    
    workflow_id: UUID = Field(default_factory=uuid4)
    workflow_type: WorkflowType
    supplier_id: Optional[UUID] = None
    current_agent: Optional[AgentRole] = None
    status: str = Field(default="RUNNING")
    state_data: Dict[str, Any] = Field(default_factory=dict)
    evidence_collected: List[UUID] = Field(default_factory=list)
    risk_factors_identified: List[UUID] = Field(default_factory=list)
    mitigation_actions: List[UUID] = Field(default_factory=list)
    hitl_required: bool = Field(default=False)
    hitl_status: Optional[HITLStatus] = None
    hitl_payload: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    step_count: int = Field(default=0)
    max_steps: int = Field(default=10)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class AgentMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    from_agent: AgentRole
    to_agent: Optional[AgentRole] = None
    message_type: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    query: str
    workflow_type: WorkflowType = WorkflowType.DEEP_DIVE_INVESTIGATION
    priority: int = Field(default=1, ge=1, le=5)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InvestigationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    workflow_id: UUID
    status: str
    summary: Optional[str] = None
    risk_factors: List[RiskFactor] = Field(default_factory=list)
    mitigation_actions: List[MitigationAction] = Field(default_factory=list)
    alternative_suppliers: List[AlternativeSupplier] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    hitl_required: bool = False
    hitl_payload: Optional[Dict[str, Any]] = None
    processing_time_seconds: float = 0.0