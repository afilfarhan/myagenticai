'use client'

import Link from 'next/link'
import { useParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import { Building2, Globe, Mail, MapPin } from 'lucide-react'
import { AppHeader, RiskBadge } from '@/components/app-header'
import { getSupplier, listInvestigations, listSupplierRiskFactors } from '@/lib/api'
import { cn } from '@/lib/utils'

const tierLabels: Record<string, string> = {
  TIER_1: 'Tier 1',
  TIER_2: 'Tier 2',
  TIER_3: 'Tier 3',
  UNKNOWN: 'Unknown',
}

function riskColor(score: number) {
  if (score >= 70) return 'text-red-600'
  if (score >= 40) return 'text-orange-500'
  if (score >= 20) return 'text-yellow-500'
  return 'text-green-600'
}

export default function SupplierDetailPage() {
  const params = useParams<{ id: string }>()
  const id = params.id

  const { data: supplier, isLoading, isError, error } = useQuery({
    queryKey: ['supplier', id],
    queryFn: () => getSupplier(id),
    retry: false,
  })
  const { data: riskFactors } = useQuery({
    queryKey: ['supplier', id, 'risk-factors'],
    queryFn: () => listSupplierRiskFactors(id),
    enabled: Boolean(supplier),
  })
  const { data: investigations } = useQuery({
    queryKey: ['investigations', 'supplier', id],
    queryFn: () => listInvestigations({ supplier_id: id, limit: 20 }),
    enabled: Boolean(supplier),
  })

  return (
    <div className="min-h-screen bg-gray-50">
      <AppHeader active="/suppliers" />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <Link href="/suppliers" className="text-sm text-primary-600 hover:text-primary-700">← All suppliers</Link>
        </div>

        {isLoading ? (
          <div className="p-12 text-center text-gray-400">Loading supplier...</div>
        ) : isError || !supplier ? (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-red-700 text-sm">
            {error?.message ?? 'Supplier not found'}
          </div>
        ) : (
          <>
            {/* Profile card */}
            <div className="bg-white rounded-xl border border-gray-200 p-6 mb-8">
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-primary-100 flex items-center justify-center">
                    <Building2 className="w-6 h-6 text-primary-600" />
                  </div>
                  <div>
                    <h1 className="text-2xl font-bold text-gray-900">{supplier.name}</h1>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-sm text-gray-500">
                      <span className="text-xs bg-gray-100 text-gray-700 rounded px-2 py-0.5">
                        {tierLabels[supplier.tier] || supplier.tier}
                      </span>
                      <span className="inline-flex items-center gap-1"><Globe className="w-3.5 h-3.5" />{supplier.country}</span>
                      {supplier.industry && <span>{supplier.industry}</span>}
                      {supplier.contact_email && (
                        <span className="inline-flex items-center gap-1"><Mail className="w-3.5 h-3.5" />{supplier.contact_email}</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className={cn('text-4xl font-bold', riskColor(supplier.risk_score))}>
                    {supplier.risk_score}
                  </div>
                  <div className="text-xs text-gray-400 uppercase tracking-wide">Risk score</div>
                  {supplier.last_assessed && (
                    <div className="text-xs text-gray-400 mt-1 inline-flex items-center gap-1">
                      <MapPin className="w-3 h-3" />
                      Assessed {formatDistanceToNow(new Date(supplier.last_assessed), { addSuffix: true })}
                    </div>
                  )}
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-gray-100 flex items-center gap-3">
                <Link
                  href={`/investigations?supplier=${supplier.id}&name=${encodeURIComponent(supplier.name)}`}
                  className="inline-flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-primary-700 transition-colors"
                >
                  Investigate this supplier
                </Link>
              </div>
            </div>

            <div className="grid grid-cols-5 gap-8">
              {/* Risk factors */}
              <div className="col-span-3 bg-white rounded-xl border border-gray-200">
                <div className="p-4 border-b border-gray-200">
                  <h2 className="font-semibold text-gray-900">Risk Factors</h2>
                </div>
                {!riskFactors || riskFactors.length === 0 ? (
                  <div className="p-8 text-sm text-gray-400 text-center">No risk factors detected yet</div>
                ) : (
                  <div className="divide-y divide-gray-100">
                    {riskFactors.map((rf) => (
                      <div key={rf.id} className="p-4">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium text-gray-900">{rf.title}</span>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-400 border border-gray-200 rounded px-1.5 py-0.5">{rf.category}</span>
                            <RiskBadge level={rf.level} />
                          </div>
                        </div>
                        <p className="text-sm text-gray-600">{rf.description}</p>
                        <div className="mt-2 flex items-center gap-4 text-xs text-gray-400">
                          <span>Confidence {(rf.confidence * 100).toFixed(0)}%</span>
                          <span>Impact {rf.impact_score}</span>
                          <span>Likelihood {rf.likelihood_score}</span>
                          <span>Detected {formatDistanceToNow(new Date(rf.detected_at), { addSuffix: true })}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Investigation history */}
              <div className="col-span-2 bg-white rounded-xl border border-gray-200">
                <div className="p-4 border-b border-gray-200">
                  <h2 className="font-semibold text-gray-900">Investigation History</h2>
                </div>
                {!investigations || investigations.investigations.length === 0 ? (
                  <div className="p-8 text-sm text-gray-400 text-center">No investigations yet</div>
                ) : (
                  <div className="divide-y divide-gray-100">
                    {investigations.investigations.map((inv) => (
                      <div key={inv.workflow_id} className="p-4">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-xs text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">
                            {inv.workflow_type.replace(/_/g, ' ')}
                          </span>
                          <StatusPill status={inv.status} />
                        </div>
                        {inv.query && <p className="text-sm text-gray-600 line-clamp-2">{inv.query}</p>}
                        <div className="mt-1 text-xs text-gray-400">
                          {formatDistanceToNow(new Date(inv.created_at), { addSuffix: true })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}

function StatusPill({ status }: { status: string }) {
  const colors: Record<string, string> = {
    RUNNING: 'bg-blue-100 text-blue-700',
    COMPLETED: 'bg-green-100 text-green-700',
    FAILED: 'bg-red-100 text-red-700',
    CANCELLED: 'bg-gray-100 text-gray-600',
    WAITING_HITL: 'bg-yellow-100 text-yellow-700',
    ESCALATED: 'bg-orange-100 text-orange-700',
  }
  return (
    <span className={cn('text-xs font-medium rounded-full px-2 py-0.5', colors[status] || 'bg-gray-100 text-gray-600')}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}
