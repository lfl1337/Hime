import { useState } from 'react'

const TEXT = `Stage 1 — Drei Modelle übersetzen parallel:
  \u2022 Qwen 2.5 32B   — fein-getuned auf JP\u2192EN Light Novels
  \u2022 Gemma 3 12B    — Googles Architektur, andere Perspektive
  \u2022 DeepSeek R1 32B — Reasoning-orientiert
Plus: JMdict-Lexikon als algorithmischer Anker für Vollständigkeit

Stage 1.5 — Konsens:
  Ein viertes Modell vergleicht alle drei Entwürfe und erstellt
  eine Konsens-Übersetzung, die das Beste aus allen kombiniert.

Stage 2 — Verfeinerung:
  Qwen 2.5 72B verbessert Fluss und Nuance.

Stage 3 — Politur:
  Qwen 2.5 14B macht den finalen Schliff.

Nach der Pipeline — Reader-Panel:
  6 Leser-Personas prüfen das Ergebnis aus verschiedenen
  Perspektiven (Namenskonsistenz, Register, Emotion, etc.)
  und markieren Stellen für mögliche Überarbeitung.

Wenn aktiv: RAG-Kontext aus früheren Bänden derselben Serie
wird automatisch in Stage 1 eingespeist für konsistente
Charakter- und Weltübersetzungen.`

export function PipelineExplanation() {
  const [open, setOpen] = useState(true)

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center justify-between text-sm text-zinc-300 hover:text-zinc-100"
      >
        <span className="font-medium">Wie übersetzt Hime?</span>
        <span className="text-xs text-zinc-500">{open ? '\u25be' : '\u25b8'}</span>
      </button>
      {open && (
        <pre className="mt-3 whitespace-pre-wrap text-xs leading-relaxed text-zinc-400 font-sans">
          {TEXT}
        </pre>
      )}
    </div>
  )
}
