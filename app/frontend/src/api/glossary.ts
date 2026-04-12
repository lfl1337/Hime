import { apiFetch } from './client'

export interface GlossaryTerm {
  id: number | null
  glossary_id: number
  source_term: string
  target_term: string
  category: string | null
  notes: string | null
  occurrences: number
  is_locked: boolean
}

export interface GlossaryResponse {
  glossary_id: number
  terms: GlossaryTerm[]
}

export async function getGlossary(book_id: number): Promise<GlossaryResponse> {
  const resp = await apiFetch(`/api/v1/books/${book_id}/glossary`, {})
  if (!resp.ok) throw new Error(`glossary fetch failed: ${resp.status}`)
  return resp.json()
}

export async function addTerm(book_id: number, term: Omit<GlossaryTerm, 'id' | 'glossary_id' | 'occurrences'>): Promise<GlossaryTerm> {
  const resp = await apiFetch(`/api/v1/books/${book_id}/glossary/terms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(term),
  })
  if (!resp.ok) throw new Error(`add term failed: ${resp.status}`)
  return resp.json()
}

export async function updateTerm(book_id: number, term_id: number, fields: Partial<GlossaryTerm>): Promise<GlossaryTerm> {
  const resp = await apiFetch(`/api/v1/books/${book_id}/glossary/terms/${term_id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  })
  if (!resp.ok) throw new Error(`update term failed: ${resp.status}`)
  return resp.json()
}

export async function deleteTerm(book_id: number, term_id: number): Promise<void> {
  const resp = await apiFetch(`/api/v1/books/${book_id}/glossary/terms/${term_id}`, { method: 'DELETE' })
  if (!resp.ok) throw new Error(`delete term failed: ${resp.status}`)
}

export async function autoExtract(book_id: number, source_text: string, translated_text: string): Promise<GlossaryTerm[]> {
  const resp = await apiFetch(`/api/v1/books/${book_id}/glossary/auto-extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_text, translated_text }),
  })
  if (!resp.ok) throw new Error(`auto-extract failed: ${resp.status}`)
  return resp.json()
}
