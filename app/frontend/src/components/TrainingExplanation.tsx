import { useState } from 'react'

const TEXT = `Modulares Training (v2)

Nur Stage-1-Modelle erhalten LoRA-Adapter. Alle anderen
Stufen sind Zero-Shot und brauchen kein Training.

  Stage 1 — 3 Übersetzer (LoRA fine-tuned)
    \u2022 Qwen2.5-32B+LoRA     (~7 Tage, GPU lokal)
    \u2022 TranslateGemma-12B   (~2 Tage, Transformers)
    \u2022 Qwen3.5-9B           (~1 Tag, Unsloth)

  Stage 2 — Merger (kein Training)
    \u2022 TranslateGemma-27B   (Zero-Shot)

  Stage 3 — Polish (kein Training)
    \u2022 Qwen3-30B-A3B (MoE)  (Zero-Shot, non-thinking)

  Stage 4 — Reader-Panel (kein Training)
    \u2022 Qwen3-2B \u00d7 15 Personas (Zero-Shot)
    \u2022 LFM2-24B Aggregator  (Zero-Shot)

Trainingsdaten: \${HIME_TRAINING_DATA_DIR}
Curriculum Learning (jparacrawl_500k → hime_training_all)
erweitert den Datensatz automatisch bei Overfitting
(Score 0.70 \u2192 0.62 \u2192 0.55).

Auto-Resume: Beim nächsten Start wird automatisch vom
letzten Checkpoint fortgesetzt. Kein Datenverlust.`

export function TrainingExplanation() {
  const [open, setOpen] = useState(false)

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center justify-between text-sm text-zinc-300 hover:text-zinc-100"
      >
        <span className="font-medium">Was ist modulares Training?</span>
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
