import { useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store'
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import type { CheckpointInfo, GGUFModelInfo, HardwareStats, LossPoint, RunInfo, TrainingProcess, TrainingStatus } from '../api/training'
import {
  createHardwareEventSource,
  createTrainingEventSource,
  fetchAllRuns,
  fetchGGUFModels,
  getBackendLog,
  getCondaEnvs,
  getCheckpoints,
  getHardwareHistory,
  getHardwareStats,
  getLossHistory,
  getRunningProcesses,
  getTrainingLog,
  getTrainingStatus,
  startTraining,
  stopTraining,
} from '../api/training'

// ---------------------------------------------------------------------------
// TrainingStatusBadge
// ---------------------------------------------------------------------------

const STATUS_CFG = {
  idle:        { ring: 'bg-zinc-800 text-zinc-400',        dot: 'bg-zinc-500',                label: 'Idle' },
  training:    { ring: 'bg-green-900/50 text-green-400',   dot: 'bg-green-400 animate-pulse', label: 'Training' },
  interrupted: { ring: 'bg-yellow-900/50 text-yellow-400', dot: 'bg-yellow-400',              label: 'Interrupted' },
  complete:    { ring: 'bg-blue-900/50 text-blue-400',     dot: 'bg-blue-400',                label: 'Complete' },
}

function TrainingStatusBadge({ status }: { status: TrainingStatus['status'] }) {
  const cfg = STATUS_CFG[status]
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${cfg.ring}`}>
      <span className={`w-2 h-2 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// useCopyToClipboard
// ---------------------------------------------------------------------------

function useCopyToClipboard(timeout = 2000) {
  const [copied, setCopied] = useState<string | null>(null)
  const timeoutRef = useRef<number | null>(null)
  const copy = (text: string, key: string) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key)
      timeoutRef.current = window.setTimeout(() => setCopied(null), timeout)
    })
  }
  useEffect(() => () => { if (timeoutRef.current) clearTimeout(timeoutRef.current) }, [])
  return { copied, copy }
}

// ---------------------------------------------------------------------------
// Status dot mapping for run selector pills
// ---------------------------------------------------------------------------

const STATUS_DOT: Record<RunInfo['status'], string> = {
  idle:        'bg-zinc-500',
  training:    'bg-green-400 animate-pulse',
  interrupted: 'bg-yellow-400',
  complete:    'bg-blue-400',
}

// ---------------------------------------------------------------------------
// Pipeline role badge helper
// ---------------------------------------------------------------------------

function pipelineRoleStyle(role: string | null): string {
  if (role === 'Stage 1 — Draft') return 'bg-blue-900/50 text-blue-400'
  if (role === 'Stage 2 — Refine') return 'bg-violet-900/50 text-violet-400'
  if (role === 'Stage 3 — Polish') return 'bg-teal-900/50 text-teal-400'
  return 'bg-zinc-800 text-zinc-400'
}

// Relative time helper
function relativeTime(isoDate: string): string {
  const diffMs = Date.now() - new Date(isoDate).getTime()
  const mins = Math.floor(diffMs / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} minute${mins === 1 ? '' : 's'} ago`
  const hrs = Math.floor(mins / 60)
  return `${hrs} hour${hrs === 1 ? '' : 's'} ago`
}

// ---------------------------------------------------------------------------
// Log line type → CSS class
// ---------------------------------------------------------------------------

function logLineClass(type: string): string {
  switch (type) {
    case 'loss':       return 'text-violet-400'
    case 'progress':   return 'text-cyan-400'
    case 'hardware':   return 'text-orange-400'
    case 'checkpoint': return 'text-green-400 font-semibold'
    case 'error':      return 'text-red-400'
    case 'info':       return 'text-zinc-300'
    default:           return 'text-zinc-500'
  }
}

// ---------------------------------------------------------------------------
// Hardware monitor card
// ---------------------------------------------------------------------------

interface HwCardProps {
  label: string
  value: string
  sub?: string
  pct: number
  barColor: string
}

function HwCard({ label, value, sub, pct, barColor }: HwCardProps) {
  const clamped = Math.min(Math.max(pct, 0), 100)
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-3 flex flex-col gap-1.5">
      <div className="text-xs text-zinc-500 font-medium uppercase tracking-wide">{label}</div>
      <div className="text-lg font-semibold text-zinc-100 leading-tight">{value}</div>
      {sub && <div className="text-xs text-zinc-500">{sub}</div>}
      <div className="w-full bg-zinc-800 rounded-full h-1.5 mt-auto">
        <div
          className={`h-1.5 rounded-full transition-all ${barColor}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  )
}

