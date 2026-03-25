import { apiFetch } from './client'
import type { ModelEndpoint } from '../types/comparison'

export async function startCompare(text: string, notes?: string): Promise<{ job_id: number }> {
  const res = await apiFetch('/api/v1/compare', {
    method: 'POST',
    body: JSON.stringify({ text, notes: notes ?? null }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText })) as { detail: string }
    throw new Error(err.detail || res.statusText)
  }
  return res.json() as Promise<{ job_id: number }>
}

export async function fetchModelEndpoints(): Promise<ModelEndpoint[]> {
  const res = await apiFetch('/api/v1/models')
  if (!res.ok) throw new Error(`models failed: ${res.statusText}`)
  return res.json() as Promise<ModelEndpoint[]>
}
