import { apiFetch, getBaseUrl } from './client'

export interface EtaInfo {
  pct: number
  current_step: number
  total_steps: number
  elapsed: string
  eta: string
  sec_per_it: number
}

export interface TrainingStatus {
  run_name: string
  model_name: string
  status: 'idle' | 'training' | 'interrupted' | 'complete'
  current_step: number
  max_steps: number
  current_epoch: number
  max_epochs: number
  progress_pct: number
  best_checkpoint: string | null
  best_eval_loss: number | null
  latest_train_loss: number | null
  has_log_file: boolean
  log_file_path: string | null
  scripts_path: string
  eta_info: EtaInfo | null
}

export interface CheckpointInfo {
  name: string
  step: number
  epoch: number
  eval_loss: number | null
  folder_size_mb: number
  timestamp: string
  is_best: boolean
  is_last: boolean
  is_interrupted: boolean
  full_path: string
}

export interface LossPoint {
  step: number
  epoch: number
  train_loss: number | null
  eval_loss: number | null
  learning_rate: number | null
}

export interface RunInfo {
  run_name: string
  display_name: string
  status: 'idle' | 'training' | 'interrupted' | 'complete'
  current_step: number
  max_steps: number
  progress_pct: number
  best_eval_loss: number | null
  has_active_log: boolean
}

export interface GGUFModelInfo {
  name: string
  display_name: string
  size_gb: number
  file_count: number
  is_pipeline_model: boolean
  pipeline_role: string | null
}

export interface TrainingProcess {
  model_name: string
  pid: number
  started_at: string
  checkpoint: string | null
  log_file: string
  epochs: number
}

export interface StartTrainingParams {
  model_name: string
  resume_checkpoint: string | null
  epochs: number
  conda_env: string
}

function runQuery(run?: string): string {
  if (!run) return ''
  return '?' + new URLSearchParams({ run }).toString()
}

export async function getTrainingStatus(run?: string): Promise<TrainingStatus> {
  const res = await apiFetch(`/api/v1/training/status${runQuery(run)}`)
  if (!res.ok) throw new Error(`training/status failed: ${res.statusText}`)
  return res.json() as Promise<TrainingStatus>
}

export async function getCheckpoints(run?: string): Promise<CheckpointInfo[]> {
  const res = await apiFetch(`/api/v1/training/checkpoints${runQuery(run)}`)
  if (!res.ok) throw new Error(`training/checkpoints failed: ${res.statusText}`)
  return res.json() as Promise<CheckpointInfo[]>
}

export async function getLossHistory(run?: string): Promise<LossPoint[]> {
  const res = await apiFetch(`/api/v1/training/loss-history${runQuery(run)}`)
  if (!res.ok) throw new Error(`training/loss-history failed: ${res.statusText}`)
  return res.json() as Promise<LossPoint[]>
}

export async function getTrainingLog(lines = 20, run?: string): Promise<string[]> {
  const params = new URLSearchParams({ lines: String(lines), ...(run ? { run } : {}) })
  const res = await apiFetch(`/api/v1/training/log?${params.toString()}`)
  if (!res.ok) throw new Error(`training/log failed: ${res.statusText}`)
  const data = await res.json() as { lines: string[] }
  return data.lines
}

export async function fetchAllRuns(): Promise<RunInfo[]> {
  const res = await apiFetch('/api/v1/training/runs')
  if (!res.ok) throw new Error(`training/runs failed: ${res.statusText}`)
  return res.json() as Promise<RunInfo[]>
}

export async function fetchGGUFModels(): Promise<GGUFModelInfo[]> {
  const res = await apiFetch('/api/v1/training/gguf-models')
  if (!res.ok) throw new Error(`training/gguf-models failed: ${res.statusText}`)
  return res.json() as Promise<GGUFModelInfo[]>
}

export async function createTrainingEventSource(run?: string): Promise<EventSource> {
  const baseUrl = await getBaseUrl()
  const url = `${baseUrl}/api/v1/training/stream${run ? `?run=${encodeURIComponent(run)}` : ''}`
  return new EventSource(url)
}

export async function startTraining(params: StartTrainingParams): Promise<TrainingProcess> {
  const res = await apiFetch('/api/v1/training/start', {
    method: 'POST',
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText })) as { detail: string }
    throw new Error(err.detail || res.statusText)
  }
  return res.json() as Promise<TrainingProcess>
}

export async function stopTraining(modelName: string): Promise<{ stopped: boolean; graceful: boolean }> {
  const res = await apiFetch('/api/v1/training/stop', {
    method: 'POST',
    body: JSON.stringify({ model_name: modelName }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText })) as { detail: string }
    throw new Error(err.detail || res.statusText)
  }
  return res.json() as Promise<{ stopped: boolean; graceful: boolean }>
}

export async function getRunningProcesses(): Promise<TrainingProcess[]> {
  const res = await apiFetch('/api/v1/training/processes')
  if (!res.ok) throw new Error(`training/processes failed: ${res.statusText}`)
  return res.json() as Promise<TrainingProcess[]>
}

export async function getAvailableCheckpoints(modelName: string): Promise<string[]> {
  const res = await apiFetch(`/api/v1/training/available-checkpoints/${encodeURIComponent(modelName)}`)
  if (!res.ok) throw new Error(`training/available-checkpoints failed: ${res.statusText}`)
  const data = await res.json() as { checkpoints: string[] }
  return data.checkpoints
}
