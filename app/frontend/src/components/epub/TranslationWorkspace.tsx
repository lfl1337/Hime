import { useEffect, useRef, useState } from 'react'
import { getParagraphs, saveTranslation, exportChapter } from '@/api/epub'
import { createSourceText, startTranslation } from '@/api/translate'
import { usePipeline } from '@/api/websocket'
import { useStore } from '@/store'
import type { BookSummary, ChapterSummary, ParagraphInfo } from '@/api/epub'
import { PipelineProgress } from '@/components/PipelineProgress'
import { ParagraphNavigator } from './ParagraphNavigator'

interface Props {
  book: BookSummary | null
  chapter: ChapterSummary | null
}

export function TranslationWorkspace({ book, chapter }: Props) {
  const [paragraphs, setParagraphs] = useState<ParagraphInfo[]>([])
  const [activeJobId, setActiveJobId] = useState<number | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState('')
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)

  const selectedParagraphIndex = useStore(s => s.selectedParagraphIndex)
  const setSelectedParagraph = useStore(s => s.setSelectedParagraph)

  const pipeline = usePipeline(activeJobId)

  const currentParagraph = paragraphs[selectedParagraphIndex] ?? null

  useEffect(() => {
    if (!chapter) return
    setActiveJobId(null)
    setEditMode(false)
    getParagraphs(chapter.id).then(data => {
      setParagraphs(data)
    }).catch(() => {})
  }, [chapter])

  // When pipeline completes, auto-save
  const savedRef = useRef(false)
  useEffect(() => {
    if (pipeline.isComplete && pipeline.finalOutput && currentParagraph && !savedRef.current) {
      savedRef.current = true
      void saveTranslation(currentParagraph.id, pipeline.finalOutput).then(() => {
        setParagraphs(prev => prev.map(p =>
          p.id === currentParagraph.id
            ? { ...p, is_translated: true, translated_text: pipeline.finalOutput }
            : p
        ))
      })
    }
  }, [pipeline.isComplete]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleTranslate() {
    if (!currentParagraph) return
    setIsStarting(true)
    setActiveJobId(null)
    savedRef.current = false
    try {
      const { id: sourceId } = await createSourceText(
        `${book?.title ?? 'Book'} — ${chapter?.title ?? 'Chapter'} — §${selectedParagraphIndex + 1}`,
        currentParagraph.source_text,
      )
      const { job_id } = await startTranslation(sourceId)
      setActiveJobId(job_id)
    } finally {
      setIsStarting(false)
    }
  }

  async function handleSaveEdit() {
    if (!currentParagraph) return
    setSaving(true)
    await saveTranslation(currentParagraph.id, editText)
    setParagraphs(prev => prev.map(p =>
      p.id === currentParagraph.id
        ? { ...p, is_translated: true, translated_text: editText }
        : p
    ))
    setEditMode(false)
    setSaving(false)
  }

  async function handleSaveAndNext() {
    if (!currentParagraph || !pipeline.finalOutput) return
    setSaving(true)
    await saveTranslation(currentParagraph.id, pipeline.finalOutput)
    setParagraphs(prev => prev.map(p =>
      p.id === currentParagraph.id
        ? { ...p, is_translated: true, translated_text: pipeline.finalOutput }
        : p
    ))
    setSaving(false)
    if (selectedParagraphIndex < paragraphs.length - 1) {
      setSelectedParagraph(selectedParagraphIndex + 1)
      setActiveJobId(null)
    }
  }

  async function handleExport() {
    if (!chapter) return
    setExporting(true)
    try {
      const content = await exportChapter(chapter.id, 'txt')
      const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${chapter.title}.txt`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  // Empty state
  if (!book || !chapter) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center">
        <div className="space-y-2">
          <p className="text-zinc-400 text-lg">Import an EPUB to get started</p>
          <p className="text-zinc-600 text-sm">or drag & drop an EPUB onto the window</p>
        </div>
      </div>
    )
  }

  const isRunning = pipeline.stage !== 'idle' && pipeline.stage !== 'complete' && pipeline.stage !== 'error'

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-zinc-800 bg-zinc-900">
        <span className="text-xs text-zinc-500 truncate">
          {book.title} → {chapter.title}
        </span>
        <div className="flex items-center gap-1 ml-auto shrink-0">
          <button
            onClick={() => setSelectedParagraph(Math.max(0, selectedParagraphIndex - 1))}
            disabled={selectedParagraphIndex === 0}
            className="px-2 py-1 rounded text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-30"
          >
            ←
          </button>
          <span className="text-xs text-zinc-400 tabular-nums">
            {selectedParagraphIndex + 1} / {paragraphs.length}
          </span>
          <button
            onClick={() => setSelectedParagraph(Math.min(paragraphs.length - 1, selectedParagraphIndex + 1))}
            disabled={selectedParagraphIndex >= paragraphs.length - 1}
            className="px-2 py-1 rounded text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-30"
          >
            →
          </button>
        </div>
        {/* Mini progress */}
        <div className="w-24 bg-zinc-800 rounded-full h-1.5 shrink-0">
          <div
            className="bg-violet-600 h-1.5 rounded-full"
            style={{ width: `${chapter.total_paragraphs > 0 ? (chapter.translated_paragraphs / chapter.total_paragraphs) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* Split pane */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Japanese source */}
        <div className="w-1/2 flex flex-col border-r border-zinc-800 overflow-hidden" style={{ background: '#1a1814' }}>
          <div className="p-4 flex-1 overflow-y-auto">
            {currentParagraph ? (
              <p className="text-lg leading-relaxed text-amber-50 jp-text font-serif">
                {currentParagraph.source_text}
              </p>
            ) : (
              <p className="text-zinc-600 text-sm">No paragraph selected</p>
            )}
          </div>
          {/* Paragraph navigator */}
          <div className="h-44 border-t border-zinc-800 p-2 overflow-hidden">
            <ParagraphNavigator
              paragraphs={paragraphs}
              currentIndex={selectedParagraphIndex}
              onSelect={idx => {
                setSelectedParagraph(idx)
                setActiveJobId(null)
                setEditMode(false)
              }}
            />
          </div>
        </div>

        {/* Right: Translation output */}
        <div className="w-1/2 flex flex-col overflow-hidden bg-zinc-950">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Stage indicator */}
            {pipeline.stage !== 'idle' && (
              <PipelineProgress currentStage={pipeline.stage} />
            )}

            {/* Already translated: show saved text */}
            {currentParagraph?.is_translated && !isRunning && !pipeline.finalOutput && (
              <div className="space-y-3">
                {editMode ? (
                  <textarea
                    value={editText}
                    onChange={e => setEditText(e.target.value)}
                    className="w-full h-48 rounded-xl bg-zinc-900 border border-zinc-700 px-4 py-3 text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-violet-600 resize-none"
                  />
                ) : (
                  <p className="text-zinc-200 text-sm leading-relaxed whitespace-pre-wrap">
                    {currentParagraph.translated_text}
                  </p>
                )}
                <button
                  onClick={() => void handleTranslate()}
                  disabled={isStarting}
                  className="text-xs text-zinc-500 hover:text-violet-400 underline"
                >
                  Re-translate
                </button>
              </div>
            )}

            {/* Pipeline output (streaming or complete) */}
            {(pipeline.finalOutput || isRunning) && (
              <div>
                <p className="text-zinc-200 text-sm leading-relaxed whitespace-pre-wrap">
                  {pipeline.finalOutput || (
                    <span className="text-zinc-600 italic animate-pulse">Translating…</span>
                  )}
                </p>
                {pipeline.durationMs && (
                  <p className="mt-2 text-xs text-zinc-600">
                    Completed in {(pipeline.durationMs / 1000).toFixed(1)}s
                  </p>
                )}
              </div>
            )}

            {/* Error */}
            {pipeline.error && (
              <p className="text-sm text-red-400">{pipeline.error}</p>
            )}

            {/* Not translated, not running */}
            {!currentParagraph?.is_translated && !isRunning && !pipeline.finalOutput && activeJobId === null && (
              <p className="text-zinc-600 text-sm">Click Translate to start</p>
            )}
          </div>

          {/* Bottom actions */}
          <div className="border-t border-zinc-800 px-4 py-3 flex items-center gap-2 bg-zinc-900 flex-wrap">
            {!editMode ? (
              <>
                <button
                  onClick={() => void handleTranslate()}
                  disabled={isRunning || isStarting || !currentParagraph}
                  className="px-4 py-2 rounded-lg text-sm bg-violet-700 hover:bg-violet-600 text-white disabled:opacity-40 transition-colors"
                >
                  {isStarting ? 'Starting…' : isRunning ? 'Translating…' : 'Translate'}
                </button>
                {pipeline.isComplete && (
                  <button
                    onClick={() => void handleSaveAndNext()}
                    disabled={saving}
                    className="px-4 py-2 rounded-lg text-sm bg-green-800 hover:bg-green-700 text-green-100 disabled:opacity-40 transition-colors"
                  >
                    {saving ? 'Saving…' : 'Save & next'}
                  </button>
                )}
                {currentParagraph?.is_translated && (
                  <button
                    onClick={() => {
                      setEditText(currentParagraph.translated_text ?? '')
                      setEditMode(true)
                    }}
                    className="px-3 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
                  >
                    Edit
                  </button>
                )}
                {pipeline.finalOutput && (
                  <button
                    onClick={() => void navigator.clipboard.writeText(pipeline.finalOutput)}
                    className="px-3 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
                  >
                    Copy
                  </button>
                )}
                <button
                  onClick={() => void handleExport()}
                  disabled={exporting}
                  className="ml-auto px-3 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 disabled:opacity-40 transition-colors"
                >
                  {exporting ? 'Exporting…' : 'Export chapter'}
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => void handleSaveEdit()}
                  disabled={saving}
                  className="px-4 py-2 rounded-lg text-sm bg-violet-700 hover:bg-violet-600 text-white disabled:opacity-40"
                >
                  {saving ? 'Saving…' : 'Save'}
                </button>
                <button
                  onClick={() => setEditMode(false)}
                  className="px-3 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
                >
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
