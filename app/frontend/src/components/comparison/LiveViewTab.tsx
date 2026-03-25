import { LiveModelCard } from './LiveModelCard'
import { useModelPolling } from '../../hooks/useModelPolling'
import { MODEL_CONFIG, MODEL_KEYS } from './modelConfig'

interface LiveViewTabProps {
  active: boolean
}

export function LiveViewTab({ active }: LiveViewTabProps) {
  const { liveStatuses, isLoading } = useModelPolling(active)

  return (
    <div className="space-y-4">
      {isLoading && (
        <p className="text-xs text-zinc-600 animate-pulse">Polling model status…</p>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {MODEL_KEYS.map((key) => (
          <LiveModelCard
            key={key}
            modelKey={key}
            displayName={MODEL_CONFIG[key].displayName}
            status={liveStatuses[key]}
          />
        ))}
      </div>
    </div>
  )
}
