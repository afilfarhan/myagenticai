import { create } from 'zustand'
import {
  getApiErrorMessage,
  startInvestigation,
  streamWorkflowUpdates,
  submitHitlResponse,
} from '@/lib/api'
import type { HitlPayload, WorkflowEvent, WorkflowType } from '@/lib/types'

export type WorkflowPhase =
  | 'idle'
  | 'starting'
  | 'streaming'
  | 'hitl_required'
  | 'completed'
  | 'failed'

interface WorkflowStoreState {
  phase: WorkflowPhase
  workflowId: string | null
  steps: WorkflowEvent[]
  hitlPayload: HitlPayload | null
  summary: string | null
  error: string | null
  start: (input: { query: string; supplierName?: string; workflowType: WorkflowType }) => Promise<void>
  resumeHitl: (action: 'APPROVE' | 'DENY' | 'ESCALATE') => Promise<void>
  reset: () => void
}

let eventSource: EventSource | null = null

function closeStream() {
  eventSource?.close()
  eventSource = null
}

export const useWorkflowStore = create<WorkflowStoreState>((set, get) => {
  function connectStream(workflowId: string) {
    closeStream()
    eventSource = streamWorkflowUpdates(
      workflowId,
      (event) => {
        if ('type' in event && event.type === 'heartbeat') return
        const step = event as WorkflowEvent
        set((s) => ({ steps: [...s.steps, step] }))

        if (step.hitl_required && step.status !== 'COMPLETED') {
          set({ phase: 'hitl_required', hitlPayload: step.hitl_payload ?? get().hitlPayload })
          return
        }
        if (step.status === 'COMPLETED') {
          set({ phase: 'completed', summary: step.summary ?? null })
          closeStream()
        } else if (step.status === 'FAILED' || step.status === 'CANCELLED') {
          set({ phase: 'failed', error: step.message || 'Workflow failed' })
          closeStream()
        }
      },
      () => {
        // Server closed the stream (e.g. after WAITING_HITL). Only surface an
        // error if the workflow is still considered in-flight.
        const phase = get().phase
        if (phase === 'streaming') {
          set({ phase: 'failed', error: 'Stream connection lost' })
        }
      },
    )
  }

  return {
    phase: 'idle',
    workflowId: null,
    steps: [],
    hitlPayload: null,
    summary: null,
    error: null,

    start: async ({ query, supplierName, workflowType }) => {
      closeStream()
      set({
        phase: 'starting',
        steps: [],
        hitlPayload: null,
        summary: null,
        error: null,
        workflowId: null,
      })

      try {
        const res = await startInvestigation({
          query,
          supplier_name: supplierName?.trim() || undefined,
          workflow_type: workflowType,
        })
        set({ workflowId: res.workflow_id, phase: 'streaming' })
        connectStream(res.workflow_id)
      } catch (error) {
        set({ phase: 'failed', error: getApiErrorMessage(error) })
      }
    },

    resumeHitl: async (action) => {
      const workflowId = get().workflowId
      if (!workflowId) return
      try {
        await submitHitlResponse(workflowId, { workflow_id: workflowId, action })
        set({ phase: 'streaming', hitlPayload: null })
        connectStream(workflowId)
      } catch (error) {
        set({ error: getApiErrorMessage(error) })
      }
    },

    reset: () => {
      closeStream()
      set({
        phase: 'idle',
        workflowId: null,
        steps: [],
        hitlPayload: null,
        summary: null,
        error: null,
      })
    },
  }
})
