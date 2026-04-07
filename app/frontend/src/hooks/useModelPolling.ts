import { useEffect, useState } from 'react'
import { fetchModelEndpoints } from '../api/compare'
import { fetchAllRuns } from '../api/training'
import type { ModelLiveStatus } from '../types/comparison'

const INITIAL: Record<string, ModelLiveStatus> = {
  gemma:    { inferenceOnline: false, inferenceEndpoint: null, loadedModel: null, isTraining: false, trainingProgress: null },
  deepseek: { inferenceOnline: false, inferenceEndpoint: null, loadedModel: null, isTraining: false, trainingProgress: null },
  qwen32b:  { inferenceOnline: false, inferenceEndpoint: null, loadedModel: null, isTraining: false, trainingProgress: null },
}

function runNameToKey(runName: string): string | null {
  const n = runName.toLowerCase()
  if (n.includes('qwen2.5-32b') || n.includes('qwen2.5_32b')) return 'qwen32b'
  if (n.includes('gemma')) return 'gemma'
  if (n.includes('deepseek')) return 'deepseek'
  return null
}

const EMPTY_STATUS: ModelLiveStatus = {
  inferenceOnline: false,
  inferenceEndpoint: null,
  loadedModel: null,
  isTraining: false,
  trainingProgress: null,
}

export function useModelPolling(active: boolean): {
  liveStatuses: Record<string, ModelLiveStatus>
  isLoading: boolean
} {
  const [liveStatuses, setLiveStatuses] = useState<Record<string, ModelLiveStatus>>(INITIAL)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!active) return

    let cancelled = false

    async function poll() {
      setIsLoading(true)
      try {
        const [endpoints, runs] = await Promise.all([
          fetchModelEndpoints().catch(() => []),
          fetchAllRuns().catch(() => []),
        ])

        if (cancelled) return

        // Start with the initial 3 Stage 1 keys, then extend with any
        // additional keys returned by the backend (consensus, stage2, stage3).
        const next: Record<string, ModelLiveStatus> = {
          gemma:    { ...INITIAL.gemma },
          deepseek: { ...INITIAL.deepseek },
          qwen32b:  { ...INITIAL.qwen32b },
        }

        // Populate inference status — accept any key the backend returns
        for (const ep of endpoints) {
          const key = ep.key as string
          if (!(key in next)) {
            next[key] = { ...EMPTY_STATUS }
          }
          next[key].inferenceOnline = ep.online
          next[key].inferenceEndpoint = ep.endpoint
          next[key].loadedModel = ep.loaded_model
        }

        // Populate training status
        for (const run of runs) {
          const key = runNameToKey(run.run_name)
          if (!key) continue
          if (!(key in next)) {
            next[key] = { ...EMPTY_STATUS }
          }
          if (run.status === 'training') {
            next[key].isTraining = true
            next[key].trainingProgress = {
              currentStep: run.current_step,
              totalSteps: run.max_steps,
              progressPct: run.progress_pct,
              loss: run.best_eval_loss,
              eta: null,
              epoch: null,
            }
          }
        }

        setLiveStatuses(next)
      } catch {
        // silent — keep stale data
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void poll()
    const id = setInterval(() => void poll(), 10_000)

    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [active])

  return { liveStatuses, isLoading }
}
