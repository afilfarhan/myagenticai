'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Shield } from 'lucide-react'

const mockSuppliers = [
  { id: 1, name: 'TechCorp Taiwan', tier: 'TIER_1', country: 'TW', industry: 'Semiconductors', risk_score: 72, is_active: true },
  { id: 2, name: 'EuroParts GmbH', tier: 'TIER_1', country: 'DE', industry: 'Automotive', risk_score: 45, is_active: true },
  { id: 3, name: 'Axia Manufacturing', tier: 'TIER_2', country: 'CN', industry: 'Electronics', risk_score: 58, is_active: true },
  { id: 4, name: 'Northern Logistics', tier: 'TIER_3', country: 'US', industry: 'Logistics', risk_score: 22, is_active: true },
]

const tierLabels = { TIER_1: 'Tier 1', TIER_2: 'Tier 2', TIER_3: 'Tier 3', UNKNOWN: 'Unknown' } as Record<string, string>

function riskColor(score: number) {
  if (score >= 70) return 'bg-red-500'
  if (score >= 40) return 'bg-orange-500'
  if (score >= 20) return 'bg-yellow-500'
  return 'bg-green-500'
}

export default function SuppliersPage() {
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
              <Link href="/suppliers" className="px-3 py-2 rounded-lg text-sm font-medium bg-primary-50 text-primary-700">Suppliers</Link>
              <Link href="/investigations" className="px-3 py-2 rounded-lg text-sm text-gray-600 hover:text-gray-900">Investigations</Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Suppliers</h1>
            <p className="text-gray-500 mt-1">Manage and monitor supplier profiles</p>
          </div>
          <button className="inline-flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors">
            + Add Supplier
          </button>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="flex items-center gap-4 p-4 border-b border-gray-200">
            <input type="text" placeholder="Search suppliers..." className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
            <select className="px-3 py-2 border border-gray-300 rounded-lg text-sm">
              <option value="">All Tiers</option>
              <option>TIER_1</option>
              <option>TIER_2</option>
              <option>TIER_3</option>
            </select>
            <select className="px-3 py-2 border border-gray-300 rounded-lg text-sm">
              <option value="">All Countries</option>
              <option>TW</option>
              <option>DE</option>
              <option>CN</option>
              <option>US</option>
            </select>
          </div>

          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Supplier</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Tier</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Country</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Industry</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Risk Score</th>
                <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Status</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {mockSuppliers.map((s) => (
                <tr key={s.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3">
                    <Link href={`/suppliers/${s.id}`} className="font-medium text-gray-900 hover:text-primary-600">{s.name}</Link>
                  </td>
                  <td className="px-4 py-3"><span className="text-xs bg-gray-100 text-gray-700 rounded px-2 py-0.5">{tierLabels[s.tier] || s.tier}</span></td>
                  <td className="px-4 py-3 text-sm text-gray-600">{s.country}</td>
                  <td className="px-4 py-3 text-sm text-gray-600">{s.industry}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${riskColor(s.risk_score)}`} style={{ width: `${s.risk_score}%` }} />
                      </div>
                      <span className="text-sm font-medium text-gray-900">{s.risk_score}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3"><span className="text-xs text-green-700 bg-green-100 rounded-full px-2 py-0.5">Active</span></td>
                  <td className="px-4 py-3 text-right">
                    <Link href={`/investigations?supplier=${s.id}`} className="text-xs text-primary-600 hover:text-primary-700">Investigate</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  )
}