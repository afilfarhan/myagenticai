'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { formatDistanceToNow } from 'date-fns'
import {
  Activity, AlertTriangle, BarChart3, Scale, Search, TrendingDown,
  Users, Zap,
} from 'lucide-react'
import { AppHeader, RiskBadge } from '@/components/app-header'
import { getAgentsStatus, getMetrics, listInvestigations, listRecentAlerts } from '@/lib/api'
import { cn } from '@/lib/utils'

const agentsConfig = [
  { key: 'scout', name: 'Scout', role: 'Data Acquisition', icon: Search, color: 'bg-blue-500' },
  { key: 'analyst', name: 'Analyst', role: 'Reasoning & Synthesis', icon: BarChart3, color: 'bg-purple-500' },
  { key: 'auditor', name: 'Auditor', role: 'Compliance', icon: Scale, color: 'bg-amber-500' },
  { key: 'mitigator', name: 'Mitigator', role: 'Action & Remediation', icon: Zap, color: 'bg-emerald-500' },
]

export default function DashboardPage() {
  const { data: metrics, isError: metricsError } = useQuery({
    queryKey: ['metrics'],
    queryFn: getMetrics,
    refetchInterval: 15000,
  })
  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: getAgentsStatus,
    refetchInterval: 30000,
  })
  const { data: alertsData } = useQuery({
    queryKey: ['alerts', 'recent'],
    queryFn: () => listRecentAlerts({ limit: 8 }),
    refetchInterval: 30000,
  })
  const { data: workflowsData } = useQuery({
    queryKey: ['investigations', 'running'],
    queryFn: () => listInvestigations({ status: 'RUNNING', limit: 5 }),
    refetchInterval: 15000,
  })

  const stats = [
    { label: 'Suppliers Monitored', value: metrics?.total_suppliers ?? null, icon: Users },
    { label: 'Active Workflows', value: metrics?.active_workflows ?? null, icon: Activity },
    { label: 'Risk Alerts (24h)', value: metrics?.risk_alerts_24h ?? null, icon: AlertTriangle },
    { label: 'Avg Risk Score', value: metrics?.avg_risk_score ?? null, icon: TrendingDown },
  ]

  return (
    <div className="min-h-screen bg-gray-50">
      <AppHeader active="/" />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Supply Chain Risk Dashboard</h1>
            <p className="text-gray-500 mt-1">Real-time autonomous monitoring and risk assessment</p>
          </div>
          <Link
            href="/investigations"
            className="inline-flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors"
          >
            <Search className="w-4 h-4" />
            New Investigation
          </Link>
        </div>

        {/* Agent Status */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {agentsConfig.map((agent) => {
            const live = agents?.[agent.key]
            const active = Boolean(live)
            return (
              <div key={agent.key} className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex items-center gap-3">
                  <div className={cn('w-10 h-10 rounded-lg flex items-center justify-center text-white', agent.color)}>
                    <agent.icon className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="font-semibold text-gray-900">{agent.name}</div>
                    <div className="text-sm text-gray-500">{agent.role}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-100">
                  <div
                    className={cn(
                      'w-2 h-2 rounded-full',
                      active ? 'bg-green-500' : 'bg-gray-300',
                    )}
                  />
                  <span className="text-xs text-gray-500">{active ? 'Active' : 'Offline'}</span>
                </div>
              </div>
            )
          })}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {stats.map((stat) => (
            <div key={stat.label} className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center justify-between">
                <div className="text-gray-500 text-sm">{stat.label}</div>
                <stat.icon className="w-5 h-5 text-gray-400" />
              </div>
              {metricsError ? (
                <div className="mt-1 text-sm text-red-600">Unavailable</div>
              ) : stat.value === null ? (
                <div className="mt-1 h-8 w-16 bg-gray-100 rounded animate-pulse" />
              ) : (
                <div className="mt-1 text-2xl font-bold text-gray-900">
                  {Number.isInteger(stat.value) ? stat.value.toLocaleString() : stat.value}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-3 gap-8">
          {/* Recent Alerts */}
          <div className="col-span-2 bg-white rounded-xl border border-gray-200">
            <div className="p-4 border-b border-gray-200 flex items-center justify-between">
              <h2 className="font-semibold text-gray-900">Recent Risk Alerts</h2>
              <Link href="/investigations" className="text-sm text-primary-600 hover:text-primary-700">View all</Link>
            </div>
            {!alertsData || alertsData.alerts.length === 0 ? (
              <div className="p-8 text-sm text-gray-400 text-center">No risk alerts yet</div>
            ) : (
              <div className="divide-y divide-gray-100">
                {alertsData.alerts.map((alert) => (
                  <Link
                    key={alert.id}
                    href={`/suppliers/${alert.supplier_id}`}
                    className="block p-4 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">{alert.supplier_name}</span>
                        <RiskBadge level={alert.level} />
                        <span className="text-xs text-gray-400 border border-gray-200 rounded px-1.5 py-0.5">{alert.category}</span>
                      </div>
                      <span className="text-xs text-gray-400">
                        {formatDistanceToNow(new Date(alert.detected_at), { addSuffix: true })}
                      </span>
                    </div>
                    <p className="text-sm text-gray-600">{alert.description}</p>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* Active Workflows */}
          <div className="bg-white rounded-xl border border-gray-200">
            <div className="p-4 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">Active Workflows</h2>
            </div>
            {!workflowsData || workflowsData.investigations.length === 0 ? (
              <div className="p-8 text-sm text-gray-400 text-center">No active workflows</div>
            ) : (
              <div className="divide-y divide-gray-100">
                {workflowsData.investigations.map((wf) => (
                  <div key={wf.workflow_id} className="p-4 hover:bg-gray-50 transition-colors">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">{wf.workflow_type.replace(/_/g, ' ')}</span>
                      {wf.hitl_required && <RiskBadge level="SEVERE" />}
                    </div>
                    <div className="font-medium text-gray-900 text-sm mb-1">{wf.supplier_name ?? 'Unknown supplier'}</div>
                    <div className="text-xs text-gray-500">
                      Started {formatDistanceToNow(new Date(wf.created_at), { addSuffix: true })}
                    </div>
                    <div className="mt-2 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full w-1/3 bg-primary-500 rounded-full animate-pulse" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
