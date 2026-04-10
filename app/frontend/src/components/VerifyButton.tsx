import { useState } from 'react'
import type { VerificationResult } from '@/api/verify'
import { verifyParagraph } from '@/api/verify'

interface Props {
  jp: string
  en: string
  paragraph_id?: number
}

const COLOR: Record<VerificationResult['overall'], string> = {
  pass: 'bg-green-900/50 text-green-300',
  warning: 'bg-amber-900/50 text-amber-300',
  fail: 'bg-red-900/50 text-red-300',
}

export function VerifyButton({ jp, en, paragraph_id }: Props) {
  const [result, setResult] = useState<VerificationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [open, setOpen] = useState(false)
  const [cached, setCached] = useState(false)

  async function run(force = false) {
    setLoading(true)
    try {
      const r = await verifyParagraph(jp, en, paragraph_id, force)
      setResult(r)
      setCached(!force)
      setOpen(true)
    } catch {
      // swallow
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative inline-block">
      <button
        onClick={() => void run(false)}
        disabled={loading || !en}
        className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
          result ? COLOR[result.overall] : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
        } disabled:opacity-50`}
      >
        {loading ? '\u2026' : result ? `verify: ${result.overall}` : 'verify'}
        {cached && result && <span className="ml-1 text-[8px] opacity-70">cached</span>}
      </button>
      {open && result && (
        <div className="absolute z-10 right-0 top-full mt-1 w-72 rounded-lg border border-zinc-700 bg-zinc-950 p-3 shadow-xl space-y-2 text-xs">
          <div className="flex justify-between text-zinc-400">
            <span>Fidelity</span>
            <span className="font-mono text-zinc-200">{result.fidelity_score.toFixed(2)}</span>
          </div>
          <div className="flex justify-between text-zinc-400">
            <span>Register</span>
            <span className={`px-1 rounded ${result.register_match === 'match' ? 'text-green-400' : 'text-amber-400'}`}>
              {result.register_match}
            </span>
          </div>
          <div className="flex justify-between text-zinc-400">
            <span>Names</span>
            <span className={`px-1 rounded ${result.name_check === 'consistent' ? 'text-green-400' : 'text-amber-400'}`}>
              {result.name_check}
            </span>
          </div>
          {result.missing_content.length > 0 && (
            <div>
              <p className="text-zinc-500">Missing:</p>
              <ul className="text-zinc-400 list-disc ml-4">
                {result.missing_content.map((m, i) => <li key={i}>{m}</li>)}
              </ul>
            </div>
          )}
          {result.added_content.length > 0 && (
            <div>
              <p className="text-zinc-500">Added:</p>
              <ul className="text-zinc-400 list-disc ml-4">
                {result.added_content.map((m, i) => <li key={i}>{m}</li>)}
              </ul>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={() => void run(true)}
              className="text-[10px] text-zinc-400 hover:text-zinc-200"
            >
              Re-run
            </button>
            <button
              onClick={() => setOpen(false)}
              className="text-[10px] text-zinc-400 hover:text-zinc-200"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
