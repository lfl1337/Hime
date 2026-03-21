import { useEffect, useState } from 'react'
import { getChapters, getParagraphs } from '@/api/epub'
import type { BookSummary, ChapterSummary } from '@/api/epub'
import { useStore } from '@/store'

const STATUS_DOT: Record<ChapterSummary['status'], string> = {
  not_started: 'bg-zinc-600',
  in_progress: 'bg-yellow-400',
  complete: 'bg-green-500',
}

interface Props {
  book: BookSummary | null
  onChapterSelected: () => void
}

export function ChapterList({ book, onChapterSelected }: Props) {
  const [chapters, setChapters] = useState<ChapterSummary[]>([])
  const setSelectedChapter = useStore(s => s.setSelectedChapter)
  const setSelectedParagraph = useStore(s => s.setSelectedParagraph)
  const setLibraryTab = useStore(s => s.setLibraryTab)

  useEffect(() => {
    if (!book) return
    getChapters(book.id).then(setChapters).catch(() => {})
  }, [book])

  function handleChapterClick(ch: ChapterSummary) {
    setSelectedChapter(ch.id)
    setSelectedParagraph(0)
    onChapterSelected()
    void getParagraphs(ch.id) // prefetch
  }

  if (!book) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-600 text-sm">
        Select a book first
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-3 border-b border-zinc-800">
        <button
          onClick={() => setLibraryTab('library')}
          className="text-xs text-zinc-500 hover:text-zinc-300 mb-2 flex items-center gap-1"
        >
          ← Library
        </button>
        <p className="text-sm font-semibold text-zinc-200 line-clamp-2">{book.title}</p>
        {book.author && <p className="text-xs text-zinc-500 mt-0.5">{book.author}</p>}
      </div>

      {/* Chapter list */}
      <div className="flex-1 overflow-y-auto">
        {chapters.map(ch => {
          const progress = ch.total_paragraphs > 0
            ? (ch.translated_paragraphs / ch.total_paragraphs) * 100
            : 0
          return (
            <button
              key={ch.id}
              onClick={() => handleChapterClick(ch)}
              className="w-full text-left px-3 py-3 border-b border-zinc-800 hover:bg-zinc-800 transition-colors"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[ch.status]}`} />
                <span className="text-sm text-zinc-200 line-clamp-1">{ch.title}</span>
              </div>
              <div className="ml-4">
                <div className="w-full bg-zinc-700 rounded-full h-1 mb-1">
                  <div
                    className="bg-violet-600 h-1 rounded-full transition-all"
                    style={{ width: `${Math.min(progress, 100)}%` }}
                  />
                </div>
                <p className="text-xs text-zinc-600">
                  {ch.translated_paragraphs} / {ch.total_paragraphs} paragraphs
                </p>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
