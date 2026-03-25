import { useState } from 'react'

interface ConsensusPanelProps {
  text: string
  done: boolean
  onlineModelCount: number
}

export function ConsensusPanel({ text, done, onlineModelCount }: ConsensusPanelProps) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    if (!text) return
    void navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="bg-zinc-800 border border-purple-700/50 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-purple-700/30">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-purple-300">Consensus</span>
          {onlineModelCount < 3 && onlineModelCount > 0 && (
            <span className="text-xs text-zinc-500 italic">Partial ({onlineModelCount}/3 models)</span>
          )}
        </div>
        {done && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-purple-900/50 text-purple-300">
            Complete
          </span>
        )}
      </div>

      <div className="min-h-[120px] max-h-[300px] overflow-y-auto p-4 font-mono text-sm text-zinc-300 leading-relaxed">
        {text ? (
          <span>
            {text}
            {!done && <span className="animate-pulse">▋</span>}
          </span>
        ) : (
          <span className="text-zinc-600 italic">
            {onlineModelCount === 0
              ? 'No models online'
              : 'Waiting for model outputs…'}
          </span>
        )}
      </div>

      <div className="px-4 py-2 border-t border-purple-700/30 flex justify-end">
        <button
          onClick={handleCopy}
          disabled={!text}
          className="text-xs px-3 py-1 rounded-md bg-zinc-700 text-zinc-300 hover:bg-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
    </div>
  )
}
