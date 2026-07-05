import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function formatDateTime(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit'
  })
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 }).format(value)
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('en-US').format(value)
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength - 3) + '...'
}

export function getRiskLevelColor(level: string): string {
  const colors: Record<string, string> = {
    LOW: 'bg-green-100 text-green-800 border-green-200',
    MEDIUM: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    HIGH: 'bg-orange-100 text-orange-800 border-orange-200',
    SEVERE: 'bg-red-100 text-red-800 border-red-200',
    CRITICAL: 'bg-red-900 text-red-100 border-red-700'
  }
  return colors[level] || 'bg-gray-100 text-gray-800 border-gray-200'
}

export function getRiskLevelBg(level: string): string {
  return {
    LOW: 'bg-green-500', MEDIUM: 'bg-yellow-500',
    HIGH: 'bg-orange-500', SEVERE: 'bg-red-500', CRITICAL: 'bg-red-800'
  }[level] || 'bg-gray-500'
}

export function getRiskCategoryIcon(category: string): string {
  const icons: Record<string, string> = {
    GEOPOLITICAL: 'Globe', FINANCIAL: 'DollarSign', ESG: 'Leaf',
    REGULATORY: 'Scale', OPERATIONAL: 'Wrench', CYBER: 'Shield',
    NATURAL_DISASTER: 'CloudRain', SUPPLIER_VIABILITY: 'Building'
  }
  return icons[category] || 'AlertTriangle'
}

export function getWorkflowTypeLabel(type: string): string {
  return {
    AUTONOMOUS_DISCOVERY: 'Autonomous Discovery',
    DEEP_DIVE_INVESTIGATION: 'Deep-Dive Investigation',
    COMPLIANCE_CHECK: 'Compliance Check',
    ALTERNATIVE_SOURCING: 'Alternative Sourcing'
  }[type] || type
}

export function getSupplierTierLabel(tier: string): string {
  return { TIER_1: 'Tier 1', TIER_2: 'Tier 2', TIER_3: 'Tier 3', UNKNOWN: 'Unknown' }[tier] || tier
}