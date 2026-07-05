'use client'

import { useState, useRef, useEffect } from 'react'
import Link from 'next/link'
import { Shield, Search, Send, Loader2, AlertTriangle, CheckCircle, Clock, XCircle, ChevronRight } from 'lucide-react'

interface WorkflowStep {
  step: number
  message: string
  status?: string
}

export default function InvestigationsPage() {
  const [query, setQuery] = useState('')
  const [supplierName, setSupplierName] = useState('')
  const [workflowType, setWorkflowType] = useState('DEEP_DIVE_INVESTIGATION')
  const [running, setRunning] = useState(false)
  const [workflowId, setWorkflowId] = useState<string | null>(null)
  const [steps, setSteps] = useState<WorkflowStep[]>([])
  const [hitlRequired, setHitlRequired] = useState(false)
  const [hitlPayload, setHitlPayload] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    return () => { esRef.current?.close() }
  }, [])

  const startWorkflow = async () => {
    if (!query && !supplierName) return
    setRunning(true)
    setError(null)
    setSteps([])
    setHitlRequired(false)

    try {
      const res = await fetch('http://localhost:8000/api/v1/investigations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, supplier_name: supplierName || undefined, workflow_type: workflowType })
      })
      const data = await res.json()
      setWorkflowId(data.workflow_id)

      if (data.hitl_required) {
        setHitlRequired(true)
        setHitlPayload(data.hitl_payload)
      }

      // Connect to SSE stream
      const es = new EventSource(`http://localhost:8000/api/v1/investigations/${data.workflow_id}/stream`)
      esRef.current = es
      es.onmessage = (event) => {
        const stepData = JSON.parse(event.data)
        setSteps(prev => [...prev, stepData])
        if (stepData.status === 'COMPLETED') { setRunning(false); es.close() }
        if (stepData.hitl_required) { setHitlRequired(true); setHitlPayload(stepData.hitl_payload) }
      }
      es.onerror = () => { setError('Stream connection lost'); setRunning(false); es.close() }
    } catch (err: any) {
      setError(err.message)
      setRunning(false)
    }
  }

  const submitHitl = async (action: string) => {
    if (!workflowId) return
    try {
      const res = await fetch(`http://localhost:8000/api/v1/investigations/${workflowId}/hitl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workflow_id: workflowId, action })
      })
      if (res.ok) setHitlRequired(false)
    } catch (err: any) { setError(err.message) }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-2">
              <Shield className="w-6 h-6 text-primary-600" />
              <span className="font-bold text-lg text-gray-900">SentinelChain</span>
            </Link>
            <nav className="flex items-center gap-1">
              <Link href="/" className="px-3 py-2 rounded-lg text-sm text-gray-600 hover:text-gray-900">Dashboard</Link>
              <Link href="/suppliers" className="px-3 py-2 rounded-lg text-sm text-gray-600 hover:text-gray-900">Suppliers</Link>
              <Link href="/investigations" className="px-3 py-2 rounded-lg text-sm font-medium bg-primary-50 text-primary-700">Investigations</Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Supply Chain Investigation</h1>

        {/* Investigation Form */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-8">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Supplier Name</label>
              <input type="text" value={supplierName} onChange={e => setSupplierName(e.target.value)}
                placeholder="e.g., TechCorp Taiwan" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Investigation Query</label>
              <textarea value={query} onChange={e => setQuery(e.target.value)} rows={2}
                placeholder="e.g., Investigate the financial stability of this supplier over the last 6 months"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-none" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Workflow Type</label>
              <select value={workflowType} onChange={e => setWorkflowType(e.target.value)} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white">
                <option value="DEEP_DIVE_INVESTIGATION">Deep-Dive Investigation</option>
                <option value="AUTONOMOUS_DISCOVERY">Autonomous Discovery</option>
                <option value="COMPLIANCE_CHECK">Compliance Check</option>
                <option value="ALTERNATIVE_SOURCING">Alternative Sourcing</option>
              </select>
            </div>
            <button onClick={startWorkflow} disabled={running || (!query && !supplierName)}
              className="inline-flex items-center gap-2 bg-primary-600 text-white px-6 py-2.5 rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              {running ? 'Running...' : 'Start Investigation'}
            </button>
          </div>
        </div>

        {/* HITL Panel */}
        {hitlRequired && hitlPayload && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 mb-8">
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              <h3 className="font-semibold text-red-900">Human Approval Required</h3>
            </div>
            <div className="bg-white rounded-lg border border-red-100 p-4 mb-4">
              <div className="font-medium text-gray-900 mb-2">{hitlPayload.supplier_name}</div>
              {hitlPayload.risk_factors?.map((rf: any, i: number) => (
                <div key={i} className="text-sm text-gray-600 ml-4">- {rf.title} [{rf.level}]</div>
              ))}
              <div className="mt-2 text-sm font-medium text-red-700">Recommendation: {hitlPayload.recommendation}</div>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => submitHitl('APPROVE')} className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 text-sm">
                <CheckCircle className="w-4 h-4 inline mr-1" /> Approve
              </button>
              <button onClick={() => submitHitl('DENY')} className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 text-sm">
                <XCircle className="w-4 h-4 inline mr-1" /> Deny
              </button>
              <button onClick={() => submitHitl('ESCALATE')} className="bg-gray-600 text-white px-4 py-2 rounded-lg hover:bg-gray-700 text-sm">
                <ChevronRight className="w-4 h-4 inline mr-1" /> Escalate
              </button>
            </div>
          </div>
        )}

        {/* Workflow Timeline */}
        {steps.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 p-6 mb-8">
            <h3 className="font-semibold text-gray-900 mb-4">Agent Workflow Timeline</h3>
            <div className="space-y-3">
              {steps.map((step, i) => (
                <div key={i} className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center">
                    <span className="text-xs font-medium text-primary-700">{step.step}</span>
                  </div>
                  <div>
                    <div className="text-sm text-gray-900">{step.message}</div>
                    {step.status === 'COMPLETED' && (
                      <div className="flex items-center gap-1 mt-1 text-xs text-green-600">
                        <CheckCircle className="w-3 h-3" /> Complete
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {running && (
              <div className="flex items-center gap-2 mt-4 text-sm text-gray-500">
                <Loader2 className="w-4 h-4 animate-spin" />
                Agents working...
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700 text-sm">{error}</div>
        )}
      </main>
    </div>
  )
}