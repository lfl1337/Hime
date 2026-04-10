import { apiFetch } from './client'

export interface ReviewFinding {
  reader: string
  severity: 'info' | 'warning' | 'error'
  paragraph_id: number | null
  finding: string
  suggestion: string | null
}

export interface ReviewResponse {
  findings: ReviewFinding[]
  rerun_triggered: boolean
}

export interface ReviewRequest {
  translation: string
  source: string | null
  paragraph_ids?: number[]
  auto_rerun?: boolean
}

export async function runReview(req: ReviewRequest): Promise<ReviewResponse> {
  const resp = await apiFetch('/api/v1/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) throw new Error(`review failed: ${resp.status}`)
  return resp.json()
}
