import { useEffect, useRef } from 'react'
import type { ParagraphInfo } from '@/api/epub'

interface Props {
  paragraphs: ParagraphInfo[]
  currentIndex: number
  onSelect: (index: number) => void
}

export function ParagraphNavigator({ paragraphs, currentIndex, onSelect }: Props) {
  const activeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [currentIndex])

  return (
    <div className="overflow-y-auto h-full space-y-1 pr-1">
      {paragraphs.map(p => {
        const isCurrent = p.paragraph_index === currentIndex
        return (
          <button
            key={p.id}
            ref={isCurrent ? activeRef : null}
            onClick={() => onSelect(p.paragraph_index)}
            className={`w-full text-left text-xs rounded-lg px-2 py-1.5 transition-colors leading-snug ${
              isCurrent
                ? 'border-l-2 border-violet-500 bg-zinc-800 text-zinc-200'
                : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800'
            }`}
          >
            <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 align-middle ${
              p.is_translated ? 'bg-green-500' : 'bg-zinc-600'
            }`} />
            <span className="line-clamp-2">{p.source_text}</span>
          </button>
        )
      })}
    </div>
  )
}
