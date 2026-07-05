const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_URL}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`)
  if (res.status === 204) return undefined as T
  return res.json()
}

// Health
export const healthCheck = () => request<{ status: string; version: string }>('/health')
export const getMetrics = () => request<Record<string, unknown>>('/metrics')
export const getAgentsStatus = () => request<Record<string, unknown>>('/api/v1/agents/status')
export const getConfig = () => request<Record<string, unknown>>('/api/v1/config')

// Suppliers
export const listSuppliers = (params?: Record<string, unknown>) => {
  const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : ''
  return request<{ suppliers: any[]; total: number }>(`/api/v1/suppliers${qs}`)
}
export const getSupplier = (id: string) => request<any>(`/api/v1/suppliers/${id}`)
export const createSupplier = (data: any) => request<any>('/api/v1/suppliers', { method: 'POST', body: JSON.stringify(data) })
export const updateSupplier = (id: string, data: any) => request<any>(`/api/v1/suppliers/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
export const deleteSupplier = (id: string) => request<void>(`/api/v1/suppliers/${id}`, { method: 'DELETE' })

// Investigations
export const startInvestigation = (data: any) => request<any>('/api/v1/investigations', { method: 'POST', body: JSON.stringify(data) })
export const getWorkflowStatus = (id: string) => request<any>(`/api/v1/investigations/${id}`)
export const submitHitlResponse = (id: string, data: any) => request<any>(`/api/v1/investigations/${id}/hitl`, { method: 'POST', body: JSON.stringify(data) })

// SSE Streaming
export function streamWorkflowUpdates(workflowId: string, onMessage: (data: any) => void, onError?: (err: Event) => void, onComplete?: () => void): EventSource {
  const url = `${API_URL}/api/v1/investigations/${workflowId}/stream`
  const es = new EventSource(url)
  es.onmessage = (event) => {
    try { onMessage(JSON.parse(event.data)) } catch { onMessage(event.data) }
  }
  es.onerror = (err) => {
    onError?.(err)
    es.close()
  }
  es.addEventListener('done', () => { onComplete?.(); es.close() })
  return es
}