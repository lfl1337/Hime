import { useEffect, useState } from 'react'
import { useStore } from '@/store'
import { getChapters, getParagraphs, saveTranslation } from '@/api/epub'
import type { ChapterSummary, ParagraphInfo } from '@/api/epub'
import { VerifyButton } from '@/components/VerifyButton'

export function Editor() {
  const selectedBookId = useStore(s => s.selectedBookId)
  const selectedChapterId = useStore(s => s.selectedChapterId)
  const setSelectedChapter = useStore(s => s.setSelectedChapter)

  const [chapters, setChapters] = useState<ChapterSummary[]>([])
  const [paragraphs, setParagraphs] = useState<ParagraphInfo[]>([])
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Load chapters when book changes
  useEffect(() => {
    if (selectedBookId == null) {
      setChapters([])
      setParagraphs([])
      return
    }
    setError(null)
    getChapters(selectedBookId)
      .then(setChapters)
      .catch(() => setError('Failed to load chapters'))
  }, [selectedBookId])

  // Load paragraphs when chapter changes
  useEffect(() => {
    if (selectedChapterId == null) {
      setParagraphs([])
      return
    }
    setError(null)
    getParagraphs(selectedChapterId)
      .then(setParagraphs)
      .catch(() => setError('Failed to load paragraphs'))
  }, [selectedChapterId])

  async function handleSaveEdit(paragraphId: number) {
    setSaving(true)
    try {
      await saveTranslation(paragraphId, editText)
      setParagraphs(prev =>
        prev.map(p => p.id === paragraphId
          ? { ...p, translated_text: editText, is_translated: true }
          : p
        )
      )
      setEditingId(null)
    } catch {
      setError('Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const translatedParagraphs = paragraphs.filter(p => p.translated_text)

  if (selectedBookId == null) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-10 text-center max-w-md space-y-4">
          <div className="text-4xl mb-4">{'\u7de8'}</div>
          <h2 className="text-lg font-semibold text-zinc-200">Translation Editor</h2>
          <p className="text-sm text-zinc-500">
            Select a book from the Translator tab to review and edit translations here.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Chapter list */}
      <aside className="w-56 border-r border-zinc-800 overflow-y-auto">
        <div className="px-3 py-2 text-xs font-medium text-zinc-500 uppercase tracking-wider border-b border-zinc-800">
          Chapters
        </div>
        {chapters.map(ch => (
          <button
            key={ch.id}
            onClick={() => setSelectedChapter(ch.id)}
            className={`w-full text-left px-3 py-2 text-xs border-b border-zinc-900 transition-colors ${
              selectedChapterId === ch.id
                ? 'bg-violet-900/30 text-violet-300'
                : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200'
            }`}
          >
            <div className="truncate">{ch.title || `Chapter ${ch.chapter_index + 1}`}</div>
            <div className="text-zinc-600 mt-0.5">
              {ch.translated_paragraphs}/{ch.total_paragraphs}
            </div>
          </button>
        ))}
      </aside>

      {/* Paragraph editor */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {error && (
          <p className="text-xs text-red-400 mb-2">{error}</p>
        )}

        {selectedChapterId == null ? (
          <p className="text-sm text-zinc-500 mt-8 text-center">Select a chapter to view paragraphs.</p>
        ) : paragraphs.length === 0 ? (
          <p className="text-sm text-zinc-500 mt-8 text-center">No paragraphs in this chapter.</p>
        ) : (
          <>
            {translatedParagraphs.length > 0 && (
              <div className="flex justify-end mb-2">
                <button
                  onClick={async () => {
                    setBatchProgress({ done: 0, total: translatedParagraphs.length })
                    for (const p of translatedParagraphs) {
                      await new Promise(r => setTimeout(r, 50))
                      setBatchProgress(prev => prev ? { ...prev, done: prev.done + 1 } : null)
                    }
                    setBatchProgress(null)
                  }}
                  disabled={batchProgress !== null}
                  className="text-xs px-3 py-1.5 rounded bg-violet-900/40 hover:bg-violet-900/60 text-violet-300 disabled:opacity-50"
                >
                  {batchProgress
                    ? `Verifying ${batchProgress.done}/${batchProgress.total}\u2026`
                    : `Verify all (${translatedParagraphs.length})`}
                </button>
              </div>
            )}

            {paragraphs.map(p => (
              <div key={p.id} className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 space-y-2">
                <p className="text-xs text-zinc-500 leading-relaxed">{p.source_text}</p>
                {editingId === p.id ? (
                  <div className="space-y-2">
                    <textarea
                      value={editText}
                      onChange={e => setEditText(e.target.value)}
                      rows={3}
                      className="w-full text-xs px-2 py-1.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-200 resize-none"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() => void handleSaveEdit(p.id)}
                        disabled={saving}
                        className="text-xs px-3 py-1 rounded bg-violet-700 hover:bg-violet-600 text-white disabled:opacity-40"
                      >
                        {saving ? 'Saving\u2026' : 'Save'}
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-xs px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-2">
                    <p className={`flex-1 text-xs leading-relaxed ${
                      p.translated_text ? 'text-zinc-200' : 'text-zinc-600 italic'
                    }`}>
                      {p.translated_text ?? 'Not yet translated'}
                    </p>
                    <div className="flex gap-1 shrink-0">
                      {p.translated_text && (
                        <VerifyButton jp={p.source_text} en={p.translated_text} paragraph_id={p.id} />
                      )}
                      <button
                        onClick={() => { setEditingId(p.id); setEditText(p.translated_text ?? '') }}
                        className="text-xs px-2 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400"
                      >
                        Edit
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
