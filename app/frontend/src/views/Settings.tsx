import { useEffect, useRef, useState } from 'react'
import { openUrl as openerOpenUrl } from '@tauri-apps/plugin-opener'
import { open as dialogOpen } from '@tauri-apps/plugin-dialog'
import { useTheme } from '@/App'
import { getTrainingConfig, updateTrainingConfig, getMemoryDetail } from '@/api/training'
import type { MemoryDetail } from '@/api/training'
import { connectionRegistry } from '@/utils/connectionRegistry'
import type { Connection } from '@/utils/connectionRegistry'
import { getEpubSettings, updateEpubSetting } from '@/api/epub'
import { getHealthInfo } from '@/api/client'

// ---------------------------------------------------------------------------
// Open URL
//
// Must be a plain (non-async) function so that the window.open() browser
// fallback is called synchronously inside the click-handler gesture context.
// If called after an `await`, browsers block window.open() as a popup.
// ---------------------------------------------------------------------------

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

function openUrl(url: string, onFallback?: (url: string) => void): void {
  if (isTauri) {
    openerOpenUrl(url).catch((e: unknown) => {
      console.error('[openUrl] opener plugin failed:', e)
      onFallback?.(url)
    })
  } else {
    // Browser dev mode — synchronous call; runs in gesture context, not blocked
    const w = window.open(url, '_blank')
    if (!w) {
      console.warn('[openUrl] window.open blocked — falling back to clipboard')
      onFallback?.(url)
    }
  }
}

// ---------------------------------------------------------------------------
// Browse folder — Tauri dialog with toast fallback
// ---------------------------------------------------------------------------

