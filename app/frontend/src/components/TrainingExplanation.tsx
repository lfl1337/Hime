import { useState } from 'react'

const TEXT = `Modulares Training

Jedes Pipeline-Modell wird unabhängig trainiert als LoRA-Adapter:

  Stage 1 — Übersetzer
    \u2022 Qwen 2.5 32B    (~7 Tage, läuft jetzt)
    \u2022 Gemma 3 12B     (~2 Tage Cloud)
    \u2022 DeepSeek R1 32B (~3 Tage Cloud)

  Stage 2 — Refinement
    \u2022 Qwen 2.5 72B    (~5 Tage Cloud)

  Stage 3 — Polish
    \u2022 Qwen 2.5 14B    (~1 Tag Cloud)

Trainingsdaten kommen aus: \${HIME_TRAINING_DATA_DIR}
Curriculum Learning erweitert den Datensatz automatisch
wenn Overfitting erkannt wird (Score 0.70 \u2192 0.62 \u2192 0.55).

Auto-Resume: Bei Crashes wird automatisch vom letzten
gültigen Checkpoint fortgesetzt. Kein Datenverlust mehr.`

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
