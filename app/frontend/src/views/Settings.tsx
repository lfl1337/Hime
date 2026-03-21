import { useEffect, useRef, useState } from 'react'
import { useTheme } from '@/App'
import { getTrainingConfig, updateTrainingConfig } from '@/api/training'
import { getEpubSettings, updateEpubSetting } from '@/api/epub'
import { getHealthInfo } from '@/api/client'

// ---------------------------------------------------------------------------
// Open URL — Tauri shell with window.open fallback
// ---------------------------------------------------------------------------

async function openUrl(url: string) {
  try {
    const { open } = await import('@tauri-apps/plugin-shell')
    await open(url)
  } catch {
    window.open(url, '_blank')
  }
}

// ---------------------------------------------------------------------------
// Pill toggle
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
// Section / Row wrappers
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
// Editable path row
// ---------------------------------------------------------------------------

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

function PathRow({
  label,
  initialValue,
  onSave,
}: {
  label: string
  initialValue: string
  onSave: (value: string) => Promise<void>
}) {
  const [value, setValue] = useState(initialValue)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const timerRef = useRef<number | null>(null)

  // Sync when parent loads data
  useEffect(() => { setValue(initialValue) }, [initialValue])

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current) }, [])

  const handleSave = async () => {
    setSaveState('saving')
    try {
      await onSave(value)
      setSaveState('saved')
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = window.setTimeout(() => setSaveState('idle'), 2000)
    } catch {
      setSaveState('error')
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = window.setTimeout(() => setSaveState('idle'), 3000)
    }
  }

  const saveLabel = saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? 'Saved!' : saveState === 'error' ? 'Error' : 'Save'
  const saveColor = saveState === 'saved'
    ? 'bg-green-800 text-green-200'
    : saveState === 'error'
    ? 'bg-red-900 text-red-300'
    : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300'

  return (
    <div className="px-4 py-3">
      <div className="text-xs text-zinc-500 mb-1.5">{label}</div>
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={value}
          onChange={e => setValue(e.target.value)}
          className="flex-1 bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs font-mono rounded-lg px-3 py-1.5 focus:outline-none focus:border-violet-500 min-w-0"
        />
        <button
          onClick={() => void handleSave()}
          disabled={saveState === 'saving'}
          className={`px-2.5 py-1.5 text-xs rounded-lg transition-colors min-w-[52px] ${saveColor}`}
        >
          {saveLabel}
        </button>
        <CopyButton text={value} />
      </div>
    </div>
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
  const { applyTheme } = useTheme()

  // FIX 3: own state so the active pill updates immediately on click
  const [theme, setTheme] = useState<'dark' | 'light' | 'system'>(
    () => (localStorage.getItem('hime_theme') ?? 'dark') as 'dark' | 'light' | 'system'
  )
  const handleTheme = (v: 'dark' | 'light' | 'system') => {
    setTheme(v)
    applyTheme(v)
  }

  // Training defaults
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
  const [modelsBasePath, setModelsBasePath] = useState('')
  const [loraPath, setLoraPath] = useState('')
  const [trainingLogPath, setTrainingLogPath] = useState('')
  const [scriptsPath, setScriptsPath] = useState('')
  const [epubFolder, setEpubFolder] = useState('')

  // About
  const [backendVersion, setBackendVersion] = useState<string | null>(null)

  useEffect(() => {
    getTrainingConfig().then(cfg => {
      setModelsBasePath(cfg.models_base_path)
      setLoraPath(cfg.lora_path)
      setTrainingLogPath(cfg.training_log_path)
      setScriptsPath(cfg.scripts_path)
    }).catch(() => {})
    getEpubSettings().then(s => setEpubFolder(s.epub_watch_folder)).catch(() => {})
    getHealthInfo().then(h => setBackendVersion(h.version)).catch(() => {})
  }, [])

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

  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-xl font-bold text-zinc-100 mb-6">Settings</h1>

      {/* ── Appearance ─────────────────────────────────────────────────── */}
      <Section title="Appearance">
        <Row label="Theme">
          <PillToggle options={THEME_OPTIONS} value={theme} onChange={handleTheme} />
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
        <PathRow
          label="EPUB Watch Folder"
          initialValue={epubFolder}
          onSave={v => updateEpubSetting('epub_watch_folder', v)}
        />
        <PathRow
          label="Models Base Path"
          initialValue={modelsBasePath}
          onSave={v => updateTrainingConfig('models_base_path', v).then(cfg => setModelsBasePath(cfg.models_base_path))}
        />
        <PathRow
          label="LoRA Path"
          initialValue={loraPath}
          onSave={v => updateTrainingConfig('lora_path', v).then(cfg => setLoraPath(cfg.lora_path))}
        />
        <PathRow
          label="Training Log Path"
          initialValue={trainingLogPath}
          onSave={v => updateTrainingConfig('training_log_path', v).then(cfg => setTrainingLogPath(cfg.training_log_path))}
        />
        <PathRow
          label="Scripts Path"
          initialValue={scriptsPath}
          onSave={v => updateTrainingConfig('scripts_path', v).then(cfg => setScriptsPath(cfg.scripts_path))}
        />
      </Section>

      {/* ── About ──────────────────────────────────────────────────────── */}
      <Section title="About">
        <div className="px-4 py-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-zinc-300 font-semibold">Hime</span>
            <span className="text-sm text-zinc-500 font-mono">v0.7.1</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-zinc-300">Backend</span>
            <span className="text-sm text-zinc-500 font-mono">{backendVersion ? `v${backendVersion}` : '—'}</span>
          </div>
          <div className="border-t border-zinc-800 pt-3 mt-3 flex gap-2">
            <button
              onClick={() => void openUrl('https://github.com/lfl1337/Hime')}
              className="px-4 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              Open on GitHub
            </button>
            <button
              onClick={() => void openUrl('https://github.com/lfl1337/Hime/releases')}
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
