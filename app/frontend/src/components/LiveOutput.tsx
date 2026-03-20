import { useEffect, useRef } from 'react'

interface LiveOutputProps {
  text: string
  label?: string
  isActive: boolean
  isError?: boolean
}

export function LiveOutput({ text, label, isActive, isError }: LiveOutputProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (isActive) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [text, isActive])

  return (
    <div
      className={`flex flex-col rounded-lg border overflow-hidden ${
        isError
          ? 'border-red-800'
          : isActive
          ? 'border-[#7C6FCD]/60'
          : 'border-zinc-800'
      }`}
    >
      {label && (
        <div
          className={`px-3 py-1.5 text-xs font-medium border-b flex items-center gap-2 ${
            isError
              ? 'bg-red-950/40 border-red-800 text-red-400'
              : isActive
              ? 'bg-[#7C6FCD]/10 border-[#7C6FCD]/30 text-[#7C6FCD]'
              : 'bg-zinc-900 border-zinc-800 text-zinc-500'
          }`}
        >
          {isActive && !isError && (
            <span className="h-1.5 w-1.5 rounded-full bg-[#7C6FCD] animate-pulse" />
          )}
          {label}
        </div>
      )}
      <div className="relative h-40 overflow-y-auto bg-zinc-950 p-3">
        <pre className="text-xs text-zinc-300 whitespace-pre-wrap break-words font-mono jp-text leading-relaxed">
          {text || (
            <span className="text-zinc-600 italic">
              {isActive ? 'Waiting…' : 'No output'}
            </span>
          )}
        </pre>
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
