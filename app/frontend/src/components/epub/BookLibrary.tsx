import { useEffect, useRef, useState } from 'react'
import { getLibrary, importEpub } from '@/api/epub'
import type { BookSummary } from '@/api/epub'
import { useStore } from '@/store'
import { BookCard } from './BookCard'

type SortKey = 'recent' | 'progress' | 'title'

export function BookLibrary({ onBookSelected }: { onBookSelected: (books: BookSummary[]) => void }) {
  const [books, setBooks] = useState<BookSummary[]>([])
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortKey>('recent')
  const [importing, setImporting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const setSelectedBook = useStore(s => s.setSelectedBook)
  const setSelectedChapter = useStore(s => s.setSelectedChapter)
  const setLibraryTab = useStore(s => s.setLibraryTab)

  async function refresh() {
    try {
      const list = await getLibrary()
      setBooks(list)
      onBookSelected(list)
    } catch { /* ignore */ }
  }

  useEffect(() => { void refresh() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleImport(filePaths: string[]) {
    setImporting(true)
    for (const p of filePaths) {
      try { await importEpub(p) } catch { /* ignore individual failures */ }
    }
    setImporting(false)
    await refresh()
  }

  async function handleTauriOpen() {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog')
      const result = await open({
        filters: [{ name: 'EPUB', extensions: ['epub'] }],
        multiple: true,
      })
      if (!result) return
      const paths = (Array.isArray(result) ? result : [result]) as string[]
      await handleImport(paths)
    } catch {
      // Fallback to file input in dev/browser mode
      fileInputRef.current?.click()
    }
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    const paths = files.map(f => (f as { path?: string }).path ?? f.name)
    void handleImport(paths)
  }

  function handleCardClick(book: BookSummary) {
    setSelectedBook(book.id)
    setSelectedChapter(null)
    setLibraryTab('chapters')
  }

  const filtered = books
    .filter(b =>
      b.title.toLowerCase().includes(search.toLowerCase()) ||
      (b.author ?? '').toLowerCase().includes(search.toLowerCase())
    )
    .sort((a, b) => {
      if (sort === 'recent') return (b.imported_at ?? '').localeCompare(a.imported_at ?? '')
      if (sort === 'progress') {
        const pa = a.total_paragraphs ? a.translated_paragraphs / a.total_paragraphs : 0
        const pb = b.total_paragraphs ? b.translated_paragraphs / b.total_paragraphs : 0
        return pb - pa
      }
      return a.title.localeCompare(b.title)
    })

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="p-3 space-y-2 border-b border-zinc-800">
        <button
          onClick={() => void handleTauriOpen()}
          disabled={importing}
          className="w-full px-3 py-2 rounded-lg text-sm bg-violet-700 hover:bg-violet-600 text-white disabled:opacity-50 transition-colors"
        >
          {importing ? 'Importing…' : 'Import EPUB'}
        </button>
        <input ref={fileInputRef} type="file" accept=".epub" multiple className="hidden" onChange={handleFileInput} />
        <input
          type="text"
          placeholder="Search…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="w-full px-2 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:ring-1 focus:ring-violet-600"
        />
        <select
          value={sort}
          onChange={e => setSort(e.target.value as SortKey)}
          className="w-full px-2 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700 text-sm text-zinc-300 focus:outline-none"
        >
          <option value="recent">Recently added</option>
          <option value="progress">By progress</option>
          <option value="title">By title</option>
        </select>
      </div>

      {/* Book grid */}
      <div className="flex-1 overflow-y-auto p-3">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
            <button
              onClick={() => void handleTauriOpen()}
              className="px-5 py-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-sm transition-colors"
            >
              Import EPUB
            </button>
            <p className="text-xs text-zinc-600">or drag & drop an EPUB here</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {filtered.map(book => (
              <BookCard key={book.id} book={book} onClick={() => handleCardClick(book)} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
