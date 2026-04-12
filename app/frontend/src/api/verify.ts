import { apiFetch } from './client'

export interface VerificationResult {
  fidelity_score: number
  missing_content: string[]
  added_content: string[]
  register_match: 'match' | 'drift' | 'wrong'
  name_check: 'consistent' | 'inconsistent'
  overall: 'pass' | 'warning' | 'fail'
}

export async function verifyParagraph(
  jp: string,
  en: string,
  paragraph_id?: number,
  force = false,
): Promise<VerificationResult> {
  const resp = await apiFetch('/api/v1/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jp, en, paragraph_id, force }),
  })
  if (!resp.ok) throw new Error(`verify failed: ${resp.status}`)
  return resp.json()
}
