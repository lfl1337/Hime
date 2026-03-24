import type { ParagraphInfo } from '@/api/epub'

interface Props {
  paragraphs: ParagraphInfo[]
  currentIndex: number
  onSelect: (index: number) => void
}

export function ParagraphNavigator({ paragraphs, currentIndex, onSelect }: Props) {
  // Show 5 context paragraphs centered on current
  const start = Math.max(0, currentIndex - 2)
  const visible = paragraphs.slice(start, start + 5)

  return (
    <div className="overflow-y-auto space-y-1 pr-1">
      {visible.map(p => {
        const isCurrent = p.paragraph_index === currentIndex
        return (
          <button
            key={p.id}
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
