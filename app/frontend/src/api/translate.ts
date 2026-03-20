import { apiFetch } from './client'

export interface TranslationRead {
  id: number
  source_text_id: number
  content: string
  model: string
  notes: string | null
  created_at: string
  current_stage: string | null
  final_output: string | null
  pipeline_duration_ms: number | null
  stage1_gemma_output: string | null
  stage1_deepseek_output: string | null
  stage1_qwen32b_output: string | null
  consensus_output: string | null
  stage2_output: string | null
}

export async function createSourceText(
  title: string,
  content: string,
): Promise<{ id: number }> {
  const res = await apiFetch('/api/v1/texts/', {
    method: 'POST',
    body: JSON.stringify({ title, content }),
  })
  if (!res.ok) {
    throw new Error(`Failed to create source text: ${res.statusText}`)
  }
  return res.json() as Promise<{ id: number }>
}

export async function startTranslation(
  sourceTextId: number,
): Promise<{ job_id: number }> {
  const res = await apiFetch('/api/v1/translations/translate', {
    method: 'POST',
    body: JSON.stringify({ source_text_id: sourceTextId }),
  })
  if (!res.ok) {
    throw new Error(`Failed to start translation: ${res.statusText}`)
  }
  return res.json() as Promise<{ job_id: number }>
}

export async function getTranslation(id: number): Promise<TranslationRead> {
  const res = await apiFetch(`/api/v1/translations/${id}`)
  if (!res.ok) {
    throw new Error(`Failed to get translation: ${res.statusText}`)
  }
  return res.json() as Promise<TranslationRead>
}

export async function listTranslations(
  sourceTextId?: number,
): Promise<TranslationRead[]> {
  const query = sourceTextId != null ? `?source_text_id=${sourceTextId}` : ''
  const res = await apiFetch(`/api/v1/translations/${query}`)
  if (!res.ok) {
    throw new Error(`Failed to list translations: ${res.statusText}`)
  }
  return res.json() as Promise<TranslationRead[]>
}
