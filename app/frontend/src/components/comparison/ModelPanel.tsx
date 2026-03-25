import { useState } from 'react'
import type { ModelOutput } from '../../types/comparison'

interface ModelPanelProps {
  modelKey: 'gemma' | 'deepseek' | 'qwen32b'
  displayName: string
  accentColor: 'blue' | 'emerald' | 'amber'
  online: boolean
  isTraining: boolean
  output: ModelOutput
}

const ACCENT_BADGE: Record<'blue' | 'emerald' | 'amber', string> = {
  blue:    'bg-blue-900/50 text-blue-300 border border-blue-700/50',
  emerald: 'bg-emerald-900/50 text-emerald-300 border border-emerald-700/50',
  amber:   'bg-amber-900/50 text-amber-300 border border-amber-700/50',
}

export function ModelPanel({ displayName, accentColor, online, isTraining, output }: ModelPanelProps) {
  const [copied, setCopied] = useState(false)

  const statusLabel = isTraining ? 'Training' : online ? 'Online' : 'Offline'
  const statusCls = isTraining
    ? 'bg-green-900/50 text-green-400'
    : online
      ? 'bg-sky-900/50 text-sky-400'
      : 'bg-zinc-800 text-zinc-500'

  const isStreaming = !output.done && !output.error && output.text.length > 0
  const showCursor = isStreaming

  function handleCopy() {
    if (!output.text) return
    void navigator.clipboard.writeText(output.text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={`flex flex-col bg-zinc-800 border border-zinc-700 rounded-xl overflow-hidden ${!online && !isTraining ? 'opacity-60' : ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-700">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-md ${ACCENT_BADGE[accentColor]}`}>
          {displayName}
        </span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusCls}`}>
          {statusLabel}
        </span>
      </div>

      {/* Output area */}
      <div className="flex-1 min-h-[200px] max-h-[400px] overflow-y-auto p-4 font-mono text-sm text-zinc-300 leading-relaxed">
        {output.error ? (
          <span className="text-red-400">{output.error}</span>
        ) : output.text ? (
          <span>
            {output.text}
            {showCursor && <span className="animate-pulse">▋</span>}
          </span>
        ) : (
          <span className="text-zinc-600 italic">
            {online ? 'Waiting for output…' : 'Model offline'}
          </span>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-zinc-700 flex justify-end">
        <button
          onClick={handleCopy}
          disabled={!output.text}
          className="text-xs px-3 py-1 rounded-md bg-zinc-700 text-zinc-300 hover:bg-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
    </div>
  )
}
