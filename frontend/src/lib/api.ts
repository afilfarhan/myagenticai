import axios, { type AxiosRequestConfig } from 'axios'
import type {
  AgentStatusMap,
  AlertListResponse,
  InvestigationListResponse,
  InvestigationStartInput,
  InvestigationStartResponse,
  Metrics,
  RiskFactor,
  Supplier,
  SupplierCreateInput,
  SupplierListResponse,
  WorkflowEvent,
} from './types'

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = window.localStorage.getItem('sc_access_token')
    if (token) config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export function getApiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    return error.message
  }
  return error instanceof Error ? error.message : 'Unknown error'
}

async function request<T>(path: string, options?: AxiosRequestConfig): Promise<T> {
  try {
    const { data } = await client.request<T>({ url: path, ...options })
    return data
  } catch (error) {
    throw new Error(getApiErrorMessage(error))
  }
}

// Health
export const healthCheck = () => request<{ status: string; version: string }>('/health')
export const getMetrics = () => request<Metrics>('/metrics')
export const getAgentsStatus = () => request<AgentStatusMap>('/api/v1/agents/status')
export const getConfig = () => request<Record<string, unknown>>('/api/v1/config')

// Suppliers
export function listSuppliers(params?: {
  query?: string
  tier?: string
  country?: string
  industry?: string
  is_active?: boolean
  limit?: number
  offset?: number
}) {
  return request<SupplierListResponse>('/api/v1/suppliers', { params })
}
export const getSupplier = (id: string) => request<Supplier>(`/api/v1/suppliers/${id}`)
export const createSupplier = (data: SupplierCreateInput) =>
  request<Supplier>('/api/v1/suppliers', { method: 'POST', data })
export const updateSupplier = (id: string, data: Partial<SupplierCreateInput>) =>
  request<Supplier>(`/api/v1/suppliers/${id}`, { method: 'PATCH', data })
export const deleteSupplier = (id: string) =>
  request<void>(`/api/v1/suppliers/${id}`, { method: 'DELETE' })

// Risk factors
export const listSupplierRiskFactors = (supplierId: string) =>
  request<RiskFactor[]>(`/api/v1/suppliers/${supplierId}/risk-factors`)

// Investigations
export const startInvestigation = (data: InvestigationStartInput) =>
  request<InvestigationStartResponse>('/api/v1/investigations', { method: 'POST', data })
export const listInvestigations = (params?: {
  supplier_id?: string
  status?: string
  workflow_type?: string
  limit?: number
  offset?: number
}) => request<InvestigationListResponse>('/api/v1/investigations', { params })
export const submitHitlResponse = (
  workflowId: string,
  data: { workflow_id: string; action: 'APPROVE' | 'DENY' | 'ESCALATE'; comment?: string },
) => request<unknown>(`/api/v1/investigations/${workflowId}/hitl`, { method: 'POST', data })

// Alerts
export function listRecentAlerts(params?: { hours?: number; level?: string; limit?: number }) {
  return request<AlertListResponse>('/api/v1/alerts/recent', { params })
}

// SSE Streaming
export function streamWorkflowUpdates(
  workflowId: string,
  onMessage: (event: WorkflowEvent | { type: 'heartbeat' }) => void,
  onError?: (err: Event) => void,
): EventSource {
  const url = `${API_BASE_URL}/api/v1/investigations/${workflowId}/stream`
  const es = new EventSource(url)
  es.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data))
    } catch {
      // Ignore malformed frames
    }
  }
  es.onerror = (err) => {
    onError?.(err)
    es.close()
  }
  return es
}
