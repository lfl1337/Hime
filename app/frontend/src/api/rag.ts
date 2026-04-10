import { apiFetch } from './client'

export interface RagSeriesStats {
  series_id: number
  chunk_count: number
  last_update: string | null
}

export interface RagIndexResponse {
  book_id: number
  new_chunks: number
}

export async function buildIndex(book_id: number): Promise<RagIndexResponse> {
  const resp = await apiFetch(`/api/v1/rag/index/${book_id}`, { method: 'POST' })
  if (!resp.ok) throw new Error(`rag index failed: ${resp.status}`)
  return resp.json()
}

export async function getStats(series_id: number): Promise<RagSeriesStats> {
  const resp = await apiFetch(`/api/v1/rag/series/${series_id}/stats`, {})
  if (!resp.ok) throw new Error(`rag stats failed: ${resp.status}`)
  return resp.json()
}

export async function deleteIndex(series_id: number): Promise<void> {
  const resp = await apiFetch(`/api/v1/rag/series/${series_id}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`rag delete failed: ${resp.status}`)
}
