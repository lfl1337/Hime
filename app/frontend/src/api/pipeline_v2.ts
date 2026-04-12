// app/frontend/src/api/pipeline_v2.ts
import { apiFetch } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SegmentSample {
  paragraph_id: number
  source_jp: string
  mecab_token_count: number
  glossary_context: string
  rag_context: string
}

export interface PreprocessResponse {
  book_id: number
  segment_count: number
  sample: SegmentSample[]
}

// Discriminated union of all v2 pipeline WebSocket events
export type PipelineV2Event =
  | { event: 'preprocess_complete'; segment_count: number }
  | { event: 'segment_start'; paragraph_id: number; index: number; total: number }
  | { event: 'stage1_complete'; paragraph_id: number; retry_kind?: 'full_retry' }
  | { event: 'stage2_complete'; paragraph_id: number; retry_kind?: 'full_retry' }
  | { event: 'stage3_complete'; paragraph_id: number; retry_kind?: 'fix_pass' | 'full_retry'; fix_pass_count?: number; full_retry_count?: number }
  | { event: 'stage4_verdict'; paragraph_id: number; verdict: 'ok' | 'fix_pass' | 'full_retry'; instruction: string; fix_pass_count: number; full_retry_count: number }
  | { event: 'segment_complete'; paragraph_id: number; translation: string; retry_flag: boolean }
  | { event: 'pipeline_complete'; epub_path: string }
  | { event: 'pipeline_error'; detail: string }

export type SegmentStatus = 'pending' | 'stage1' | 'stage2' | 'stage3' | 'stage4' | 'complete' | 'error'

export interface SegmentProgress {
  paragraphId: number
  index: number
  status: SegmentStatus
  verdict: 'ok' | 'fix_pass' | 'full_retry' | null
  retryCount: number
  retryFlag: boolean
  fixPassCount: number
  fullRetryCount: number
  translation: string | null
}

export type PipelineV2Status =
  | 'idle'
  | 'preprocessing'
  | 'translating'
  | 'complete'
  | 'error'

export interface BookPipelineState {
  status: PipelineV2Status
  totalSegments: number
  completedSegments: number
  segments: Record<number, SegmentProgress>
  epubPath: string | null
  error: string | null
}

export const INITIAL_PIPELINE_STATE: BookPipelineState = {
  status: 'idle',
  totalSegments: 0,
  completedSegments: 0,
  segments: {},
  epubPath: null,
  error: null,
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function triggerPreprocess(bookId: number): Promise<PreprocessResponse> {
  const res = await apiFetch(`/api/v1/pipeline/${bookId}/preprocess`, { method: 'POST' })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`Preprocess failed (${res.status}): ${detail}`)
  }
  return res.json() as Promise<PreprocessResponse>
}