async function browseFolder(defaultPath: string): Promise<string | null> {
  try {
    const selected = await dialogOpen({
      directory: true,
      multiple: false,
      defaultPath: defaultPath || undefined,
    })
    return typeof selected === 'string' ? selected : null
  } catch {
    return null
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
// Editable path row (with Browse button)
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

  const handleBrowse = async () => {
    const selected = await browseFolder(value)
    if (selected) setValue(selected)
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
          onClick={() => void handleBrowse()}
          className="px-2.5 py-1.5 text-xs rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
        >
          Browse…
        </button>
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

  // Paths
  const [modelsBasePath, setModelsBasePath] = useState('')
  const [loraPath, setLoraPath] = useState('')
  const [trainingLogPath, setTrainingLogPath] = useState('')
  const [scriptsPath, setScriptsPath] = useState('')
  const [epubFolder, setEpubFolder] = useState('')

  // Memory & Performance
  const [memDetail, setMemDetail] = useState<MemoryDetail | null>(null)
  const [jsHeap, setJsHeap] = useState<{ used: number; total: number; limit: number } | null>(null)
  const [debugState, setDebugState] = useState<Record<string, number>>({})
  const [connections, setConnections] = useState<Connection[]>([])
  const heapHistory = useRef<{ ts: number; used: number }[]>([])

  // About
  const [backendVersion, setBackendVersion] = useState<string | null>(null)
  const [urlToast, setUrlToast] = useState<string | null>(null)
  const urlToastTimer = useRef<number | null>(null)

  const handleUrlFallback = (url: string) => {
    navigator.clipboard.writeText(url).catch(() => {})
    if (urlToastTimer.current) clearTimeout(urlToastTimer.current)
    setUrlToast(url)
    urlToastTimer.current = window.setTimeout(() => setUrlToast(null), 4000)
  }

  useEffect(() => () => { if (urlToastTimer.current) clearTimeout(urlToastTimer.current) }, [])

  // Memory profiler: JS heap + debug state every 5s, system memory every 10s
  useEffect(() => {
    function refreshFast() {
      const mem = (performance as any).memory
      if (mem) {
        const entry = { ts: Date.now(), used: mem.usedJSHeapSize / 1024 / 1024 }
        heapHistory.current = [...heapHistory.current.slice(-11), entry]
        setJsHeap({
          used: Math.round(mem.usedJSHeapSize / 1024 / 1024),
          total: Math.round(mem.totalJSHeapSize / 1024 / 1024),
          limit: Math.round(mem.jsHeapSizeLimit / 1024 / 1024),
        })
      }
      setDebugState({ ...((window as any).__himeDebug ?? {}) })
      setConnections(connectionRegistry.getAll())
    }
    refreshFast()
    const fastId = setInterval(refreshFast, 5_000)

    getMemoryDetail().then(setMemDetail).catch(() => {})
    const slowId = setInterval(() => {
      getMemoryDetail().then(setMemDetail).catch(() => {})
    }, 30_000)

    return () => { clearInterval(fastId); clearInterval(slowId) }
  }, [])

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

      {/* ── Memory & Performance ───────────────────────────────────────── */}
      <Section title="Memory & Performance">
        {/* Frontend Memory */}
        <div className="px-4 py-3 space-y-2">
          <div className="text-xs font-medium text-zinc-400 mb-2">Frontend Memory (WebView2)</div>
          {jsHeap ? (
            <>
              <div className="flex justify-between text-xs text-zinc-400">
                <span>JS Heap</span>
                <span>{jsHeap.used} / {jsHeap.total} MB (limit: {jsHeap.limit} MB)</span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full transition-all ${
                    jsHeap.total / jsHeap.limit > 0.8 ? 'bg-red-500' :
                    jsHeap.total / jsHeap.limit > 0.5 ? 'bg-yellow-500' : 'bg-green-500'
                  }`}
                  style={{ width: `${Math.min((jsHeap.total / jsHeap.limit) * 100, 100)}%` }}
                />
              </div>
              {(() => {
                const h = heapHistory.current
                if (h.length >= 2) {
                  const oldest = h[0], newest = h[h.length - 1]
                  const mins = (newest.ts - oldest.ts) / 60_000
                  const rate = mins > 0 ? (newest.used - oldest.used) / mins : 0
                  return (
                    <div className="text-xs text-zinc-500">
                      Growth: {rate >= 0 ? '+' : ''}{rate.toFixed(1)} MB/min
                    </div>
                  )
                }
                return null
              })()}
              {typeof (window as any).gc === 'function' && (
                <button
                  onClick={() => (window as any).gc()}
                  className="mt-1 px-2.5 py-1 text-xs rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
                >
                  Force GC
                </button>
              )}
            </>
          ) : (
            <p className="text-xs text-zinc-600">performance.memory not available in this environment</p>
          )}
        </div>

        {/* React State sizes */}
        {Object.keys(debugState).length > 0 && (
          <div className="px-4 py-3 space-y-1">
            <div className="text-xs font-medium text-zinc-400 mb-2">React State (TrainingMonitor)</div>
            {Object.entries(debugState).map(([k, v]) => (
              <div key={k} className="flex justify-between text-xs">
                <span className="text-zinc-500">{k.replace(/Length$/, '').replace(/([A-Z])/g, ' $1').trim()}</span>
                <span className="text-zinc-400 font-mono">{v}</span>
              </div>
            ))}
          </div>
        )}

        {/* Active Connections */}
        <div className="px-4 py-3">
          <div className="text-xs font-medium text-zinc-400 mb-2">Active Connections</div>
          {connections.length === 0 ? (
            <p className="text-xs text-zinc-600">No active connections</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-zinc-600">
                  <th className="text-left py-1">ID</th>
                  <th className="text-left py-1">Type</th>
                  <th className="text-right py-1">Events</th>
                  <th className="text-right py-1">Bytes</th>
                </tr>
              </thead>
              <tbody>
                {connections.map(c => (
                  <tr key={c.id} className="text-zinc-400 border-t border-zinc-800">
                    <td className="py-1 font-mono truncate max-w-[120px]">{c.id}</td>
                    <td className="py-1">{c.type}</td>
                    <td className="py-1 text-right">{c.eventCount}</td>
                    <td className="py-1 text-right">{(c.bytesReceived / 1024).toFixed(1)} KB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* System Memory */}
        {memDetail && (
          <div className="px-4 py-3 space-y-3">
            <div className="text-xs font-medium text-zinc-400 mb-2">System Memory</div>
            <div>
              <div className="flex justify-between text-xs text-zinc-400 mb-1">
                <span>System RAM</span>
                <span>{memDetail.system_used_pct}% — {(memDetail.system_total_gb - memDetail.system_available_gb).toFixed(1)} / {memDetail.system_total_gb} GB</span>
              </div>
              <div className="w-full bg-zinc-800 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full ${memDetail.system_used_pct > 80 ? 'bg-red-500' : memDetail.system_used_pct > 50 ? 'bg-yellow-500' : 'bg-green-500'}`}
                  style={{ width: `${memDetail.system_used_pct}%` }}
                />
              </div>
            </div>
            {memDetail.pagefile_total_gb > 0 && (
              <div>
                <div className="flex justify-between text-xs text-zinc-400 mb-1">
                  <span>Pagefile</span>
                  <span>{memDetail.pagefile_used_pct}% — {memDetail.pagefile_used_gb.toFixed(1)} / {memDetail.pagefile_total_gb.toFixed(1)} GB</span>
                </div>
                <div className="w-full bg-zinc-800 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full ${memDetail.pagefile_used_pct > 80 ? 'bg-red-500' : memDetail.pagefile_used_pct > 50 ? 'bg-yellow-500' : 'bg-blue-500'}`}
                    style={{ width: `${memDetail.pagefile_used_pct}%` }}
                  />
                </div>
              </div>
            )}
            <div className="flex justify-between text-xs">
              <span className="text-zinc-500">Backend Python RSS</span>
              <span className="text-zinc-400 font-mono">{memDetail.process_rss_mb} MB</span>
            </div>
            {memDetail.top_processes.length > 0 && (
              <div>
                <div className="text-xs text-zinc-600 mb-1">Top processes by RSS</div>
                <table className="w-full text-xs">
                  <tbody>
                    {memDetail.top_processes.map((p) => (
                      <tr key={p.pid} className="text-zinc-400">
                        <td className="py-0.5 font-mono truncate max-w-[180px]">{p.name}</td>
                        <td className="py-0.5 text-right text-zinc-500">{p.rss_mb} MB</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </Section>

      {/* ── About ──────────────────────────────────────────────────────── */}
      <Section title="About">
        <div className="px-4 py-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-zinc-300 font-semibold">Hime</span>
            <span className="text-sm text-zinc-500 font-mono">v0.7.2</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-zinc-300">Backend</span>
            <span className="text-sm text-zinc-500 font-mono">{backendVersion ? `v${backendVersion}` : '—'}</span>
          </div>
          <div className="border-t border-zinc-800 pt-3 mt-3 flex gap-2 flex-wrap">
            <button
              onClick={() => openUrl('https://github.com/lfl1337/Hime', handleUrlFallback)}
              className="px-4 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              Open on GitHub
            </button>
            <button
              onClick={() => openUrl('https://github.com/lfl1337/Hime/releases', handleUrlFallback)}
              className="px-4 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              Check for updates
            </button>
          </div>
          {urlToast && (
            <div className="mt-3 flex items-center gap-2 text-xs bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2">
              <span className="text-zinc-400">Could not open browser. URL copied to clipboard:</span>
              <span className="font-mono text-violet-400 truncate">{urlToast}</span>
            </div>
          )}
        </div>
      </Section>
    </div>
  )
}
