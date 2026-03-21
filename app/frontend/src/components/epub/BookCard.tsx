import type { BookSummary } from '@/api/epub'

interface Props {
  book: BookSummary
  onClick: () => void
}

const STATUS_BADGE: Record<BookSummary['status'], string> = {
  not_started: 'bg-zinc-700 text-zinc-400',
  in_progress: 'bg-violet-900/60 text-violet-300 animate-pulse',
  complete: 'bg-green-900/50 text-green-400',
}

const STATUS_LABEL: Record<BookSummary['status'], string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  complete: 'Complete',
}

function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / 86_400_000)
  if (days === 0) return 'today'
  if (days === 1) return '1 day ago'
  return `${days} days ago`
}

export function BookCard({ book, onClick }: Props) {
  const progress = book.total_paragraphs > 0
    ? (book.translated_paragraphs / book.total_paragraphs) * 100
    : 0

  return (
    <button
      onClick={onClick}
      className="text-left rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden hover:border-violet-700 transition-colors"
    >
      {/* Cover */}
      <div className="h-40 bg-zinc-950 flex items-center justify-center overflow-hidden">
        {book.cover_image_b64 ? (
          <img
            src={`data:image/jpeg;base64,${book.cover_image_b64}`}
            alt={book.title}
            className="h-full w-full object-cover"
          />
        ) : (
          <span className="text-5xl text-zinc-700 select-none">本</span>
        )}
      </div>

      {/* Info */}
      <div className="p-3 space-y-2">
        <div>
          <p className="text-sm font-medium text-zinc-200 line-clamp-2">{book.title}</p>
          {book.author && (
            <p className="text-xs text-zinc-500 mt-0.5 truncate">{book.author}</p>
          )}
        </div>

        {/* Progress bar */}
        <div>
          <div className="w-full bg-zinc-800 rounded-full h-1.5 mb-1">
            <div
              className="bg-violet-600 h-1.5 rounded-full transition-all"
              style={{ width: `${Math.min(progress, 100)}%` }}
            />
          </div>
          <p className="text-xs text-zinc-600">
            {book.translated_paragraphs} / {book.total_paragraphs} paragraphs
          </p>
        </div>

        <div className="flex items-center justify-between">
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${STATUS_BADGE[book.status]}`}>
            {STATUS_LABEL[book.status]}
          </span>
          {book.last_accessed && (
            <span className="text-xs text-zinc-600">{timeAgo(book.last_accessed)}</span>
          )}
        </div>
      </div>
    </button>
  )
}
