import { useState } from 'react'
import { VerifyButton } from '@/components/VerifyButton'
import { verifyParagraph } from '@/api/verify'

export function Editor() {
  const [batchProgress, setBatchProgress] = useState<{ done: number; total: number } | null>(null)

  // Placeholder paragraphs — will be wired to real data when Editor gets full implementation
  const paragraphs: { id: number; source_text: string; translated_text: string | null }[] = []

  async function verifyAll() {
    const translatedParagraphs = paragraphs.filter(p => p.translated_text)
    if (translatedParagraphs.length === 0) return
    setBatchProgress({ done: 0, total: translatedParagraphs.length })
    for (const p of translatedParagraphs) {
      await verifyParagraph(p.source_text, p.translated_text!, p.id)
      setBatchProgress(prev => prev ? { ...prev, done: prev.done + 1 } : null)
    }
    setBatchProgress(null)
  }

  return (
    <div className="flex items-center justify-center h-full">
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-10 text-center max-w-md space-y-4">
        <div className="text-4xl mb-4">{'\u7de8'}</div>
        <h2 className="text-lg font-semibold text-zinc-200 mb-2">
          Translation Editor
        </h2>
        <p className="text-sm text-zinc-500">
          Review and edit saved translations before exporting.
        </p>
        {paragraphs.length > 0 && (
          <div className="space-y-2">
            <button
              onClick={() => void verifyAll()}
              disabled={batchProgress !== null}
              className="text-xs px-3 py-1.5 rounded bg-violet-900/40 hover:bg-violet-900/60 text-violet-300 disabled:opacity-50"
            >
              {batchProgress ? `Verifying ${batchProgress.done}/${batchProgress.total}...` : 'Verify all'}
            </button>
            {paragraphs.map(p => (
              <div key={p.id} className="flex items-center gap-2 text-xs text-zinc-400">
                <span className="truncate flex-1">{p.source_text.slice(0, 40)}...</span>
                {p.translated_text && (
                  <VerifyButton jp={p.source_text} en={p.translated_text} paragraph_id={p.id} />
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
