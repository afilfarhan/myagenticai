import { create } from 'zustand'
import {
  connectWorkflowSocket,
  getApiErrorMessage,
  startInvestigation,
  streamWorkflowUpdates,
  submitHitlResponse,
  type StreamHandle,
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
  transport: 'websocket' | 'sse' | null
  start: (input: { query: string; supplierName?: string; workflowType: WorkflowType }) => Promise<void>
  resumeHitl: (action: 'APPROVE' | 'DENY' | 'ESCALATE') => Promise<void>
  reset: () => void
}

let streamHandle: StreamHandle | null = null

function closeStream() {
  streamHandle?.close()
  streamHandle = null
}

export const useWorkflowStore = create<WorkflowStoreState>((set, get) => {
  function processEvent(step: WorkflowEvent) {
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
  }

  /**
   * Prefer the WebSocket transport; if it fails before delivering any event
   * (e.g. proxies without WS support), silently fall back to SSE.
   */
  function connectStream(workflowId: string) {
    closeStream()
    let received = 0
    let fellBack = false

    const onEvent = (event: WorkflowEvent | { type: 'heartbeat' }) => {
      if ('type' in event && event.type === 'heartbeat') return
      received += 1
      set({ transport: fellBack ? 'sse' : 'websocket' })
      processEvent(event as WorkflowEvent)
    }

    const onWsDead = () => {
      if (received === 0 && !fellBack && get().workflowId === workflowId) {
        fellBack = true
        streamHandle?.close()
        streamHandle = streamWorkflowUpdates(workflowId, onEvent, () => {
          // Server closed the stream (e.g. after WAITING_HITL). Only surface
          // an error if the workflow is still considered in-flight.
          if (get().phase === 'streaming') {
            set({ phase: 'failed', error: 'Stream connection lost' })
          }
        })
      }
    }

    streamHandle = connectWorkflowSocket(workflowId, onEvent, onWsDead)
  }

  return {
    phase: 'idle',
    workflowId: null,
    steps: [],
    hitlPayload: null,
    summary: null,
    error: null,
    transport: null,

    start: async ({ query, supplierName, workflowType }) => {
      closeStream()
      set({
        phase: 'starting',
        steps: [],
        hitlPayload: null,
        summary: null,
        error: null,
        workflowId: null,
        transport: null,
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
        transport: null,
      })
    },
  }
})
