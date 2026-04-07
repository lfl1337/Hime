import { useState, memo } from 'react'
import { MODEL_CONFIG, type ModelKey, MODEL_KEYS } from './comparison/modelConfig'

interface Stage1PanelProps {
  stage1Tokens: Record<string, string>
  stage1Complete: Record<string, string>
  modelErrors: Record<string, string>
  modelUnavailable: Record<string, string>
  isStage1Active: boolean
  isStage1Done: boolean
}

const ACCENT_CLASSES: Record<string, { border: string; text: string; bg: string }> = {
  blue:    { border: 'border-blue-600',    text: 'text-blue-400',    bg: 'bg-blue-900/20' },
  emerald: { border: 'border-emerald-600', text: 'text-emerald-400', bg: 'bg-emerald-900/20' },
  amber:   { border: 'border-amber-600',   text: 'text-amber-400',  bg: 'bg-amber-900/20' },
}

const ModelCard = memo(function ModelCard({
  modelKey,
  tokens,
  complete,
  error,
  unavailable,
  isActive,
}: {
  modelKey: ModelKey
  tokens: string
  complete: string
  error: string | null
  unavailable: string | null
  isActive: boolean
}) {
  const config = MODEL_CONFIG[modelKey]
  const accent = ACCENT_CLASSES[config.accentColor] ?? ACCENT_CLASSES.blue
  const output = complete || tokens
  const isDone = !!complete
  const isOffline = !!unavailable
  const hasError = !!error

  return (
    <div className={`flex-1 min-w-0 rounded-lg border ${accent.border} bg-zinc-900 overflow-hidden`}>
      {/* Header */}
      <div className={`px-3 py-1.5 flex items-center justify-between ${accent.bg}`}>
        <span className={`text-xs font-medium ${accent.text}`}>{config.displayName}</span>
        {isOffline && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-400">Offline</span>
        )}
        {hasError && !isOffline && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/50 text-red-400">Error</span>
        )}
        {isDone && !hasError && !isOffline && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-900/50 text-green-400">Done</span>
        )}
        {isActive && !isDone && !hasError && !isOffline && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/50 text-violet-400 animate-pulse">Streaming</span>
        )}
      </div>
      {/* Content */}
      <div className="px-3 py-2 h-32 overflow-y-auto text-xs text-zinc-300 leading-relaxed">
        {isOffline ? (
          <p className="text-zinc-600 italic">{unavailable}</p>
        ) : hasError ? (
          <p className="text-red-400 italic">{error}</p>
        ) : output ? (
          <>
            {output}
            {isActive && !isDone && <span className="text-violet-400 animate-pulse">▋</span>}
          </>
        ) : isActive ? (
          <p className="text-zinc-600 italic animate-pulse">Waiting for tokens…</p>
        ) : (
          <p className="text-zinc-700 italic">Idle</p>
        )}
      </div>
    </div>
  )
})

export function Stage1Panel({
  stage1Tokens,
  stage1Complete,
  modelErrors,
  modelUnavailable,
  isStage1Active,
  isStage1Done,
}: Stage1PanelProps) {
  const [collapsed, setCollapsed] = useState(false)

  if (!isStage1Active && !isStage1Done) return null

  return (
    <div className="space-y-2">
      <button
        onClick={() => setCollapsed(prev => !prev)}
        className="flex items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <span className="transform transition-transform" style={{ transform: collapsed ? 'rotate(-90deg)' : 'rotate(0deg)' }}>
          ▼
        </span>
        Stage 1 — Parallel Translation
        {isStage1Done && (
          <span className="text-green-500 text-[10px]">✓ Complete</span>
        )}
      </button>

      {!collapsed && (
        <div className="flex gap-2">
          {MODEL_KEYS.map(key => (
            <ModelCard
              key={key}
              modelKey={key}
              tokens={stage1Tokens[key] ?? ''}
              complete={stage1Complete[key] ?? ''}
              error={modelErrors[key] ?? null}
              unavailable={modelUnavailable[key] ?? null}
              isActive={isStage1Active}
            />
          ))}
        </div>
      )}
    </div>
  )
}