function gpuUtilColor(pct: number): string {
  if (pct >= 71) return 'bg-green-500'
  if (pct >= 31) return 'bg-yellow-500'
  return 'bg-zinc-500'
}

function tempColor(celsius: number): string {
  if (celsius > 80) return 'text-red-400'
  if (celsius >= 60) return 'text-yellow-400'
  return 'text-green-400'
}

// ---------------------------------------------------------------------------
// TrainingMonitor
// ---------------------------------------------------------------------------

export function TrainingMonitor() {
  const [runs, setRuns] = useState<RunInfo[]>([])
  const [runsLoaded, setRunsLoaded] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const [ggufModels, setGgufModels] = useState<GGUFModelInfo[]>([])
  const [runLoading, setRunLoading] = useState(false)
  const [status, setStatus] = useState<TrainingStatus | null>(null)
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([])
  const [lossHistory, setLossHistory] = useState<LossPoint[]>([])
  const [logLines, setLogLines] = useState<Array<{ line: string; type: string }>>([])
  const [lastUpdated, setLastUpdated] = useState<number>(Date.now())
  const [sseConnected, setSseConnected] = useState(false)
  const [secondsAgo, setSecondsAgo] = useState(0)

  // Log tab state
  const [logTab, setLogTab] = useState<'training' | 'backend'>('training')
  const [backendLogLines, setBackendLogLines] = useState<string[]>([])

  // Hardware monitor state
  const [hwStats, setHwStats] = useState<HardwareStats | null>(null)
  const [hwHistory, setHwHistory] = useState<HardwareStats[]>([])
  const hwEsRef = useRef<EventSource | null>(null)

  // Log filter state
  const [logFilter, setLogFilter] = useState<'all' | 'loss' | 'progress' | 'hardware' | 'checkpoint' | 'error'>('all')

  // Training controls state
  const [trainingEpochs, setTrainingEpochs] = useState<number>(() =>
    parseInt(localStorage.getItem('hime_default_epochs') ?? '3') || 3
  )
  const [condaEnv, setCondaEnv] = useState<string>(() =>
    localStorage.getItem('hime_default_conda_env') ?? 'hime'
  )
  const [condaEnvs, setCondaEnvs] = useState<string[] | null>(null)
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<string | null>(null)
  const [runningProcesses, setRunningProcesses] = useState<TrainingProcess[]>([])
  const [controlError, setControlError] = useState<string | null>(null)
  const [confirmAction, setConfirmAction] = useState<'start' | 'stop' | null>(null)
  const [controlLoading, setControlLoading] = useState(false)
  const [stopPollStart, setStopPollStart] = useState<number | null>(null)
  const stopPollRef = useRef<number | null>(null)

  const isWindowVisible = useStore(s => s.isWindowVisible)

  const logEndRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)
  const fallbackRef = useRef<number | null>(null)
  const selectedRunRef = useRef<string | null>(null)

  // Mount effect: fetch runs and GGUF models in parallel, then select first run
  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setLoadError('Request timed out after 10 seconds — check that the backend is running.')
      setRunsLoaded(true)
    }, 10_000)

    getCondaEnvs().then(envs => setCondaEnvs(envs)).catch(() => {})

    Promise.allSettled([fetchAllRuns(), fetchGGUFModels(), getRunningProcesses()]).then(([runsResult, ggufResult, procResult]) => {
      clearTimeout(timeoutId)
      if (runsResult.status === 'rejected') {
        setLoadError(String(runsResult.reason))
      }
      const loadedRuns = runsResult.status === 'fulfilled' ? runsResult.value : []
      const loadedGguf = ggufResult.status === 'fulfilled' ? ggufResult.value : []
      const loadedProcs = procResult.status === 'fulfilled' ? procResult.value : []
      setRuns(loadedRuns)
      setGgufModels(loadedGguf)
      setRunningProcesses(loadedProcs)
      setSelectedRun(loadedRuns[0]?.run_name ?? null)
      setRunsLoaded(true)
    })

    return () => clearTimeout(timeoutId)
  }, [])

  // Hardware SSE — pauses when window is hidden, resumes on restore
  useEffect(() => {
    if (!isWindowVisible) return

    let cancelled = false

    getHardwareStats().then(s => { if (!cancelled) setHwStats(s) }).catch(() => {})
    getHardwareHistory(10).then(h => { if (!cancelled) setHwHistory(h) }).catch(() => {})

    const hwHandler = (e: MessageEvent<string>) => {
      try {
        const stats = JSON.parse(e.data) as HardwareStats
        setHwStats(stats)
        setHwHistory(prev => {
          const next = [...prev, stats]
          return next.length > 120 ? next.slice(-120) : next
        })
      } catch { /* ignore */ }
    }

    createHardwareEventSource().then(es => {
      if (cancelled) { es.close(); return }
      hwEsRef.current = es
      es.addEventListener('hardware_stats', hwHandler)
    }).catch(() => {})

    return () => {
      cancelled = true
      if (hwEsRef.current) {
        hwEsRef.current.removeEventListener('hardware_stats', hwHandler)
        hwEsRef.current.close()
        hwEsRef.current = null
      }
    }
  }, [isWindowVisible])

  // Keep selectedRunRef in sync with selectedRun
  useEffect(() => {
    selectedRunRef.current = selectedRun
  }, [selectedRun])

  // Auto-select checkpoint when checkpoints load, respecting stored preference
  useEffect(() => {
    if (checkpoints.length === 0) { setSelectedCheckpoint(null); return }
    const pref = localStorage.getItem('hime_default_checkpoint') ?? 'best'
    const chosen = pref === 'latest'
      ? (checkpoints.filter(c => !c.is_interrupted).sort((a, b) => b.step - a.step)[0] ?? null)
      : (checkpoints.find(c => c.is_best) ?? checkpoints.find(c => c.is_last) ?? null)
    setSelectedCheckpoint(chosen ? chosen.name : null)
  }, [checkpoints])

  // selectedRun effect: load data and connect SSE for the selected run
  useEffect(() => {
    if (selectedRun === null || !isWindowVisible) return

    // Close old SSE
    esRef.current?.close()
    esRef.current = null

    // Clear old fallback
    if (fallbackRef.current !== null) {
      clearInterval(fallbackRef.current)
      fallbackRef.current = null
    }

    // Clear state
    setStatus(null)
    setCheckpoints([])
    setLossHistory([])
    setLogLines([])
    setRunLoading(true)
    setSseConnected(false)

    let aborted = false

    // Initial data fetch
    Promise.allSettled([
      getTrainingStatus(selectedRun),
      getCheckpoints(selectedRun),
      getLossHistory(selectedRun),
      getTrainingLog(20, selectedRun),
    ]).then(([s, cp, lh, ll]) => {
      if (aborted) return
      if (s.status === 'fulfilled') { setStatus(s.value); setLastUpdated(Date.now()) }
      if (cp.status === 'fulfilled') setCheckpoints(cp.value)
      if (lh.status === 'fulfilled') setLossHistory(lh.value.slice(-1000))
      if (ll.status === 'fulfilled') setLogLines(ll.value.map(line => ({ line, type: 'info' })))
      setRunLoading(false)
    })

    // Connect SSE
    createTrainingEventSource(selectedRun).then(es => {
      if (aborted) {
        es.close()
        return
      }
      esRef.current = es

      es.addEventListener('status', (e: MessageEvent<string>) => {
        if (aborted) return
        try {
          const s = JSON.parse(e.data) as TrainingStatus
          setStatus(s)
          setLastUpdated(Date.now())
        } catch { /* ignore parse errors */ }
      })

      es.addEventListener('log_line', (e: MessageEvent<string>) => {
        if (aborted) return
        try {
          const parsed = JSON.parse(e.data) as { line: string; type?: string }
          const entry = { line: parsed.line, type: parsed.type ?? 'info' }
          setLogLines(prev => {
            const next = [...prev, entry]
            return next.length > 100 ? next.slice(-100) : next
          })
        } catch { /* ignore */ }
      })

      es.addEventListener('loss_point', (e: MessageEvent<string>) => {
        if (aborted) return
        try {
          const point = JSON.parse(e.data) as LossPoint
          setLossHistory(prev => {
            const next = [...prev, point]
            return next.length > 1000 ? next.slice(-1000) : next
          })
        } catch { /* ignore */ }
      })

      es.onopen = () => {
        if (!aborted) setSseConnected(true)
      }

      es.onerror = () => {
        if (aborted) return
        setSseConnected(false)
        es.close()
        esRef.current = null
        // Fallback: poll every 5s using selectedRunRef to get current run
        if (fallbackRef.current === null) {
          fallbackRef.current = window.setInterval(() => {
            const currentRun = selectedRunRef.current
            if (currentRun === null) return
            Promise.allSettled([
              getTrainingStatus(currentRun),
              getTrainingLog(20, currentRun),
            ]).then(([s, ll]) => {
              if (aborted) return
              if (s.status === 'fulfilled') { setStatus(s.value); setLastUpdated(Date.now()) }
              if (ll.status === 'fulfilled') setLogLines(ll.value.map(line => ({ line, type: 'info' })))
            })
          }, 5000)
        }
      }
    }).catch(() => {
      if (!aborted) setSseConnected(false)
    })

    return () => {
      aborted = true
      esRef.current?.close()
      esRef.current = null
      if (fallbackRef.current !== null) {
        clearInterval(fallbackRef.current)
        fallbackRef.current = null
      }
      if (stopPollRef.current !== null) {
        clearInterval(stopPollRef.current)
        stopPollRef.current = null
      }
    }
  }, [selectedRun, isWindowVisible])

  // "X seconds ago" ticker
  useEffect(() => {
    const id = window.setInterval(() => {
      setSecondsAgo(Math.floor((Date.now() - lastUpdated) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [lastUpdated])

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logLines])

  // Poll backend log every 5s when the backend tab is active
  useEffect(() => {
    if (logTab !== 'backend') return
    const load = () => getBackendLog(50).then(d => setBackendLogLines(d.lines)).catch(() => {})
    void load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [logTab])

  // Chart data: last 500 train points + all eval points
  const chartData = useMemo(() => {
    const evalSteps = new Set(lossHistory.filter(p => p.eval_loss !== null).map(p => p.step))
    const trainPoints = lossHistory.filter(p => p.train_loss !== null).slice(-500)
    const trainSteps = new Set(trainPoints.map(p => p.step))
    return lossHistory
      .filter(p => trainSteps.has(p.step) || evalSteps.has(p.step))
      .map(p => ({
        step: p.step,
        train_loss: trainSteps.has(p.step) ? p.train_loss : null,
        eval_loss: p.eval_loss,
      }))
  }, [lossHistory])

  const { copied, copy } = useCopyToClipboard()

  const bestCp = checkpoints.find(c => c.is_best) ?? checkpoints.find(c => c.is_last) ?? null

  // Running process for selected run
  const runningProcess = selectedRun
    ? runningProcesses.find(p => p.model_name === selectedRun) ?? null
    : null

  async function handleConfirmStart() {
    if (!selectedRun) return
    setControlLoading(true)
    setControlError(null)
    try {
      await startTraining({
        model_name: selectedRun,
        resume_checkpoint: selectedCheckpoint,
        epochs: trainingEpochs,
        conda_env: condaEnv,
      })
      const procs = await getRunningProcesses()
      setRunningProcesses(procs)
    } catch (e) {
      setControlError(String(e))
    } finally {
      setControlLoading(false)
      setConfirmAction(null)
    }
  }

  async function handleConfirmStop() {
    if (!selectedRun) return
    setControlLoading(true)
    setControlError(null)
    try {
      await stopTraining(selectedRun)
    } catch (e) {
      setControlError(String(e))
      setControlLoading(false)
      setConfirmAction(null)
      return
    }
    setConfirmAction(null)
    const pollStart = Date.now()
    setStopPollStart(pollStart)

    // Poll /processes every 2s until gone or 30s timeout
    stopPollRef.current = window.setInterval(async () => {
      const procs = await getRunningProcesses().catch(() => null)
      if (procs !== null) setRunningProcesses(procs)
      const stillRunning = procs?.some(p => p.model_name === selectedRun) ?? true
      const elapsed = Date.now() - pollStart
      if (!stillRunning || elapsed > 30_000) {
        clearInterval(stopPollRef.current!)
        stopPollRef.current = null
        setStopPollStart(null)
        setControlLoading(false)
      }
    }, 2000)
  }

  // Loading / error / empty screen
  if (!runsLoaded || runs.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        {!runsLoaded ? (
          <div className="flex items-center gap-3 text-zinc-500 text-sm">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-zinc-400" />
            Loading training runs…
          </div>
        ) : loadError ? (
          <div className="text-center space-y-3 max-w-lg px-6">
            <p className="text-red-400 text-sm font-medium">Failed to load training data</p>
            <p className="text-zinc-500 text-xs font-mono break-all">{loadError}</p>
          </div>
        ) : (
          <div className="text-center space-y-2">
            <p className="text-zinc-400 text-sm">No training runs found</p>
            <p className="text-zinc-600 text-xs">
              Run a training job first — LoRA checkpoints will appear here automatically.
            </p>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full">

      {/* Confirmation modal */}
      {confirmAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 max-w-md w-full mx-4 space-y-4">
            {confirmAction === 'start' ? (
              <>
                <h3 className="text-zinc-200 font-semibold">Start Training?</h3>
                <p className="text-zinc-400 text-sm">
                  Start training <span className="text-zinc-200">{selectedRun}</span>
                  {selectedCheckpoint
                    ? <> from checkpoint <span className="text-zinc-200 font-mono">{selectedCheckpoint}</span></>
                    : <> from scratch</>
                  }? This will use your GPU.
                </p>
              </>
            ) : (
              <>
                <h3 className="text-zinc-200 font-semibold">Stop Training?</h3>
                <p className="text-zinc-400 text-sm">
                  The model will finish its current step and save a checkpoint before stopping.
                </p>
              </>
            )}
            {controlError && (
              <p className="text-red-400 text-xs font-mono break-all">{controlError}</p>
            )}
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => { setConfirmAction(null); setControlError(null) }}
                className="px-4 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
                disabled={controlLoading}
              >
                Cancel
              </button>
              {confirmAction === 'start' ? (
                <button
                  onClick={() => void handleConfirmStart()}
                  className="px-4 py-2 rounded-lg text-sm bg-green-700 hover:bg-green-600 text-white transition-colors disabled:opacity-50"
                  disabled={controlLoading}
                >
                  {controlLoading ? 'Starting…' : 'Start Training'}
                </button>
              ) : (
                <button
                  onClick={() => void handleConfirmStop()}
                  className="px-4 py-2 rounded-lg text-sm bg-red-700 hover:bg-red-600 text-white transition-colors disabled:opacity-50"
                  disabled={controlLoading}
                >
                  {controlLoading ? 'Stopping…' : 'Stop Training'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Section 0: Run Selector */}
      <div className="flex flex-wrap gap-2 mb-2">
        {runs.map(run => (
          <button
            key={run.run_name}
            onClick={() => setSelectedRun(run.run_name)}
            className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
              selectedRun === run.run_name
                ? 'bg-violet-700 text-white'
                : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${STATUS_DOT[run.status]}`} />
            {run.display_name}
          </button>
        ))}
      </div>

      {/* Hardware Monitor */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
        <h3 className="text-sm font-medium text-zinc-400 mb-3">Hardware</h3>
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
          <HwCard
            label="VRAM"
            value={hwStats
              ? `${(hwStats.gpu_vram_used_mb / 1024).toFixed(1)} / ${(hwStats.gpu_vram_total_mb / 1024).toFixed(1)} GB`
              : '— / — GB'}
            pct={hwStats?.gpu_vram_pct ?? 0}
            barColor="bg-violet-500"
          />
          <HwCard
            label="GPU"
            value={hwStats ? `${hwStats.gpu_utilization_pct}%` : '—'}
            pct={hwStats?.gpu_utilization_pct ?? 0}
            barColor={gpuUtilColor(hwStats?.gpu_utilization_pct ?? 0)}
          />
          <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-3 flex flex-col gap-1.5">
            <div className="text-xs text-zinc-500 font-medium uppercase tracking-wide">Temp</div>
            <div className={`text-lg font-semibold leading-tight ${tempColor(hwStats?.gpu_temp_celsius ?? 0)}`}>
              {hwStats ? `${hwStats.gpu_temp_celsius}°C` : '—'}
            </div>
            <div className="text-xs text-zinc-600">Limit: 90°C</div>
            <div className="w-full bg-zinc-800 rounded-full h-1.5 mt-auto">
              <div
                className={`h-1.5 rounded-full transition-all ${hwStats && hwStats.gpu_temp_celsius > 80 ? 'bg-red-500' : hwStats && hwStats.gpu_temp_celsius >= 60 ? 'bg-yellow-500' : 'bg-green-500'}`}
                style={{ width: `${Math.min((hwStats?.gpu_temp_celsius ?? 0) / 90 * 100, 100)}%` }}
              />
            </div>
          </div>
          <HwCard
            label="Power"
            value={hwStats ? `${hwStats.gpu_power_draw_w.toFixed(0)}W` : '—'}
            sub={hwStats?.gpu_power_limit_w ? `/ ${hwStats.gpu_power_limit_w.toFixed(0)}W limit` : undefined}
            pct={hwStats && hwStats.gpu_power_limit_w > 0 ? hwStats.gpu_power_draw_w / hwStats.gpu_power_limit_w * 100 : 0}
            barColor="bg-violet-400"
          />
          <HwCard
            label="RAM"
            value={hwStats
              ? `${hwStats.ram_used_gb.toFixed(1)} / ${hwStats.ram_total_gb.toFixed(1)} GB`
              : '— / — GB'}
            pct={hwStats?.ram_pct ?? 0}
            barColor="bg-blue-500"
          />
          <HwCard
            label="CPU"
            value={hwStats ? `${hwStats.cpu_utilization_pct.toFixed(0)}%` : '—'}
            pct={hwStats?.cpu_utilization_pct ?? 0}
            barColor="bg-zinc-400"
          />
        </div>

        {/* Sparkline chart: VRAM%, GPU%, Temp% over last 10 minutes */}
        {hwHistory.length > 1 && (
          <div className="mt-4">
            <ResponsiveContainer width="100%" height={80}>
              <ComposedChart
                data={hwHistory.map(h => ({
                  t: h.timestamp,
                  vram: h.gpu_vram_pct,
                  gpu: h.gpu_utilization_pct,
                  temp: Math.min(h.gpu_temp_celsius / 90 * 100, 100),
                }))}
                margin={{ top: 2, right: 4, bottom: 2, left: 4 }}
              >
                <Line type="monotone" dataKey="vram" name="VRAM%" stroke="#8b5cf6" dot={false} strokeWidth={1.5} isAnimationActive={false} />
                <Line type="monotone" dataKey="gpu" name="GPU%" stroke="#22c55e" dot={false} strokeWidth={1.5} isAnimationActive={false} />
                <Line type="monotone" dataKey="temp" name="Temp%" stroke="#f97316" dot={false} strokeWidth={1.5} isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="flex gap-4 mt-1 text-xs text-zinc-600">
              <span><span className="text-violet-500">■</span> VRAM%</span>
              <span><span className="text-green-500">■</span> GPU%</span>
              <span><span className="text-orange-500">■</span> Temp%</span>
            </div>
          </div>
        )}
      </div>

      {/* Content: fades when switching runs */}
      <div className={`space-y-6 transition-opacity duration-200 ${runLoading ? 'opacity-40' : 'opacity-100'}`}>

        {/* Training Controls */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h3 className="text-sm font-medium text-zinc-400 mb-4">Training Controls</h3>

          {controlLoading && stopPollStart !== null ? (
            /* Stopping state — polling for process to die */
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-zinc-400 text-sm">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-zinc-600 border-t-zinc-400" />
                Stopping training…
              </div>
              {Date.now() - stopPollStart > 10_000 && (
                <p className="text-yellow-400 text-xs">
                  Still running — run in CMD: <span className="font-mono">taskkill /F /T /PID {runningProcess?.pid}</span>
                </p>
              )}
            </div>
          ) : runningProcess ? (
            /* Running state */
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-green-400 animate-pulse" />
                <span className="text-green-400 text-sm font-medium">Training in progress</span>
              </div>
              <div className="text-xs text-zinc-500 space-y-1">
                <div>PID: <span className="font-mono text-zinc-400">{runningProcess.pid}</span></div>
                <div>Started {relativeTime(runningProcess.started_at)}</div>
              </div>
              <button
                onClick={() => setConfirmAction('stop')}
                className="px-4 py-2 rounded-lg text-sm bg-red-800 hover:bg-red-700 text-white transition-colors"
              >
                Stop Training
              </button>
            </div>
          ) : (
            /* Idle/Interrupted/Complete state */
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Resume from checkpoint</label>
                  <select
                    value={selectedCheckpoint ?? ''}
                    onChange={e => setSelectedCheckpoint(e.target.value || null)}
                    className="w-full bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500"
                  >
                    <option value="">Fresh start</option>
                    {checkpoints.filter(c => !c.is_interrupted).map(cp => (
                      <option key={cp.name} value={cp.name}>
                        {cp.name}
                        {cp.is_best ? ' (best)' : ''}
                        {cp.is_last ? ' (last)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Epochs</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={trainingEpochs}
                    onChange={e => setTrainingEpochs(Math.max(1, Math.min(10, parseInt(e.target.value) || 3)))}
                    className="w-full bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Conda env</label>
                  {condaEnvs ? (
                    <select
                      value={condaEnv}
                      onChange={e => setCondaEnv(e.target.value)}
                      className="w-full bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500"
                    >
                      {(condaEnvs.includes(condaEnv) ? condaEnvs : [condaEnv, ...condaEnvs]).map(env => (
                        <option key={env} value={env}>{env}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={condaEnv}
                      onChange={e => setCondaEnv(e.target.value)}
                      className="w-full bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500"
                    />
                  )}
                </div>
              </div>
              <button
                onClick={() => setConfirmAction('start')}
                className="px-4 py-2 rounded-lg text-sm bg-green-700 hover:bg-green-600 text-white transition-colors"
              >
                Start Training
              </button>
            </div>
          )}

          {controlError && !confirmAction && (
            <p className="mt-2 text-red-400 text-xs font-mono break-all">{controlError}</p>
          )}
        </div>

        {/* 1. Status Header */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <div className="flex items-center gap-3 mb-3">
            <span className="text-zinc-200 font-semibold">
              {status?.model_name ?? selectedRun ?? '—'}
            </span>
            <TrainingStatusBadge status={status?.status ?? 'idle'} />
            <span className="text-zinc-600 text-xs ml-auto">
              Updated {secondsAgo}s ago
            </span>
            <span
              className={`w-2 h-2 rounded-full ${sseConnected ? 'bg-green-500' : 'bg-zinc-600'}`}
              title={sseConnected ? 'SSE connected' : 'SSE disconnected'}
            />
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-zinc-500">Epoch </span>
              <span className="text-zinc-300">
                {(status?.current_epoch ?? 0).toFixed(2)} / {status?.max_epochs ?? 0}
              </span>
            </div>
            {status?.best_checkpoint && (
              <div>
                <span className="text-zinc-500">Best </span>
                <span className="text-zinc-300">
                  {status.best_checkpoint}
                  {status.best_eval_loss !== null && (
                    <span className="text-zinc-500"> (loss {status.best_eval_loss.toFixed(4)})</span>
                  )}
                </span>
              </div>
            )}
            {status?.latest_train_loss !== null && status?.latest_train_loss !== undefined && (
              <div>
                <span className="text-zinc-500">Latest train loss </span>
                <span className="text-zinc-300">{status.latest_train_loss.toFixed(4)}</span>
              </div>
            )}
          </div>
        </div>

        {/* 2. Progress Bar */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <div className="flex justify-between text-xs text-zinc-500 mb-2">
            <span>Progress</span>
            <span>{(status?.progress_pct ?? 0).toFixed(1)}%</span>
          </div>
          <div className="w-full bg-zinc-800 rounded-full h-3 mb-2">
            <div
              className="bg-violet-600 h-3 rounded-full transition-all"
              style={{ width: `${Math.min(status?.progress_pct ?? 0, 100)}%` }}
            />
          </div>
          <div className="text-xs text-zinc-500">
            {(status?.current_step ?? 0).toLocaleString()} / {(status?.max_steps ?? 0).toLocaleString()} steps
          </div>
          {status?.eta_info && (
            <div className="text-xs text-zinc-500 mt-1">
              ETA: {status.eta_info.eta} — {status.eta_info.sec_per_it.toFixed(1)}s/step
            </div>
          )}
        </div>

        {/* 3. Loss Chart */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h3 className="text-sm font-medium text-zinc-400 mb-4">Loss History</h3>
          {chartData.length === 0 ? (
            <div className="h-[260px] flex items-center justify-center text-zinc-600 text-sm">
              Loading chart data…
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                <XAxis
                  dataKey="step"
                  tick={{ fill: '#71717a', fontSize: 11 }}
                  tickFormatter={v => (v as number).toLocaleString()}
                />
                <YAxis
                  tick={{ fill: '#71717a', fontSize: 11 }}
                  tickFormatter={v => (v as number).toFixed(2)}
                  width={48}
                />
                <Tooltip
                  contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 }}
                  labelStyle={{ color: '#a1a1aa' }}
                  itemStyle={{ color: '#e4e4e7' }}
                  formatter={(value: unknown) => [(value as number).toFixed(4)]}
                  labelFormatter={v => `Step ${(v as number).toLocaleString()}`}
                />
                <Line
                  type="monotone"
                  dataKey="train_loss"
                  name="Train loss"
                  stroke="#7C6FCD"
                  dot={false}
                  isAnimationActive={false}
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="eval_loss"
                  name="Eval loss"
                  stroke="#F0997B"
                  dot={{ r: 3, fill: '#F0997B' }}
                  isAnimationActive={false}
                  connectNulls={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 4. Checkpoints */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h3 className="text-sm font-medium text-zinc-400 mb-4">Checkpoints</h3>
          {checkpoints.length === 0 ? (
            <p className="text-zinc-600 text-sm">No checkpoints found.</p>
          ) : (
            <div className="space-y-3">
              {checkpoints.map(cp => (
                <div
                  key={cp.name}
                  className="flex items-start justify-between rounded-lg border border-zinc-800 bg-zinc-950 p-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-200 font-mono text-sm">{cp.name}</span>
                      {cp.is_best && (
                        <span className="px-1.5 py-0.5 rounded text-xs bg-green-900/50 text-green-400 font-medium">BEST</span>
                      )}
                      {cp.is_last && (
                        <span className="px-1.5 py-0.5 rounded text-xs bg-blue-900/50 text-blue-400 font-medium">LAST</span>
                      )}
                      {cp.is_interrupted && (
                        <span className="px-1.5 py-0.5 rounded text-xs bg-yellow-900/50 text-yellow-400 font-medium">INTERRUPTED</span>
                      )}
                    </div>
                    <div className="text-xs text-zinc-500 space-x-3">
                      <span>Step {cp.step.toLocaleString()}</span>
                      <span>Epoch {cp.epoch.toFixed(2)}</span>
                      {cp.eval_loss !== null && <span>Loss {cp.eval_loss.toFixed(4)}</span>}
                      <span>{cp.folder_size_mb.toFixed(0)} MB</span>
                      <span>{new Date(cp.timestamp).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => copy(cp.full_path, `cp-path-${cp.name}`)}
                    className="ml-4 shrink-0 px-3 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
                  >
                    {copied === `cp-path-${cp.name}` ? 'Copied!' : 'Copy path'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 4.5. Pipeline Models (GGUF) */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h3 className="text-sm font-medium text-zinc-400 mb-4">Pipeline Models (GGUF)</h3>
          {ggufModels.length === 0 ? (
            <p className="text-zinc-600 text-sm">No GGUF models found.</p>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {ggufModels.map(model => (
                <div
                  key={model.name}
                  className="rounded-lg border border-zinc-800 bg-zinc-950 p-4"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <span className="text-zinc-200 font-medium text-sm">{model.display_name}</span>
                      <div className="flex items-center gap-2 mt-1">
                        {model.pipeline_role && (
                          <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${pipelineRoleStyle(model.pipeline_role)}`}>
                            {model.pipeline_role}
                          </span>
                        )}
                        {model.file_count > 0 ? (
                          <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-green-900/50 text-green-400">
                            Ready
                          </span>
                        ) : (
                          <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-zinc-800 text-zinc-500">
                            Not found
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="text-right text-xs text-zinc-500 ml-4 shrink-0">
                      <div>{model.size_gb.toFixed(1)} GB</div>
                      <div>{model.file_count} files</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 5. Log Feed */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            {(['training', 'backend'] as const).map(t => (
              <button key={t}
                onClick={() => setLogTab(t)}
                className={`text-xs px-2 py-0.5 rounded ${logTab === t ? 'bg-zinc-700 text-zinc-200' : 'text-zinc-500 hover:text-zinc-300'}`}
              >
                {t === 'training' ? 'Training Log' : 'Backend Log'}
              </button>
            ))}
            {logTab === 'training' && (
              <div className="flex items-center gap-1 ml-2 flex-wrap">
                {(['all', 'loss', 'progress', 'hardware', 'checkpoint', 'error'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setLogFilter(f)}
                    className={`text-xs px-1.5 py-0.5 rounded transition-colors ${logFilter === f ? 'bg-zinc-600 text-zinc-100' : 'text-zinc-600 hover:text-zinc-400'}`}
                  >
                    {f === 'all' ? 'All' : f === 'checkpoint' ? 'Checkpoints' : f.charAt(0).toUpperCase() + f.slice(1)}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div
            className="h-48 overflow-y-auto rounded-lg p-3 font-mono text-xs leading-relaxed"
            style={{ background: '#0d0d0d' }}
          >
            {logTab === 'training' ? (
              logLines.length === 0 ? (
                <div className="text-zinc-600">
                  No log file yet. Use Training Controls above to start a training job.
                </div>
              ) : (
                logLines
                  .filter(entry => logFilter === 'all' || entry.type === logFilter)
                  .map((entry, i) => (
                    <div key={i} className={`whitespace-pre-wrap break-all ${logLineClass(entry.type)}`}>
                      {entry.line}
                    </div>
                  ))
              )
            ) : (
              backendLogLines.length === 0 ? (
                <div className="text-zinc-600">
                  No backend log yet. Start the backend to generate log output.
                </div>
              ) : (
                backendLogLines.map((line, i) => {
                  const t = /\] ERROR\b|\] CRITICAL\b/.test(line) ? 'error' : 'info'
                  return (
                    <div key={i} className={`whitespace-pre-wrap break-all ${logLineClass(t)}`}>
                      {line}
                    </div>
                  )
                })
              )
            )}
            <div ref={logEndRef} />
          </div>
        </div>

        {/* 6. Quick Actions */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h3 className="text-sm font-medium text-zinc-400 mb-4">Quick Actions</h3>
          <div className="flex flex-wrap gap-3">
            {bestCp && (
              <button
                onClick={() => copy(bestCp.full_path, 'cp-path')}
                className="px-4 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
              >
                {copied === 'cp-path' ? 'Copied!' : 'Copy checkpoint path'}
              </button>
            )}
            <button
              onClick={() => copy(`${status?.scripts_path ?? ''}\\train_hime.py`, 'script-path')}
              className="px-4 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              {copied === 'script-path' ? 'Copied!' : 'Copy script path'}
            </button>
            {bestCp && (
              <button
                onClick={() => {
                  setSelectedCheckpoint(bestCp.name)
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
                className="px-4 py-2 rounded-lg text-sm bg-violet-700 hover:bg-violet-600 text-white transition-colors"
              >
                Resume Training
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
