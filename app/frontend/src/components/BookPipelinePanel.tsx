// app/frontend/src/components/BookPipelinePanel.tsx
import { useState } from 'react'
import { useBookPipelineV2 } from '@/api/useBookPipelineV2'
import type { BookSummary } from '@/api/epub'
import type { SegmentProgress } from '@/api/pipeline_v2'

interface Props {
  book: BookSummary
}

const STAGE_LABELS: Record<string, string> = {
  stage1: 'S1',
  stage2: 'S2',
  stage3: 'S3',
  stage4: 'S4',
  complete: '✓',
  error: '✗',
  pending: '…',
}

const STAGE_COLORS: Record<string, string> = {
  stage1: 'bg-blue-800 text-blue-300',
  stage2: 'bg-indigo-800 text-indigo-300',
  stage3: 'bg-violet-800 text-violet-300',
  stage4: 'bg-purple-800 text-purple-300',
  complete: 'bg-emerald-900 text-emerald-300',
  error: 'bg-red-900 text-red-300',
  pending: 'bg-zinc-800 text-zinc-500',
}

function SegmentRow({ seg }: { seg: SegmentProgress }) {
  const stageColor = STAGE_COLORS[seg.status] ?? STAGE_COLORS.pending
  const verdictBadge = seg.verdict === 'retry'
    ? <span className="ml-1 text-[9px] px-1 rounded bg-amber-900/60 text-amber-400">retry×{seg.retryCount}</span>
    : seg.verdict === 'okay'
    ? <span className="ml-1 text-[9px] px-1 rounded bg-emerald-900/40 text-emerald-500">ok</span>
    : null

  return (
    <div className="flex items-center gap-2 py-0.5">
      <span className="text-[10px] text-zinc-600 w-8 text-right">#{seg.index + 1}</span>
      <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${stageColor}`}>
        {STAGE_LABELS[seg.status] ?? '?'}
      </span>
      {verdictBadge}
      {seg.status === 'complete' && seg.translation && (
        <span className="text-[10px] text-zinc-500 truncate max-w-[200px]">
          {seg.translation.slice(0, 60)}…
        </span>
      )}
    </div>
  )
}

export function BookPipelinePanel({ book }: Props) {
  const { state, start, reset } = useBookPipelineV2()
  const [open, setOpen] = useState(false)

  const isRunning = state.status === 'translating'
  const isDone = state.status === 'complete'
  const isError = state.status === 'error'
  const progressPct = state.totalSegments > 0
    ? Math.round((state.completedSegments / state.totalSegments) * 100)
    : 0

  const visibleSegments = Object.values(state.segments)
    .sort((a, b) => b.index - a.index)
    .slice(0, 8)

  return (
    <div className="border-t border-zinc-800 mt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 flex items-center justify-between"
      >
        <span>Pipeline v2 — Full Book</span>
        <span className="text-xs text-zinc-500">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          <div className="flex items-center gap-2">
            {state.status === 'idle' && (
              <button
                onClick={() => start(book.id)}
                className="text-xs px-3 py-1.5 rounded bg-violet-900/50 hover:bg-violet-900/70 text-violet-300 transition-colors"
              >
                Translate full book
              </button>
            )}
            {isRunning && (
              <div className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border border-zinc-600 border-t-zinc-300" />
                <span className="text-xs text-zinc-400">
                  {state.completedSegments}/{state.totalSegments} segments
                </span>
              </div>
            )}
            {(isDone || isError) && (
              <button
                onClick={reset}
                className="text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400"
              >
                Reset
              </button>
            )}
          </div>

          {(isRunning || isDone) && state.totalSegments > 0 && (
            <div>
              <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                <span>{progressPct}% complete</span>
                <span>{state.completedSegments}/{state.totalSegments}</span>
              </div>
              <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-violet-600 transition-all duration-300"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          )}

          {isError && state.error && (
            <p className="text-xs text-red-400">{state.error}</p>
          )}

          {isDone && state.epubPath && (
            <div className="rounded-lg border border-emerald-800/50 bg-emerald-950/30 p-3">
              <p className="text-xs text-emerald-400 font-medium mb-1">Translation complete!</p>
              <p className="text-[10px] text-zinc-500 font-mono break-all">{state.epubPath}</p>
            </div>
          )}

          {visibleSegments.length > 0 && (
            <div className="space-y-0.5 max-h-40 overflow-y-auto">
              {visibleSegments.map(seg => (
                <SegmentRow key={seg.paragraphId} seg={seg} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
