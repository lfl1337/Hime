import type { PipelineStage } from '@/api/websocket'

interface PipelineProgressProps {
  currentStage: PipelineStage
}

const STAGES: { key: PipelineStage; label: string }[] = [
  { key: 'stage1', label: 'Stage 1' },
  { key: 'consensus', label: 'Consensus' },
  { key: 'stage2', label: 'Stage 2' },
  { key: 'stage3', label: 'Stage 3' },
]

const STAGE_ORDER: PipelineStage[] = ['stage1', 'consensus', 'stage2', 'stage3', 'complete']

function stageIndex(stage: PipelineStage): number {
  return STAGE_ORDER.indexOf(stage)
}

export function PipelineProgress({ currentStage }: PipelineProgressProps) {
  const currentIdx = stageIndex(currentStage)

  return (
    <div className="flex items-center gap-2 w-full">
      {STAGES.map((s, i) => {
        const idx = stageIndex(s.key)
        const isActive = currentIdx === idx
        const isComplete = currentIdx > idx
        const isError = currentStage === 'error'

        return (
          <div key={s.key} className="flex items-center gap-2 flex-1">
            <div className="flex flex-col items-center flex-1">
              <div
                className={`h-2 w-full rounded-full transition-all duration-500 ${
                  isError && isActive
                    ? 'bg-red-500'
                    : isComplete
                    ? 'bg-[#7C6FCD]'
                    : isActive
                    ? 'bg-[#7C6FCD] animate-pulse'
                    : 'bg-zinc-700'
                }`}
              />
              <span
                className={`mt-1 text-xs ${
                  isActive
                    ? 'text-[#7C6FCD] font-semibold'
                    : isComplete
                    ? 'text-zinc-400'
                    : 'text-zinc-600'
                }`}
              >
                {s.label}
              </span>
            </div>
            {i < STAGES.length - 1 && (
              <div className="w-4 h-px bg-zinc-700 mb-4 flex-shrink-0" />
            )}
          </div>
        )
      })}
    </div>
  )
}
