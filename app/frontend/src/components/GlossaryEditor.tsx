import { useEffect, useState } from 'react'
import type { GlossaryTerm } from '@/api/glossary'
import { addTerm, autoExtract, deleteTerm, getGlossary, updateTerm } from '@/api/glossary'

interface Props {
  book_id: number
  sample_source?: string
  sample_translation?: string
}

export function GlossaryEditor({ book_id, sample_source = '', sample_translation = '' }: Props) {
  const [terms, setTerms] = useState<GlossaryTerm[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState({ source_term: '', target_term: '', category: '', notes: '' })

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getGlossary(book_id)
      .then(g => { if (!cancelled) setTerms(g.terms) })
      .catch(e => { if (!cancelled) setError(String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [book_id])

  async function handleAdd() {
    if (!draft.source_term || !draft.target_term) return
    try {
      const t = await addTerm(book_id, {
        source_term: draft.source_term,
        target_term: draft.target_term,
        category: draft.category || null,
        notes: draft.notes || null,
        is_locked: false,
      })
      setTerms(prev => [...prev, t])
      setDraft({ source_term: '', target_term: '', category: '', notes: '' })
    } catch (e) {
      setError(String(e))
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteTerm(book_id, id)
      setTerms(prev => prev.filter(t => t.id !== id))
    } catch (e) {
      setError(String(e))
    }
  }

  async function handleToggleLock(t: GlossaryTerm) {
    if (t.id === null) return
    const updated = await updateTerm(book_id, t.id, { is_locked: !t.is_locked })
    setTerms(prev => prev.map(x => x.id === t.id ? updated : x))
  }

  async function handleAutoExtract() {
    if (!sample_source || !sample_translation) {
      setError('Kein Beispieltext verfügbar \u2014 öffne ein übersetztes Kapitel')
      return
    }
    const added = await autoExtract(book_id, sample_source, sample_translation)
    setTerms(prev => [...prev, ...added])
  }

  if (loading) return <p className="text-xs text-zinc-500 animate-pulse">Lade Glossar\u2026</p>

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="rounded border border-zinc-800 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-zinc-900 text-zinc-400">
            <tr>
              <th className="text-left px-2 py-1">Source</th>
              <th className="text-left px-2 py-1">Target</th>
              <th className="text-left px-2 py-1">Cat</th>
              <th className="text-left px-2 py-1">Lock</th>
              <th className="text-left px-2 py-1"></th>
            </tr>
          </thead>
          <tbody>
            {terms.map(t => (
              <tr key={t.id} className="border-t border-zinc-800">
                <td className="px-2 py-1 font-mono text-zinc-300">{t.source_term}</td>
                <td className="px-2 py-1 text-zinc-300">{t.target_term}</td>
                <td className="px-2 py-1 text-zinc-500">{t.category ?? '\u2014'}</td>
                <td className="px-2 py-1">
                  <button
                    onClick={() => void handleToggleLock(t)}
                    className="text-zinc-500 hover:text-zinc-300"
                  >
                    {t.is_locked ? '\ud83d\udd12' : '\ud83d\udd13'}
                  </button>
                </td>
                <td className="px-2 py-1 text-right">
                  <button
                    onClick={() => t.id !== null && void handleDelete(t.id)}
                    className="text-red-500 hover:text-red-300"
                  >
                    \u2715
                  </button>
                </td>
              </tr>
            ))}
            {terms.length === 0 && (
              <tr>
                <td colSpan={5} className="px-2 py-2 text-center text-zinc-600">Noch keine Begriffe</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <input
          value={draft.source_term}
          onChange={e => setDraft({ ...draft, source_term: e.target.value })}
          placeholder="Source (jp)"
          className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-200"
        />
        <input
          value={draft.target_term}
          onChange={e => setDraft({ ...draft, target_term: e.target.value })}
          placeholder="Target (en)"
          className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-200"
        />
        <input
          value={draft.category}
          onChange={e => setDraft({ ...draft, category: e.target.value })}
          placeholder="Category (name|place|...)"
          className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-200"
        />
        <input
          value={draft.notes}
          onChange={e => setDraft({ ...draft, notes: e.target.value })}
          placeholder="Notes"
          className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-200"
        />
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => void handleAdd()}
          className="text-xs px-3 py-1 rounded bg-violet-900/40 hover:bg-violet-900/60 text-violet-300"
        >
          Begriff hinzufügen
        </button>
        <button
          onClick={() => void handleAutoExtract()}
          className="text-xs px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
        >
          Begriffe automatisch vorschlagen
        </button>
      </div>
    </div>
  )
}
