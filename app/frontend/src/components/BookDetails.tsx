import { useState } from 'react'
import { GlossaryEditor } from './GlossaryEditor'
import { RagIndexPanel } from './RagIndexPanel'

interface Props {
  book_id: number
  series_id: number | null
  series_title: string | null
  onSeriesChange: (id: number | null, title: string | null) => void
  sample_source?: string
  sample_translation?: string
}

export function BookDetails({
  book_id, series_id, series_title, onSeriesChange,
  sample_source, sample_translation,
}: Props) {
  const [open, setOpen] = useState(false)
  const [draftId, setDraftId] = useState(series_id?.toString() ?? '')
  const [draftTitle, setDraftTitle] = useState(series_title ?? '')

  function handleSaveSeries() {
    const idNum = draftId.trim() ? Number(draftId) : null
    const title = draftTitle.trim() || null
    onSeriesChange(idNum, title)
  }

  return (
    <aside className="w-80 border-l border-zinc-800 bg-zinc-950 overflow-y-auto">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 border-b border-zinc-800 flex items-center justify-between"
      >
        <span>Book details</span>
        <span className="text-xs text-zinc-500">{open ? '\u25be' : '\u25b8'}</span>
      </button>
      {open && (
        <div className="p-4 space-y-6">
          <section>
            <h4 className="text-xs font-medium text-zinc-400 mb-2">Series</h4>
            <div className="space-y-2">
              <input
                value={draftId}
                onChange={e => setDraftId(e.target.value)}
                placeholder="Series ID"
                className="w-full text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-200"
              />
              <input
                value={draftTitle}
                onChange={e => setDraftTitle(e.target.value)}
                placeholder="Series title"
                className="w-full text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-200"
              />
              <button
                onClick={handleSaveSeries}
                className="text-xs px-3 py-1 rounded bg-violet-900/40 hover:bg-violet-900/60 text-violet-300"
              >
                Speichern
              </button>
            </div>
          </section>

          <section>
            <h4 className="text-xs font-medium text-zinc-400 mb-2">RAG Index</h4>
            <RagIndexPanel book_id={book_id} series_id={series_id} />
          </section>

          <section>
            <h4 className="text-xs font-medium text-zinc-400 mb-2">Glossar</h4>
            <GlossaryEditor
              book_id={book_id}
              sample_source={sample_source}
              sample_translation={sample_translation}
            />
          </section>
        </div>
      )}
    </aside>
  )
}
