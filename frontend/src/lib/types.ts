export type SupplierTier = 'TIER_1' | 'TIER_2' | 'TIER_3' | 'UNKNOWN'
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'SEVERE' | 'CRITICAL'
export type RiskCategory =
  | 'GEOPOLITICAL'
  | 'FINANCIAL'
  | 'ESG'
  | 'REGULATORY'
  | 'OPERATIONAL'
  | 'CYBER'
  | 'NATURAL_DISASTER'
  | 'SUPPLIER_VIABILITY'
export type WorkflowType =
  | 'AUTONOMOUS_DISCOVERY'
  | 'DEEP_DIVE_INVESTIGATION'
  | 'COMPLIANCE_CHECK'
  | 'ALTERNATIVE_SOURCING'

export interface Supplier {
  id: string
  name: string
  legal_name: string | null
  tier: SupplierTier
  country: string
  region: string | null
  industry: string | null
  website: string | null
  contact_email: string | null
  contact_phone: string | null
  risk_score: number
  last_assessed: string | null
  is_active: boolean
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface SupplierListResponse {
  suppliers: Supplier[]
  total: number
  limit: number
  offset: number
}

export interface SupplierCreateInput {
  name: string
  legal_name?: string
  tier?: SupplierTier
  country: string
  region?: string
  industry?: string
  website?: string
  contact_email?: string
  contact_phone?: string
}

export interface Metrics {
  total_suppliers: number
  active_workflows: number
  risk_alerts_24h: number
  avg_risk_score: number
  cost_last_30_days: number
  false_positive_rate: number
}

export interface AgentStatus {
  status: string
  capabilities: string[]
}

export type AgentStatusMap = Record<string, AgentStatus>

export interface RiskAlert {
  id: string
  supplier_id: string
  supplier_name: string
  category: string
  level: RiskLevel
  title: string
  description: string
  confidence: number
  impact_score: number
  likelihood_score: number
  detected_at: string
}

export interface AlertListResponse {
  alerts: RiskAlert[]
  total: number
}

export interface InvestigationSummary {
  workflow_id: string
  supplier_id: string | null
  supplier_name: string | null
  workflow_type: WorkflowType
  status: string
  query: string | null
  hitl_required: boolean
  hitl_status: string | null
  error: string | null
  step_count: number
  created_at: string
  updated_at: string
  completed_at: string | null
}

export interface InvestigationListResponse {
  investigations: InvestigationSummary[]
  total: number
  limit: number
  offset: number
}

export interface HitlPayload {
  supplier_name?: string
  recommendation?: string
  risk_factors?: { title: string; level: RiskLevel }[]
  [key: string]: unknown
}

export interface InvestigationStartInput {
  query: string
  supplier_id?: string
  supplier_name?: string
  workflow_type: WorkflowType
}

export interface InvestigationStartResponse {
  workflow_id: string
  status: string
  summary: string | null
  hitl_required: boolean
  hitl_payload: HitlPayload | null
  processing_time_seconds: number
}

export interface WorkflowEvent {
  workflow_id: string
  agent: string | null
  message: string
  status: string
  step: number
  hitl_required: boolean
  hitl_payload: HitlPayload | null
  summary?: string
  timestamp?: string
  type?: string
}

export interface RiskFactor {
  id: string
  supplier_id: string
  category: RiskCategory
  level: RiskLevel
  title: string
  description: string
  evidence_ids: string[]
  confidence: number
  impact_score: number
  likelihood_score: number
  detected_at: string
  acknowledged_at: string | null
  resolved_at: string | null
  metadata: Record<string, unknown>
}
