'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import {
  AlertTriangle, CheckCircle, ChevronRight, Loader2, Search, XCircle,
} from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { useWorkflowStore } from '@/stores/workflow'
import type { WorkflowType } from '@/lib/types'
import { cn } from '@/lib/utils'

const workflowTypes: { value: WorkflowType; label: string }[] = [
  { value: 'DEEP_DIVE_INVESTIGATION', label: 'Deep-Dive Investigation' },
  { value: 'AUTONOMOUS_DISCOVERY', label: 'Autonomous Discovery' },
  { value: 'COMPLIANCE_CHECK', label: 'Compliance Check' },
  { value: 'ALTERNATIVE_SOURCING', label: 'Alternative Sourcing' },
]

export default function InvestigationsPage() {
  const searchParams = useSearchParams()
  const {
    phase, steps, hitlPayload, summary, error,
    start, resumeHitl, reset,
  } = useWorkflowStore()

  const [supplierName, setSupplierName] = useState('')
  const [query, setQuery] = useState('')
  const [workflowType, setWorkflowType] = useState<WorkflowType>('DEEP_DIVE_INVESTIGATION')

  const running = phase === 'starting' || phase === 'streaming'

  // Prefill from /investigations?supplier={id}&name={name}
  useEffect(() => {
    const name = searchParams.get('name')
    if (name) setSupplierName(name)
  }, [searchParams])

  const startWorkflow = () => {
    if (!query.trim() && !supplierName.trim()) return
    start({
      query: query.trim() || `Investigate ${supplierName.trim()}`,
      supplierName: supplierName.trim(),
      workflowType,
    })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <AppHeader active="/investigations" />

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Supply Chain Investigation</h1>
          {(phase === 'completed' || phase === 'failed') && (
            <button onClick={reset} className="text-sm text-primary-600 hover:text-primary-700">
              New investigation
            </button>
          )}
        </div>

        {/* Investigation Form */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-8">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Supplier Name</label>
              <input
                type="text"
                value={supplierName}
                onChange={(e) => setSupplierName(e.target.value)}
                placeholder="e.g., TechCorp Taiwan"
                disabled={running}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm disabled:bg-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Investigation Query</label>
              <textarea
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                rows={2}
                placeholder="e.g., Investigate the financial stability of this supplier over the last 6 months"
                disabled={running}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-none disabled:bg-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Workflow Type</label>
              <select
                value={workflowType}
                onChange={(e) => setWorkflowType(e.target.value as WorkflowType)}
                disabled={running}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white disabled:bg-gray-100"
              >
                {workflowTypes.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <button
              onClick={startWorkflow}
              disabled={running || (!query && !supplierName)}
              className="inline-flex items-center gap-2 bg-primary-600 text-white px-6 py-2.5 rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              {running ? 'Running...' : 'Start Investigation'}
            </button>
          </div>
        </div>

        {/* HITL Panel */}
        {phase === 'hitl_required' && hitlPayload && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 mb-8">
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle className="w-5 h-5 text-red-600" />
              <h3 className="font-semibold text-red-900">Human Approval Required</h3>
            </div>
            <div className="bg-white rounded-lg border border-red-100 p-4 mb-4">
              {hitlPayload.supplier_name && (
                <div className="font-medium text-gray-900 mb-2">{hitlPayload.supplier_name}</div>
              )}
              {hitlPayload.risk_factors?.map((rf, i) => (
                <div key={i} className="text-sm text-gray-600 ml-4">- {rf.title} [{rf.level}]</div>
              ))}
              {hitlPayload.recommendation && (
                <div className="mt-2 text-sm font-medium text-red-700">Recommendation: {hitlPayload.recommendation}</div>
              )}
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => resumeHitl('APPROVE')} className="bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 text-sm">
                <CheckCircle className="w-4 h-4 inline mr-1" /> Approve
              </button>
              <button onClick={() => resumeHitl('DENY')} className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 text-sm">
                <XCircle className="w-4 h-4 inline mr-1" /> Deny
              </button>
              <button onClick={() => resumeHitl('ESCALATE')} className="bg-gray-600 text-white px-4 py-2 rounded-lg hover:bg-gray-700 text-sm">
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
                <div key={`${i}-${step.message}`} className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-100 flex items-center justify-center">
                    <span className="text-xs font-medium text-primary-700">{i + 1}</span>
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

        {/* Result summary */}
        {phase === 'completed' && summary && (
          <div className="bg-green-50 border border-green-200 rounded-xl p-6 mb-8">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="w-5 h-5 text-green-600" />
              <h3 className="font-semibold text-green-900">Investigation Complete</h3>
            </div>
            <p className="text-sm text-green-800">{summary}</p>
          </div>
        )}

        {error && (
          <div className={cn('rounded-xl p-4 text-sm border', 'bg-red-50 border-red-200 text-red-700')}>
            {error}
          </div>
        )}

        {phase === 'idle' && (
          <div className="text-sm text-gray-400">
            Start an investigation to see live agent updates. You can also browse{' '}
            <Link href="/suppliers" className="text-primary-600 hover:text-primary-700">suppliers</Link>.
          </div>
        )}
      </main>
    </div>
  )
}
