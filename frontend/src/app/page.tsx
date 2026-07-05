'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Shield, Globe, DollarSign, Scale, Activity, AlertTriangle,
  CheckCircle, Clock, Search, Plus, ChevronRight, BarChart3,
  Users, Zap, TrendingUp, TrendingDown
} from 'lucide-react'
import { cn } from '@/lib/utils'

const agentsConfig = [
  { name: 'Scout', role: 'Data Acquisition', icon: Search, color: 'bg-blue-500' },
  { name: 'Analyst', role: 'Reasoning & Synthesis', icon: BarChart3, color: 'bg-purple-500' },
  { name: 'Auditor', role: 'Compliance', icon: Scale, color: 'bg-amber-500' },
  { name: 'Mitigator', role: 'Action & Remediation', icon: Zap, color: 'bg-emerald-500' },
]

const mockStats = [
  { label: 'Suppliers Monitored', value: '2,847', change: '+12%', trend: 'up', icon: Users },
  { label: 'Active Workflows', value: '14', change: '+3', trend: 'up', icon: Activity },
  { label: 'Risk Alerts (24h)', value: '23', change: '-8%', trend: 'down', icon: AlertTriangle },
  { label: 'Avg Risk Score', value: '32.4', change: '-2.1', trend: 'down', icon: TrendingDown },
]

const mockRecentAlerts = [
  { id: 1, supplier: 'TechCorp Taiwan', risk: 'HIGH', category: 'FINANCIAL', time: '2h ago', summary: '40% drop in cash reserves detected in latest 10-Q filing' },
  { id: 2, supplier: 'EuroParts GmbH', risk: 'SEVERE', category: 'REGULATORY', time: '4h ago', summary: 'New EU sanctions entity linked as sub-contractor' },
  { id: 3, supplier: 'Axia Manufacturing', risk: 'MEDIUM', category: 'GEOPOLITICAL', time: '6h ago', summary: 'Port strike affecting shipping routes identified' },
  { id: 4, supplier: 'Northern Logistics', risk: 'LOW', category: 'ESG', time: '12h ago', summary: 'Minor ESG compliance gap in environmental reporting' },
]

const mockActiveWorkflows = [
  { id: 'wf-001', type: 'DEEP_DIVE_INVESTIGATION', supplier: 'TechCorp Taiwan', agent: 'Analyst', progress: 60 },
  { id: 'wf-002', type: 'AUTONOMOUS_DISCOVERY', supplier: 'EuroParts GmbH', agent: 'Auditor', progress: 80 },
  { id: 'wf-003', type: 'COMPLIANCE_CHECK', supplier: 'GlobalChem Ltd', agent: 'Scout', progress: 30 },
]

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Supply Chain Risk Dashboard</h1>
            <p className="text-gray-500 mt-1">Real-time autonomous monitoring and risk assessment</p>
          </div>
          <Link href="/investigations" className="inline-flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
            <Search className="w-4 h-4" />
            New Investigation
          </Link>
        </div>

        {/* Agent Status */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {agentsConfig.map((agent) => (
            <div key={agent.name} className="bg-white rounded-xl border border-gray-200 p-4">
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
                <div className="w-2 h-2 rounded-full bg-green-500" />
                <span className="text-xs text-gray-500">Active</span>
              </div>
            </div>
          ))}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          {mockStats.map((stat) => (
            <div key={stat.label} className="bg-white rounded-xl border border-gray-200 p-4">
              <div className="flex items-center justify-between">
                <div className="text-gray-500 text-sm">{stat.label}</div>
                <stat.icon className="w-5 h-5 text-gray-400" />
              </div>
              <div className="flex items-baseline gap-2 mt-1">
                <div className="text-2xl font-bold text-gray-900">{stat.value}</div>
                <div className={cn('text-xs font-medium', stat.trend === 'up' ? 'text-green-600' : 'text-red-600')}>
                  {stat.trend === 'up' ? <TrendingUp className="w-3 h-3 inline" /> : <TrendingDown className="w-3 h-3 inline" />}
                  {' '}{stat.change}
                </div>
              </div>
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
            <div className="divide-y divide-gray-100">
              {mockRecentAlerts.map((alert) => (
                <div key={alert.id} className="p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">{alert.supplier}</span>
                      <RiskBadge level={alert.risk} />
                      <span className="text-xs text-gray-400 border border-gray-200 rounded px-1.5 py-0.5">{alert.category}</span>
                    </div>
                    <span className="text-xs text-gray-400">{alert.time}</span>
                  </div>
                  <p className="text-sm text-gray-600">{alert.summary}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Active Workflows */}
          <div className="bg-white rounded-xl border border-gray-200">
            <div className="p-4 border-b border-gray-200">
              <h2 className="font-semibold text-gray-900">Active Workflows</h2>
            </div>
            <div className="divide-y divide-gray-100">
              {mockActiveWorkflows.map((wf) => (
                <div key={wf.id} className="p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-gray-400 bg-gray-100 rounded px-1.5 py-0.5">{wf.type.replace('_', ' ')}</span>
                    <span className="text-xs text-gray-400">{Math.round(wf.progress)}%</span>
                  </div>
                  <div className="font-medium text-gray-900 text-sm mb-1">{wf.supplier}</div>
                  <div className="text-xs text-gray-500">Agent: {wf.agent}</div>
                  <div className="mt-2 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div className="h-full bg-primary-500 rounded-full" style={{ width: `${wf.progress}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

function Header() {
  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2">
              <Shield className="w-6 h-6 text-primary-600" />
              <span className="font-bold text-lg text-gray-900">SentinelChain</span>
            </div>
            <nav className="flex items-center gap-1">
              <Link href="/" className="px-3 py-2 rounded-lg text-sm font-medium bg-primary-50 text-primary-700">Dashboard</Link>
              <Link href="/suppliers" className="px-3 py-2 rounded-lg text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-50">Suppliers</Link>
              <Link href="/investigations" className="px-3 py-2 rounded-lg text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-50">Investigations</Link>
            </nav>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <div className="w-2 h-2 rounded-full bg-green-500" />
              <span>All agents operational</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}

function RiskBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    LOW: 'bg-green-100 text-green-700', MEDIUM: 'bg-yellow-100 text-yellow-700',
    HIGH: 'bg-orange-100 text-orange-700', SEVERE: 'bg-red-100 text-red-700',
    CRITICAL: 'bg-red-200 text-red-900'
  }
  return <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', colors[level] || 'bg-gray-100 text-gray-700')}>{level}</span>
}