import { useState } from 'react'

const TEXT = `Pre-Processing:
  \u2022 MeCab-Tokenisierung + JMdict-Lookup (algorithmisch, kein GPU)
  \u2022 Glossar-Kontext (bucheigene Begriffe, Namen, Honorifics)
  \u2022 RAG-Kontext (frühere Bände derselben Serie, wenn verfügbar)

Stage 1 — 4 Modelle übersetzen parallel:
  \u2022 Qwen2.5-32B + LoRA  — fein-getuned auf JP\u2192EN Light Novels
  \u2022 TranslateGemma-12B  — Googles Übersetzungsarchitektur
  \u2022 Qwen3.5-9B          — Reasoning-orientiert (non-thinking mode)
  \u2022 Gemma4 E4B          — effizientes Google-Modell, andere Perspektive

Stage 2 — Merger:
  TranslateGemma-27B fusioniert alle 4 Entwürfe + JMdict-Anker
  + RAG- und Glossar-Kontext zu einer einzigen Übersetzung.

Stage 3 — Politur:
  Qwen3-30B-A3B (MoE, non-thinking) macht den literarischen
  Feinschliff: Fluss, Nuance, Register.

Stage 4 — Reader-Panel (Retry-Schleife):
  15 Kritiker-Personas (Qwen3-2B) prüfen parallel:
  Treue, Stil, Charakterstimmen, Yuri-Subtext, Lesbarkeit,
  Grammatik, Pacing, Dialog, Atmosphäre, Subtext,
  Kulturkontext, Honorifics u.a.
  LFM2-24B aggregiert die Annotations zum Urteil:
  \u2022 ok          \u2192 fertig
  \u2022 fix_pass    \u2192 Stage 3 nochmal mit Feedback-Instruktion (max. 2×)
  \u2022 full_retry  \u2192 Stage 1\u21922\u21923 komplett neu, Instruktion im RAG-Kontext (max. 1×)
  Bei Budget-Erschöpfung: retry_flag gesetzt, Segment wird trotzdem übernommen.

Post-Processing:
  Absätze werden zu Kapiteltext zusammengefügt (Titel + Text).
  Nicht übersetzte Absätze erhalten einen [untranslated]-Fallback.`

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
