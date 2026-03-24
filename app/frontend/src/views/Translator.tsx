import { useEffect, useState } from 'react'
import type { BookSummary, ChapterSummary } from '@/api/epub'
import { getChapters, getLibrary } from '@/api/epub'
import { useStore } from '@/store'
import { LeftPanel } from '@/components/epub/LeftPanel'
import { TranslationWorkspace } from '@/components/epub/TranslationWorkspace'

export function Translator() {
  const [books, setBooks] = useState<BookSummary[]>([])
  const [chapters, setChapters] = useState<ChapterSummary[]>([])

  const selectedBookId = useStore(s => s.selectedBookId)
  const selectedChapterId = useStore(s => s.selectedChapterId)

  const selectedBook = books.find(b => b.id === selectedBookId) ?? null
  const selectedChapter = chapters.find(c => c.id === selectedChapterId) ?? null

  // Load library on mount
  useEffect(() => {
    getLibrary().then(setBooks).catch(() => {})
  }, [])

  // Fetch chapters when selected book changes
  useEffect(() => {
    if (selectedBookId === null) { setChapters([]); return }
    getChapters(selectedBookId).then(setChapters).catch(() => {})
  }, [selectedBookId])

  return (
    <div className="flex h-full overflow-hidden">
      <LeftPanel
        books={books}
        selectedBook={selectedBook}
        onBooksLoaded={setBooks}
      />
      <TranslationWorkspace
        book={selectedBook}
        chapter={selectedChapter}
      />
    </div>
  )
}
