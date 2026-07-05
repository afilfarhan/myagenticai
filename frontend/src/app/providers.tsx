'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { useState } from 'react'

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: { staleTime: 60 * 1000, refetchOnWindowFocus: false }
    }
  }))

  return (
    <QueryClientProvider client={queryClient}>
      <Toaster richColors position="top-right" />
      {children}
    </QueryClientProvider>
  )
}