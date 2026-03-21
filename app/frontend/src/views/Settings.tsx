import { useEffect, useRef, useState } from 'react'
import { useTheme } from '@/App'
import { getTrainingConfig, type TrainingConfig } from '@/api/training'
import { getEpubSettings } from '@/api/epub'
import { getHealthInfo } from '@/api/client'

// ---------------------------------------------------------------------------
// Pill toggle helper
// ---------------------------------------------------------------------------

interface PillOption<T extends string> {
  value: T
  label: string
}

function PillToggle<T extends string>({
  options,
  value,
  onChange,
}: {
  options: PillOption<T>[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex gap-1 bg-zinc-800 rounded-lg p-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1 rounded-md text-sm transition-colors ${
            value === opt.value
              ? 'bg-violet-700 text-white'
              : 'text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-8">
      <h2 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-3">{title}</h2>
      <div className="bg-zinc-900 rounded-xl border border-zinc-800 divide-y divide-zinc-800">
        {children}
      </div>
    </section>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 py-3">
      <span className="text-sm text-zinc-300">{label}</span>
      <div className="flex items-center gap-2">{children}</div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Copy button
// ---------------------------------------------------------------------------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<number | null>(null)

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = window.setTimeout(() => setCopied(false), 2000)
    })
  }

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current) }, [])

  return (
    <button
      onClick={handleCopy}
      className="px-2 py-0.5 text-xs rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors min-w-[52px]"
    >
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

// ---------------------------------------------------------------------------
// Settings view
// ---------------------------------------------------------------------------

const THEME_OPTIONS: PillOption<'dark' | 'light' | 'system'>[] = [
  { value: 'dark', label: 'Dark' },
  { value: 'light', label: 'Light' },
  { value: 'system', label: 'System' },
]

const CHECKPOINT_OPTIONS: PillOption<'best' | 'latest'>[] = [
  { value: 'best', label: 'Best checkpoint' },
  { value: 'latest', label: 'Latest checkpoint' },
]

export function Settings() {
  const { current: currentTheme, applyTheme } = useTheme()

  // Training defaults — read from localStorage
  const [checkpointPref, setCheckpointPref] = useState<'best' | 'latest'>(
    () => (localStorage.getItem('hime_default_checkpoint') as 'best' | 'latest') ?? 'best'
  )
  const [defaultEpochs, setDefaultEpochs] = useState<number>(
    () => parseInt(localStorage.getItem('hime_default_epochs') ?? '3') || 3
  )
  const [defaultCondaEnv, setDefaultCondaEnv] = useState<string>(
    () => localStorage.getItem('hime_default_conda_env') ?? 'hime'
  )

  // Paths
  const [trainingConfig, setTrainingConfig] = useState<TrainingConfig | null>(null)
  const [epubFolder, setEpubFolder] = useState<string | null>(null)

  // About
  const [backendVersion, setBackendVersion] = useState<string | null>(null)

  useEffect(() => {
    getTrainingConfig().then(setTrainingConfig).catch(() => {})
    getEpubSettings().then(s => setEpubFolder(s.epub_watch_folder)).catch(() => {})
    getHealthInfo().then(h => setBackendVersion(h.version)).catch(() => {})
  }, [])

  // Persist training defaults on change
  const handleCheckpointPref = (v: 'best' | 'latest') => {
    setCheckpointPref(v)
    localStorage.setItem('hime_default_checkpoint', v)
  }
  const handleEpochs = (v: number) => {
    setDefaultEpochs(v)
    localStorage.setItem('hime_default_epochs', String(v))
  }
  const handleCondaEnv = (v: string) => {
    setDefaultCondaEnv(v)
    localStorage.setItem('hime_default_conda_env', v)
  }

  const pathRows = [
    { label: 'EPUB Watch Folder', value: epubFolder },
    { label: 'Models Base Path', value: trainingConfig?.models_base_path ?? null },
    { label: 'LoRA Path', value: trainingConfig?.lora_path ?? null },
    { label: 'Training Log Path', value: trainingConfig?.training_log_path ?? null },
    { label: 'Scripts Path', value: trainingConfig?.scripts_path ?? null },
  ]

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-xl font-bold text-zinc-100 mb-6">Settings</h1>

      {/* ── Appearance ─────────────────────────────────────────────────── */}
      <Section title="Appearance">
        <Row label="Theme">
          <PillToggle options={THEME_OPTIONS} value={currentTheme} onChange={applyTheme} />
        </Row>
      </Section>

      {/* ── Training Defaults ──────────────────────────────────────────── */}
      <Section title="Training Defaults">
        <Row label="Default checkpoint">
          <PillToggle options={CHECKPOINT_OPTIONS} value={checkpointPref} onChange={handleCheckpointPref} />
        </Row>
        <Row label="Default epochs">
          <input
            type="number"
            min={1}
            max={10}
            value={defaultEpochs}
            onChange={e => handleEpochs(Math.max(1, Math.min(10, parseInt(e.target.value) || 3)))}
            className="w-16 bg-zinc-800 border border-zinc-700 text-zinc-200 text-sm rounded-lg px-2 py-1 text-center focus:outline-none focus:border-violet-500"
          />
        </Row>
        <Row label="Conda environment">
          <input
            type="text"
            value={defaultCondaEnv}
            onChange={e => handleCondaEnv(e.target.value)}
            className="w-40 bg-zinc-800 border border-zinc-700 text-zinc-200 text-sm rounded-lg px-3 py-1 focus:outline-none focus:border-violet-500"
          />
        </Row>
      </Section>

      {/* ── Paths ──────────────────────────────────────────────────────── */}
      <Section title="Paths">
        {pathRows.map(({ label, value }) => (
          <div key={label} className="px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm text-zinc-300 min-w-[140px]">{label}</span>
              <span className="text-xs text-zinc-500 font-mono truncate flex-1 text-right">
                {value ?? '—'}
              </span>
              {value && <CopyButton text={value} />}
            </div>
          </div>
        ))}
      </Section>

      {/* ── About ──────────────────────────────────────────────────────── */}
      <Section title="About">
        <div className="px-4 py-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-zinc-300 font-semibold">Hime</span>
            <span className="text-sm text-zinc-500 font-mono">v0.7.0</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-zinc-300">Backend</span>
            <span className="text-sm text-zinc-500 font-mono">{backendVersion ? `v${backendVersion}` : '—'}</span>
          </div>
          <div className="border-t border-zinc-800 pt-3 mt-3 flex gap-2">
            <button
              onClick={() => window.open('https://github.com/lfl1337/Hime', '_blank')}
              className="px-4 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              Open on GitHub
            </button>
            <button
              onClick={() => window.open('https://github.com/lfl1337/Hime/releases', '_blank')}
              className="px-4 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              Check for updates
            </button>
          </div>
        </div>
      </Section>
    </div>
  )
}
