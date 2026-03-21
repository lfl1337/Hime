import type { BookSummary } from '@/api/epub'
import { useStore } from '@/store'
import { BookLibrary } from './BookLibrary'
import { ChapterList } from './ChapterList'

interface Props {
  books: BookSummary[]
  selectedBook: BookSummary | null
  onBooksLoaded: (books: BookSummary[]) => void
}

export function LeftPanel({ selectedBook, onBooksLoaded }: Props) {
  const libraryTab = useStore(s => s.libraryTab)
  const setLibraryTab = useStore(s => s.setLibraryTab)

  return (
    <div className="w-80 shrink-0 border-r border-zinc-800 flex flex-col h-full">
      {/* Tabs */}
      <div className="flex border-b border-zinc-800">
        {(['library', 'chapters'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setLibraryTab(tab)}
            className={`flex-1 py-2.5 text-xs font-medium capitalize transition-colors ${
              libraryTab === tab
                ? 'text-violet-400 border-b-2 border-violet-500'
                : 'text-zinc-500 hover:text-zinc-300'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {libraryTab === 'library' ? (
          <BookLibrary onBookSelected={onBooksLoaded} />
        ) : (
          <ChapterList book={selectedBook} onChapterSelected={() => {}} />
        )}
      </div>
    </div>
  )
}
