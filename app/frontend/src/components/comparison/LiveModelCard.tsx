import { useNavigate } from 'react-router-dom'
import type { ModelLiveStatus } from '../../types/comparison'

interface LiveModelCardProps {
  modelKey: 'qwen32b' | 'translategemma' | 'qwen35_9b' | 'llm_jp'
  displayName: string
  status: ModelLiveStatus
}

function StatusBadge({ status }: { status: ModelLiveStatus }) {
  if (status.isTraining) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full bg-green-900/50 text-green-400 font-medium">
        Training
      </span>
    )
  }
  if (status.inferenceOnline) {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full bg-sky-900/50 text-sky-400 font-medium">
        Online
      </span>
    )
  }
  return (
    <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-500 font-medium">
      Offline
    </span>
  )
}

export function LiveModelCard({ displayName, status }: LiveModelCardProps) {
  const navigate = useNavigate()
  const isActive = status.isTraining || status.inferenceOnline

  return (
    <div className={`bg-zinc-800 border border-zinc-700 rounded-xl overflow-hidden ${!isActive ? 'opacity-60' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-700">
        <span className="text-sm font-semibold text-zinc-200">{displayName}</span>
        <StatusBadge status={status} />
      </div>

      <div className="p-4 space-y-3">
        {/* Training section */}
        {status.isTraining && status.trainingProgress && (
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-zinc-400">
              <span>Step {status.trainingProgress.currentStep.toLocaleString()} / {status.trainingProgress.totalSteps.toLocaleString()}</span>
              <span>{status.trainingProgress.progressPct.toFixed(1)}%</span>
            </div>
            <div className="h-1.5 bg-zinc-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 rounded-full transition-all duration-500"
                style={{ width: `${status.trainingProgress.progressPct}%` }}
              />
            </div>
            {status.trainingProgress.loss !== null && (
              <div className="text-xs text-zinc-500">
                Best loss: <span className="text-zinc-300">{status.trainingProgress.loss.toFixed(4)}</span>
              </div>
            )}
            <button
              onClick={() => navigate('/monitor')}
              className="text-xs text-purple-400 hover:text-purple-300 transition-colors"
            >
              View in Monitor →
            </button>
          </div>
        )}

        {/* Inference section */}
        {status.inferenceOnline && (
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
              <span className="text-xs text-sky-400 font-medium">Ready for translation</span>
            </div>
            {status.loadedModel && (
              <div className="text-xs text-zinc-500 font-mono truncate">{status.loadedModel}</div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!isActive && (
          <div className="text-center py-4 space-y-3">
            <p className="text-sm text-zinc-600">Not active</p>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => navigate('/monitor')}
                className="text-xs px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-300 rounded-lg transition-colors"
              >
                Start Training
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
