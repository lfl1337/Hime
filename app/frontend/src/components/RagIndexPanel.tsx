import { useEffect, useState } from 'react'
import type { RagSeriesStats } from '@/api/rag'
import { buildIndex, deleteIndex, getStats } from '@/api/rag'

interface Props {
  book_id: number
  series_id: number | null
}

export function RagIndexPanel({ book_id, series_id }: Props) {
  const [stats, setStats] = useState<RagSeriesStats | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    if (series_id === null) return
    let cancelled = false
    getStats(series_id)
      .then(s => { if (!cancelled) setStats(s) })
      .catch(e => { if (!cancelled) setError(String(e)) })
    return () => { cancelled = true }
  }, [series_id])

  if (series_id === null) {
    return (
      <p className="text-xs text-zinc-500">
        Setze zuerst eine Series-ID, um RAG-Indexing zu aktivieren.
      </p>
    )
  }

  async function handleBuild() {
    setBusy(true)
    setError(null)
    try {
      const r = await buildIndex(book_id)
      setMessage(`${r.new_chunks} neue Chunks indiziert`)
      const s = await getStats(series_id!)
      setStats(s)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  async function handleRebuild() {
    setBusy(true)
    setError(null)
    try {
      await deleteIndex(series_id!)
      const r = await buildIndex(book_id)
      setMessage(`Neu aufgebaut: ${r.new_chunks} Chunks`)
      const s = await getStats(series_id!)
      setStats(s)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 space-y-2 text-xs">
      <div className="flex items-center justify-between text-zinc-400">
        <span>Index-Status</span>
        <span className="text-zinc-200">
          {stats === null ? '\u2014' : stats.chunk_count > 0 ? `${stats.chunk_count} chunks` : 'leer'}
        </span>
      </div>
      {stats?.last_update && (
        <div className="flex items-center justify-between text-zinc-400">
          <span>Zuletzt aktualisiert</span>
          <span className="text-zinc-300 font-mono">{new Date(stats.last_update).toLocaleString()}</span>
        </div>
      )}
      {error && <p className="text-red-400">{error}</p>}
      {message && <p className="text-green-400">{message}</p>}
      <div className="flex gap-2 pt-1">
        <button
          onClick={() => void handleBuild()}
          disabled={busy}
          className="text-xs px-2 py-1 rounded bg-violet-900/40 hover:bg-violet-900/60 text-violet-300 disabled:opacity-50"
        >
          {busy ? '\u2026' : 'Add to series index'}
        </button>
        <button
          onClick={() => void handleRebuild()}
          disabled={busy}
          className="text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 disabled:opacity-50"
        >
          Rebuild index
        </button>
      </div>
    </div>
  )
}
