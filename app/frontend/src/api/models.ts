import { apiFetch } from './client'

export async function checkHealth(): Promise<{ status: string; app: string }> {
  const res = await apiFetch('/health')
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.statusText}`)
  }
  return res.json() as Promise<{ status: string; app: string }>
}
