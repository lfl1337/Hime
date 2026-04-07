import { useEffect, useRef, useState } from 'react'
import { createWebSocket } from './client'

// Discriminated union of all pipeline events
export type PipelineEvent =
  | { event: 'stage1_start'; models: string[] }
  | { event: 'stage1_token'; model: string; token: string }
  | { event: 'stage1_complete'; model: string; output: string }
  | { event: 'consensus_start' }
  | { event: 'consensus_token'; token: string }
  | { event: 'consensus_complete'; output: string }
  | { event: 'stage2_start' }
  | { event: 'stage2_token'; token: string }
  | { event: 'stage2_complete'; output: string }
  | { event: 'stage3_start' }
  | { event: 'stage3_token'; token: string }
  | { event: 'stage3_complete'; output: string }
  | { event: 'pipeline_complete'; final_output: string; duration_ms: number }
  | { event: 'pipeline_error'; detail: string }
  | { event: 'model_error'; stage: string; model: string; detail: string }
  | { event: 'model_unavailable'; model: string; reason: string }
  | { event: 'pipeline_status'; current_stage: string }

export type PipelineStage =
  | 'idle'
  | 'stage1'
  | 'consensus'
  | 'stage2'
  | 'stage3'
  | 'complete'
  | 'error'

export interface PipelineState {
  stage: PipelineStage
  stage1Tokens: Record<string, string>
  stage1Complete: Record<string, string>
  modelErrors: Record<string, string>
  modelUnavailable: Record<string, string>
  consensusOutput: string
  stage2Output: string
  finalOutput: string
  durationMs: number | null
  isComplete: boolean
  error: string | null
}

const initialState: PipelineState = {
  stage: 'idle',
  stage1Tokens: {},
  stage1Complete: {},
  modelErrors: {},
  modelUnavailable: {},
  consensusOutput: '',
  stage2Output: '',
  finalOutput: '',
  durationMs: null,
  isComplete: false,
  error: null,
}

export function usePipeline(jobId: number | null): PipelineState {
  const [state, setState] = useState<PipelineState>(initialState)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (jobId === null) {
      setState(initialState)
      return
    }

    // Reset for new job
    setState(initialState)

    let cancelled = false

    createWebSocket(jobId).then((ws) => {
      if (cancelled) {
        ws.close()
        return
      }
      wsRef.current = ws

      ws.onmessage = (ev) => {
        let parsed: PipelineEvent
        try {
          parsed = JSON.parse(ev.data as string) as PipelineEvent
        } catch {
          return
        }

        setState((prev) => applyEvent(prev, parsed))
      }

      ws.onerror = () => {
        setState((prev) => ({
          ...prev,
          stage: 'error',
          error: 'WebSocket connection error',
        }))
      }

      ws.onclose = () => {
        // Nothing — state is already updated by pipeline_complete or pipeline_error
      }
    }).catch(() => {
      setState((prev) => ({
        ...prev,
        stage: 'error',
        error: 'Failed to connect to pipeline WebSocket',
      }))
    })

    return () => {
      cancelled = true
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [jobId])

  return state
}

function applyEvent(prev: PipelineState, ev: PipelineEvent): PipelineState {
  switch (ev.event) {
    case 'stage1_start':
      return { ...prev, stage: 'stage1' }

    case 'stage1_token': {
      const existing = prev.stage1Tokens[ev.model] ?? ''
      return {
        ...prev,
        stage1Tokens: { ...prev.stage1Tokens, [ev.model]: existing + ev.token },
      }
    }

    case 'stage1_complete':
      return {
        ...prev,
        stage1Complete: { ...prev.stage1Complete, [ev.model]: ev.output },
      }

    case 'consensus_start':
      return { ...prev, stage: 'consensus' }

    case 'consensus_token':
      return { ...prev, consensusOutput: prev.consensusOutput + ev.token }

    case 'consensus_complete':
      return { ...prev, consensusOutput: ev.output }

    case 'stage2_start':
      return { ...prev, stage: 'stage2' }

    case 'stage2_token':
      return { ...prev, stage2Output: prev.stage2Output + ev.token }

    case 'stage2_complete':
      return { ...prev, stage2Output: ev.output }

    case 'stage3_start':
      return { ...prev, stage: 'stage3' }

    case 'stage3_token':
      return { ...prev, finalOutput: prev.finalOutput + ev.token }

    case 'stage3_complete':
      return { ...prev, finalOutput: ev.output }

    case 'pipeline_complete':
      return {
        ...prev,
        stage: 'complete',
        finalOutput: ev.final_output,
        durationMs: ev.duration_ms,
        isComplete: true,
      }

    case 'pipeline_error':
      return { ...prev, stage: 'error', error: ev.detail }

    case 'model_error':
      return {
        ...prev,
        modelErrors: { ...prev.modelErrors, [ev.model]: ev.detail },
      }

    case 'model_unavailable':
      return {
        ...prev,
        modelUnavailable: { ...prev.modelUnavailable, [ev.model]: ev.reason },
      }

    case 'pipeline_status':
      return prev

    default:
      return prev
  }
}
