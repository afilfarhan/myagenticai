'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Loader2, X } from 'lucide-react'
import { AppHeader } from '@/components/app-header'
import { createSupplier, listSuppliers } from '@/lib/api'
import type { SupplierTier } from '@/lib/types'
import { cn } from '@/lib/utils'

const tierLabels: Record<string, string> = {
  TIER_1: 'Tier 1',
  TIER_2: 'Tier 2',
  TIER_3: 'Tier 3',
  UNKNOWN: 'Unknown',
}

const countries = ['US', 'DE', 'CN', 'TW', 'JP', 'KR', 'IN', 'VN', 'MX', 'BR', 'GB', 'FR']

function riskColor(score: number) {
  if (score >= 70) return 'bg-red-500'
  if (score >= 40) return 'bg-orange-500'
  if (score >= 20) return 'bg-yellow-500'
  return 'bg-green-500'
}

export default function SuppliersPage() {
  const queryClient = useQueryClient()
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [tier, setTier] = useState('')
  const [country, setCountry] = useState('')
  const [showModal, setShowModal] = useState(false)

  // Debounce the search box
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput.trim()), 300)
    return () => clearTimeout(t)
  }, [searchInput])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['suppliers', { search, tier, country }],
    queryFn: () =>
      listSuppliers({
        query: search || undefined,
        tier: tier || undefined,
        country: country || undefined,
        limit: 100,
      }),
  })

  const createMutation = useMutation({
    mutationFn: createSupplier,
    onSuccess: (supplier) => {
      toast.success(`Supplier "${supplier.name}" created`)
      setShowModal(false)
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
    },
    onError: (err) => toast.error(err.message),
  })

  return (
    <div className="min-h-screen bg-gray-50">
      <AppHeader active="/suppliers" />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Suppliers</h1>
            <p className="text-gray-500 mt-1">
              Manage and monitor supplier profiles{data ? ` (${data.total})` : ''}
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="inline-flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg hover:bg-primary-700 transition-colors"
          >
            + Add Supplier
          </button>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="flex items-center gap-4 p-4 border-b border-gray-200">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search suppliers..."
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <select
              value={tier}
              onChange={(e) => setTier(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
            >
              <option value="">All Tiers</option>
              <option value="TIER_1">TIER_1</option>
              <option value="TIER_2">TIER_2</option>
              <option value="TIER_3">TIER_3</option>
            </select>
            <select
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
            >
              <option value="">All Countries</option>
              {countries.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>

          {isLoading ? (
            <div className="p-12 flex items-center justify-center text-gray-400">
              <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading suppliers...
            </div>
          ) : isError ? (
            <div className="p-8 text-sm text-red-600 text-center">{error.message}</div>
          ) : !data || data.suppliers.length === 0 ? (
            <div className="p-8 text-sm text-gray-400 text-center">
              No suppliers found. Add one or seed sample data via <code>POST /api/v1/seed</code>.
            </div>
          ) : (
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
                {data.suppliers.map((s) => (
                  <tr key={s.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <Link href={`/suppliers/${s.id}`} className="font-medium text-gray-900 hover:text-primary-600">{s.name}</Link>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-gray-100 text-gray-700 rounded px-2 py-0.5">{tierLabels[s.tier] || s.tier}</span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{s.country}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">{s.industry ?? '—'}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div className={cn('h-full rounded-full', riskColor(s.risk_score))} style={{ width: `${s.risk_score}%` }} />
                        </div>
                        <span className="text-sm font-medium text-gray-900">{s.risk_score}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn(
                        'text-xs rounded-full px-2 py-0.5',
                        s.is_active ? 'text-green-700 bg-green-100' : 'text-gray-500 bg-gray-100',
                      )}>
                        {s.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link href={`/investigations?supplier=${s.id}`} className="text-xs text-primary-600 hover:text-primary-700">Investigate</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>

      {showModal && (
        <AddSupplierModal
          submitting={createMutation.isPending}
          onClose={() => setShowModal(false)}
          onSubmit={(input) => createMutation.mutate(input)}
        />
      )}
    </div>
  )
}

function AddSupplierModal({
  onSubmit,
  onClose,
  submitting,
}: {
  onSubmit: (input: { name: string; country: string; tier?: SupplierTier; industry?: string }) => void
  onClose: () => void
  submitting: boolean
}) {
  const [name, setName] = useState('')
  const [country, setCountry] = useState('')
  const [tier, setTier] = useState<SupplierTier>('UNKNOWN')
  const [industry, setIndustry] = useState('')

  const valid = name.trim().length > 0 && country.trim().length === 2

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-md p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Add Supplier</h2>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g., TechCorp Taiwan"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Country code *</label>
            <input
              value={country}
              onChange={(e) => setCountry(e.target.value.toUpperCase())}
              maxLength={2}
              placeholder="e.g., TW"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm uppercase focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Tier</label>
            <select
              value={tier}
              onChange={(e) => setTier(e.target.value as SupplierTier)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
            >
              <option value="UNKNOWN">UNKNOWN</option>
              <option value="TIER_1">TIER_1</option>
              <option value="TIER_2">TIER_2</option>
              <option value="TIER_3">TIER_3</option>
            </select>
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Industry</label>
          <input
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            placeholder="e.g., Semiconductors"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900">Cancel</button>
          <button
            disabled={!valid || submitting}
            onClick={() => onSubmit({ name: name.trim(), country: country.trim(), tier, industry: industry.trim() || undefined })}
            className="inline-flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Create Supplier
          </button>
        </div>
      </div>
    </div>
  )
}
