'use client'

import Link from 'next/link'
import { Shield } from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { href: '/', label: 'Dashboard' },
  { href: '/suppliers', label: 'Suppliers' },
  { href: '/investigations', label: 'Investigations' },
]

export function AppHeader({ active }: { active?: string }) {
  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
        <div className="flex items-center gap-8">
          <Link href="/" className="flex items-center gap-2">
            <Shield className="w-6 h-6 text-primary-600" />
            <span className="font-bold text-lg text-gray-900">SentinelChain</span>
          </Link>
          <nav className="flex items-center gap-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'px-3 py-2 rounded-lg text-sm',
                  item.href === active
                    ? 'font-medium bg-primary-50 text-primary-700'
                    : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50',
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </header>
  )
}

export function RiskBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    LOW: 'bg-green-100 text-green-700',
    MEDIUM: 'bg-yellow-100 text-yellow-700',
    HIGH: 'bg-orange-100 text-orange-700',
    SEVERE: 'bg-red-100 text-red-700',
    CRITICAL: 'bg-red-200 text-red-900',
  }
  return (
    <span
      className={cn(
        'text-xs font-medium px-2 py-0.5 rounded-full',
        colors[level] || 'bg-gray-100 text-gray-700',
      )}
    >
      {level}
    </span>
  )
}
