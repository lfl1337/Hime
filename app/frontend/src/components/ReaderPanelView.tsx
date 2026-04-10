import { useState } from 'react'
import type { ReviewFinding } from '@/api/review'
import { runReview } from '@/api/review'

interface Props {
  translation: string
  source: string | null
  onRerun?: (paragraphIds: (number | null)[]) => void
}

const READERS = [
  { id: 'name_consistency',     label: 'Namen' },
  { id: 'register',             label: 'Register' },
  { id: 'omissions',            label: 'Auslassungen' },
  { id: 'natural_flow',         label: 'Natürlicher Fluss' },
  { id: 'emotional_continuity', label: 'Emotion' },
  { id: 'yuri_register',        label: 'Yuri-Register' },
] as const

const SEVERITY_STYLE: Record<ReviewFinding['severity'], string> = {
  info: 'bg-zinc-800 text-zinc-300',
  warning: 'bg-amber-900/50 text-amber-300',
  error: 'bg-red-900/50 text-red-300',
}

export function ReaderPanelView({ translation, source, onRerun }: Props) {
  const [findings, setFindings] = useState<ReviewFinding[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  async function run() {
    setLoading(true)
    setError(null)
    try {
      const resp = await runReview({ translation, source, auto_rerun: false })
      setFindings(resp.findings)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const errorIds = findings.filter(f => f.severity === 'error').map(f => f.paragraph_id)

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-zinc-300">Reader Panel (6 critics)</h3>
        <button
          onClick={() => void run()}
          disabled={loading || !translation}
          className="text-xs px-3 py-1 rounded bg-violet-900/40 hover:bg-violet-900/60 text-violet-300 disabled:opacity-50 transition-colors"
        >
          {loading ? 'Prüfe\u2026' : 'Prüfen'}
        </button>
      </div>
      {error && <p className="text-xs text-red-400 mb-2">{error}</p>}
      <div className="grid grid-cols-2 gap-2">
        {READERS.map(r => {
          const readerFindings = findings.filter(f => f.reader === r.id)
          const worst = readerFindings.reduce<ReviewFinding['severity']>(
            (acc, f) => f.severity === 'error' ? 'error' : acc === 'error' ? 'error' : f.severity,
            'info',
          )
          const isOpen = expanded === r.id
          return (
            <div key={r.id} className="rounded-lg border border-zinc-800 bg-zinc-950 p-2">
              <button
                onClick={() => setExpanded(isOpen ? null : r.id)}
                className="flex w-full items-center justify-between text-xs"
              >
                <span className="text-zinc-300">{r.label}</span>
                <span className={`px-1.5 py-0.5 rounded ${
                  readerFindings.length === 0 ? 'bg-zinc-800 text-zinc-500' : SEVERITY_STYLE[worst]
                }`}>
                  {readerFindings.length}
                </span>
              </button>
              {isOpen && readerFindings.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {readerFindings.map((f, i) => (
                    <li key={i} className="text-[10px] text-zinc-400">
                      <span className={`inline-block px-1 rounded mr-1 ${SEVERITY_STYLE[f.severity]}`}>
                        {f.severity}
                      </span>
                      {f.finding}
                      {f.suggestion && <span className="text-zinc-500"> — {f.suggestion}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )
        })}
      </div>
      {errorIds.length > 0 && onRerun && (
        <button
          onClick={() => onRerun(errorIds)}
          className="mt-3 w-full text-xs px-3 py-2 rounded bg-red-900/40 hover:bg-red-900/60 text-red-300 transition-colors"
        >
          {errorIds.length} markierte Absätze neu übersetzen
        </button>
      )}
    </div>
  )
}
