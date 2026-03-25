import { useEffect, useState } from 'react'
import { fetchModelEndpoints } from '../api/compare'
import { fetchAllRuns } from '../api/training'
import type { ModelLiveStatus } from '../types/comparison'

type ModelKey = 'gemma' | 'deepseek' | 'qwen32b'

const INITIAL: Record<ModelKey, ModelLiveStatus> = {
  gemma:    { inferenceOnline: false, inferenceEndpoint: null, loadedModel: null, isTraining: false, trainingProgress: null },
  deepseek: { inferenceOnline: false, inferenceEndpoint: null, loadedModel: null, isTraining: false, trainingProgress: null },
  qwen32b:  { inferenceOnline: false, inferenceEndpoint: null, loadedModel: null, isTraining: false, trainingProgress: null },
}

function runNameToKey(runName: string): ModelKey | null {
  const n = runName.toLowerCase()
  if (n.includes('qwen2.5-32b') || n.includes('qwen2.5_32b')) return 'qwen32b'
  if (n.includes('gemma')) return 'gemma'
  if (n.includes('deepseek')) return 'deepseek'
  return null
}

export function useModelPolling(active: boolean): {
  liveStatuses: Record<ModelKey, ModelLiveStatus>
  isLoading: boolean
} {
  const [liveStatuses, setLiveStatuses] = useState<Record<ModelKey, ModelLiveStatus>>(INITIAL)
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

        const next: Record<ModelKey, ModelLiveStatus> = {
          gemma:    { ...INITIAL.gemma },
          deepseek: { ...INITIAL.deepseek },
          qwen32b:  { ...INITIAL.qwen32b },
        }

        // Populate inference status
        for (const ep of endpoints) {
          const key = ep.key as ModelKey
          if (key in next) {
            next[key].inferenceOnline = ep.online
            next[key].inferenceEndpoint = ep.endpoint
            next[key].loadedModel = ep.loaded_model
          }
        }

        // Populate training status
        for (const run of runs) {
          const key = runNameToKey(run.run_name)
          if (!key) continue
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
