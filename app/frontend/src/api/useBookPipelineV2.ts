// app/frontend/src/api/useBookPipelineV2.ts
import { useCallback, useRef, useState } from 'react'
import { createBookPipelineWebSocket } from './client'
import type { BookPipelineState, PipelineV2Event, SegmentProgress } from './pipeline_v2'
import { INITIAL_PIPELINE_STATE } from './pipeline_v2'

export interface UseBookPipelineV2Return {
  state: BookPipelineState
  start: (bookId: number) => void
  reset: () => void
}

export function useBookPipelineV2(): UseBookPipelineV2Return {
  const [state, setState] = useState<BookPipelineState>(INITIAL_PIPELINE_STATE)
  const wsRef = useRef<WebSocket | null>(null)

  const reset = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    setState(INITIAL_PIPELINE_STATE)
  }, [])

  const start = useCallback((bookId: number) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return

    setState({ ...INITIAL_PIPELINE_STATE, status: 'translating' })

    createBookPipelineWebSocket(bookId).then((ws) => {
      wsRef.current = ws

      ws.onmessage = (ev) => {
        if (ev.data === 'null' || ev.data === null) return
        let parsed: PipelineV2Event
        try {
          parsed = JSON.parse(ev.data as string) as PipelineV2Event
        } catch {
          return
        }
        setState(prev => applyV2Event(prev, parsed))
      }

      ws.onerror = () => {
        setState(prev => ({ ...prev, status: 'error', error: 'WebSocket connection error' }))
      }

      ws.onclose = () => {
        // State already updated by pipeline_complete or pipeline_error
      }
    }).catch(() => {
      setState(prev => ({ ...prev, status: 'error', error: 'Failed to connect to pipeline' }))
    })
  }, [])

  return { state, start, reset }
}

function applyV2Event(prev: BookPipelineState, ev: PipelineV2Event): BookPipelineState {
  switch (ev.event) {
    case 'preprocess_complete':
      return { ...prev, status: 'translating', totalSegments: ev.segment_count }

    case 'segment_start': {
      const seg: SegmentProgress = {
        paragraphId: ev.paragraph_id,
        index: ev.index,
        status: 'stage1',
        verdict: null,
        retryCount: 0,
        translation: null,
      }
      return {
        ...prev,
        totalSegments: ev.total,
        segments: { ...prev.segments, [ev.paragraph_id]: seg },
      }
    }

    case 'stage1_complete':
      return updateSegment(prev, ev.paragraph_id, { status: 'stage2' })

    case 'stage2_complete':
      return updateSegment(prev, ev.paragraph_id, { status: 'stage3' })

    case 'stage3_complete':
      return updateSegment(prev, ev.paragraph_id, { status: 'stage4' })

    case 'stage4_verdict':
      return updateSegment(prev, ev.paragraph_id, {
        verdict: ev.verdict,
        retryCount: ev.retry_count,
      })

    case 'segment_complete':
      return {
        ...updateSegment(prev, ev.paragraph_id, {
          status: 'complete',
          translation: ev.translation,
        }),
        completedSegments: prev.completedSegments + 1,
      }

    case 'pipeline_complete':
      return { ...prev, status: 'complete', epubPath: ev.epub_path }

    case 'pipeline_error':
      return { ...prev, status: 'error', error: ev.detail }

    default:
      return prev
  }
}

function updateSegment(
  prev: BookPipelineState,
  paragraphId: number,
  patch: Partial<SegmentProgress>,
): BookPipelineState {
  const existing = prev.segments[paragraphId]
  if (!existing) return prev
  return {
    ...prev,
    segments: {
      ...prev.segments,
      [paragraphId]: { ...existing, ...patch },
    },
  }
}
