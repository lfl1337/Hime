import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useStore } from '../store'
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from 'recharts'
import type { CheckpointInfo, GGUFModelInfo, HardwareStats, LossPoint, RunInfo, StopConfig, TrainingProcess, TrainingStatus } from '../api/training'
import {
  createTrainingEventSource,
  fetchAllRuns,
  fetchGGUFModels,
  getBackendLog,
  getCheckpoints,
  getHardwareStats,
  getLossHistory,
  getRunningProcesses,
  getStopConfig,
  getTrainingLog,
  getTrainingStatus,
  saveTrainingCheckpoint,
  startTraining,
  stopTraining,
  updateStopConfig,
} from '../api/training'

// ---------------------------------------------------------------------------
// Module-level log entry ID counter — gives each log line a stable React key
// ---------------------------------------------------------------------------

let _nextLogId = 0

// ---------------------------------------------------------------------------
// Stable Tooltip/Axis objects — defined outside component so React never sees
// a "new" reference on re-render, preventing unnecessary recharts repaints
// ---------------------------------------------------------------------------

const TOOLTIP_CONTENT_STYLE = { background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8 } as const
const TOOLTIP_LABEL_STYLE    = { color: '#a1a1aa' } as const
const TOOLTIP_ITEM_STYLE     = { color: '#e4e4e7' } as const
const AXIS_TICK_SM           = { fill: '#71717a', fontSize: 10 } as const
const AXIS_TICK_LG           = { fill: '#71717a', fontSize: 11 } as const
const LOSS_CHART_MARGIN      = { top: 4, right: 16, bottom: 4, left: 0 } as const
const HW_CHART_MARGIN        = { top: 2, right: 8,  bottom: 2, left: 0 } as const

function fmtLoss(value: unknown): [string] { return [(value as number).toFixed(4)] }
function fmtLossLabel(v: unknown): string  { return `Step ${(v as number).toLocaleString()}` }
function fmtPct(value: unknown): [string]  { return [`${(value as number).toFixed(1)}%`] }
function fmtEmpty(): string                { return '' }
function fmtStep(v: unknown): string       { return (v as number).toLocaleString() }
function fmtLossAxis(v: unknown): string   { return (v as number).toFixed(2) }

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
// useInterval — stable polling hook
// ---------------------------------------------------------------------------

function useInterval(callback: () => void, delay: number, active = true, label?: string) {
  const savedCallback = useRef(callback)
  useEffect(() => { savedCallback.current = callback }, [callback])
  useEffect(() => {
    if (!active) return
    if (label) console.log(`[${label}] interval start (${delay}ms)`)
    const id = setInterval(() => savedCallback.current(), delay)
    return () => {
      if (label) console.log(`[${label}] interval stop`)
      clearInterval(id)
    }
  }, [delay, active, label])
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

const HwCard = memo(function HwCard({ label, value, sub, pct, barColor }: HwCardProps) {
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
})

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
// Downsample — reduce an array to at most maxPoints entries
// ---------------------------------------------------------------------------

function downsample<T>(data: T[], maxPoints: number): T[] {
  if (data.length <= maxPoints) return data
  const step = Math.ceil(data.length / maxPoints)
  return data.filter((_, i) => i % step === 0)
}

// ---------------------------------------------------------------------------
// Model → LoRA output directory mapping
// ---------------------------------------------------------------------------

const MODEL_TO_LORA_DIR: Record<string, string> = {
  qwen32b:  'Qwen2.5-32B-Instruct',
  qwen14b:  'Qwen2.5-14B-Instruct',
  qwen72b:  'Qwen2.5-72B-Instruct',
  gemma27b: 'Gemma-3-27B-IT',
  deepseek: 'DeepSeek-R1-Distill-Qwen-32B',
}

// ---------------------------------------------------------------------------
// LossChart — memoized; full-featured with metric toggles, dual Y-axis, epoch markers
// ---------------------------------------------------------------------------

interface LossChartProps {
  chartData: Array<{
    step: number
    epoch?: number | null
    train_loss: number | null
    eval_loss: number | null
    learning_rate?: number | null
    grad_norm?: number | null
  }>
  visibleMetrics: { trainLoss: boolean; evalLoss: boolean; learningRate: boolean; gradNorm: boolean }
  epochBoundaries: Array<{ step: number; label: string }>
  onToggleMetric: (key: keyof { trainLoss: boolean; evalLoss: boolean; learningRate: boolean; gradNorm: boolean }) => void
}

const fmtLrAxis = (v: unknown): string => {
  const n = v as number
  if (n === 0) return '0'
  return n.toExponential(1)
}

const METRIC_CFG = [
  { key: 'trainLoss'    as const, label: 'Train Loss',    color: '#8B5CF6' },
  { key: 'evalLoss'     as const, label: 'Eval Loss',     color: '#EF4444' },
  { key: 'learningRate' as const, label: 'Learning Rate', color: '#9CA3AF' },
  { key: 'gradNorm'     as const, label: 'Grad Norm',     color: '#F59E0B' },
]

const LossChart = memo(function LossChart({ chartData, visibleMetrics, epochBoundaries, onToggleMetric }: LossChartProps) {
  const showGradNorm = visibleMetrics.gradNorm
  const showLr = visibleMetrics.learningRate
  return (
    <>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mb-3">
        {METRIC_CFG.map(({ key, label, color }) => (
          <label
            key={key}
            className="flex items-center gap-1.5 cursor-pointer select-none text-xs"
            style={{ color: visibleMetrics[key] ? color : '#52525b' }}
          >
            <input
              type="checkbox"
              checked={visibleMetrics[key]}
              onChange={() => onToggleMetric(key)}
              style={{ accentColor: color, cursor: 'pointer' }}
            />
            {label}
          </label>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={chartData} margin={LOSS_CHART_MARGIN}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis dataKey="step" tick={AXIS_TICK_LG} tickFormatter={fmtStep} />
          <YAxis yAxisId="left" tick={AXIS_TICK_LG} tickFormatter={fmtLossAxis} width={48} />
          {showGradNorm && (
            <YAxis yAxisId="gradNorm" orientation="right" tick={AXIS_TICK_LG} tickFormatter={fmtLrAxis} width={64} />
          )}
          {showLr && (
            <YAxis yAxisId="lr" orientation="right" hide={true} domain={['auto', 'auto']} />
          )}
          <Tooltip
            contentStyle={TOOLTIP_CONTENT_STYLE}
            labelStyle={TOOLTIP_LABEL_STYLE}
            itemStyle={TOOLTIP_ITEM_STYLE}
            formatter={(value: unknown, name: string) => [
              typeof value === 'number' ? value.toFixed(6) : String(value),
              name,
            ]}
            labelFormatter={fmtLossLabel}
          />
          {epochBoundaries.map(({ step, label }) => (
            <ReferenceLine
              key={step}
              x={step}
              yAxisId="left"
              stroke="#3f3f46"
              strokeDasharray="4 2"
              label={{ value: label, position: 'insideTopRight', fill: '#71717a', fontSize: 10 }}
            />
          ))}
          {visibleMetrics.trainLoss && (
            <Line
              yAxisId="left" type="monotone" dataKey="train_loss" name="Train Loss"
              stroke="#8B5CF6" strokeWidth={2} dot={false} activeDot={false}
              isAnimationActive={false} connectNulls={true}
            />
          )}
          {visibleMetrics.evalLoss && (
            <Line
              yAxisId="left" type="monotone" dataKey="eval_loss" name="Eval Loss"
              stroke="#EF4444" strokeWidth={2.5} dot={{ r: 4, fill: '#EF4444' }} activeDot={false}
              isAnimationActive={false} connectNulls={true}
            />
          )}
          {visibleMetrics.learningRate && (
            <Line
              yAxisId="lr" type="monotone" dataKey="learning_rate" name="Learning Rate"
              stroke="#9CA3AF" strokeWidth={1} strokeDasharray="4 2" dot={false} activeDot={false}
              isAnimationActive={false} connectNulls={false}
            />
          )}
          {visibleMetrics.gradNorm && (
            <Line
              yAxisId="gradNorm" type="monotone" dataKey="grad_norm" name="Grad Norm"
              stroke="#F59E0B" strokeWidth={1} dot={false} activeDot={false}
              isAnimationActive={false} connectNulls={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </>
  )
})

// ---------------------------------------------------------------------------
// HwChart — memoized to prevent recharts re-render on 1s timestamp ticks
// ---------------------------------------------------------------------------

interface HwChartProps { hwChartData: HardwareStats[]; hwHistoryLength: number }

const HwChart = memo(function HwChart({ hwChartData, hwHistoryLength }: HwChartProps) {
  return (
    <div className="mt-4">
      <div className="text-xs text-zinc-600 mb-1">Last {hwHistoryLength} samples</div>
      <ResponsiveContainer width="100%" height={120}>
        <ComposedChart data={hwChartData} margin={HW_CHART_MARGIN}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis dataKey="timestamp" hide />
          <YAxis domain={[0, 100]} width={28} tick={AXIS_TICK_SM} />
          <Tooltip
            contentStyle={TOOLTIP_CONTENT_STYLE}
            labelStyle={TOOLTIP_LABEL_STYLE}
            itemStyle={TOOLTIP_ITEM_STYLE}
            formatter={fmtPct}
            labelFormatter={fmtEmpty}
          />
          <Line dataKey="gpu_vram_pct" stroke="#8b5cf6" dot={false} activeDot={false} name="VRAM%" isAnimationActive={false} />
          <Line dataKey="gpu_utilization_pct" stroke="#22c55e" dot={false} activeDot={false} name="GPU%" isAnimationActive={false} />
          <Line dataKey="ram_pct" stroke="#f59e0b" dot={false} activeDot={false} name="RAM%" isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-1 text-xs text-zinc-600">
        <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-violet-500 inline-block" />VRAM%</span>
        <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-green-500 inline-block" />GPU%</span>
        <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-yellow-500 inline-block" />RAM%</span>
      </div>
    </div>
  )
})

// ---------------------------------------------------------------------------
// Default stop config
// ---------------------------------------------------------------------------

const DEFAULT_STOP_CONFIG: StopConfig = {
  stop_mode: 'none',
  target_loss: null,
  target_loss_metric: 'loss',
  target_confirmations: 3,
  patience: null,
  patience_metric: 'eval_loss',
  min_delta: 0.001,
  min_steps: 0,
  max_epochs: 3,
}

// ---------------------------------------------------------------------------
// SmartStopStatus — shows active smart-stop state below progress bar
// ---------------------------------------------------------------------------

function SmartStopStatus({ status, stopConfig }: {
  status: TrainingStatus | null
  stopConfig: StopConfig | null
}) {
  const sc = status?.stop_config
  const cfgMode = stopConfig?.stop_mode ?? 'none'
  if (!sc && cfgMode === 'none') return null
  const mode = sc?.mode ?? cfgMode
  if (mode === 'none') return null

  return (
    <div className="text-xs text-zinc-500 mt-1 flex flex-wrap gap-x-3">
      <span className="text-zinc-600">Smart Stop:</span>
      {(mode === 'patience' || mode === 'both') && (
        <span>
          Patience{' '}
          {sc != null && sc.patience_remaining !== null && sc.patience !== null
            ? `${sc.patience_remaining}/${sc.patience} remaining`
            : stopConfig?.patience !== null && stopConfig?.patience !== undefined
              ? `${stopConfig.patience} evals configured`
              : '—'}
        </span>
      )}
      {(mode === 'threshold' || mode === 'both') && (
        <span>
          Target {sc != null ? sc.target_reached_count : 0}/{sc != null ? sc.target_confirmations : (stopConfig?.target_confirmations ?? 3)} confirmations
          {stopConfig?.target_loss !== null && stopConfig?.target_loss !== undefined ? ` (≤ ${stopConfig.target_loss})` : ''}
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TrainingMonitor
// ---------------------------------------------------------------------------

export function TrainingMonitor() {
  useEffect(() => {
    console.log('[TrainingMonitor] mount')
    return () => console.log('[TrainingMonitor] unmount')
  }, [])

  const [runs, setRuns] = useState<RunInfo[]>([])
  const [runsLoaded, setRunsLoaded] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const [ggufModels, setGgufModels] = useState<GGUFModelInfo[]>([])
  const [runLoading, setRunLoading] = useState(false)
  const [status, setStatus] = useState<TrainingStatus | null>(null)
  const [checkpoints, setCheckpoints] = useState<CheckpointInfo[]>([])
  const [lossHistory, setLossHistory] = useState<LossPoint[]>([])
  const [logLines, setLogLines] = useState<Array<{ id: number; line: string; type: string }>>([])
  const [lastUpdated, setLastUpdated] = useState<number>(Date.now())
  const [sseConnected, setSseConnected] = useState(false)
  const [secondsAgo, setSecondsAgo] = useState(0)
  const [hwSecondsAgo, setHwSecondsAgo] = useState<number | null>(null)

  // Log tab state
  const [logTab, setLogTab] = useState<'training' | 'backend'>('training')
  const [backendLogLines, setBackendLogLines] = useState<string[]>([])

  // Hardware monitor state
  const [hwStats, setHwStats] = useState<HardwareStats | null>(null)
  const [hwRefreshing, setHwRefreshing] = useState(false)
  const [hwHistory, setHwHistory] = useState<HardwareStats[]>([])
  const [hwLastUpdated, setHwLastUpdated] = useState<number | null>(null)
  const [hwError, setHwError] = useState(false)

  // Training model selector + per-model checkpoints
  const [selectedModelKey, setSelectedModelKey] = useState<string>('qwen32b')
  const [modelCheckpoints, setModelCheckpoints] = useState<CheckpointInfo[]>([])

  // Log filter state
  const [logFilter, setLogFilter] = useState<'all' | 'loss' | 'progress' | 'hardware' | 'checkpoint' | 'error'>('all')

  // Metric visibility toggles for LossChart
  const [visibleMetrics, setVisibleMetrics] = useState({
    trainLoss: true,
    evalLoss: true,
    learningRate: false,
    gradNorm: false,
  })
  const [showMetricInfo, setShowMetricInfo] = useState(false)

  const handleToggleMetric = useCallback(
    (key: keyof typeof visibleMetrics) =>
      setVisibleMetrics(prev => ({ ...prev, [key]: !prev[key] })),
    [],
  )

  // Config panel state
  const [configPanelOpen, setConfigPanelOpen] = useState(false)
  const [stopConfig, setStopConfig] = useState<StopConfig | null>(null)
  const [configDraft, setConfigDraft] = useState<StopConfig | null>(null)
  const [configSaving, setConfigSaving] = useState(false)
  const [configErrors, setConfigErrors] = useState<Record<string, string>>({})

  // Training controls state
  const [trainingEpochs, setTrainingEpochs] = useState<number>(() =>
    parseInt(localStorage.getItem('hime_default_epochs') ?? '3') || 3
  )
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<string | null>(null)
  const [runningProcesses, setRunningProcesses] = useState<TrainingProcess[]>([])
  const [controlError, setControlError] = useState<string | null>(null)
  const [confirmAction, setConfirmAction] = useState<'start' | 'stop' | null>(null)
  const [controlLoading, setControlLoading] = useState(false)
  const [stopPollStart, setStopPollStart] = useState<number | null>(null)
  const [savingCheckpoint, setSavingCheckpoint] = useState(false)
  const [saveCheckpointFeedback, setSaveCheckpointFeedback] = useState<'success' | 'error' | null>(null)
  const stopPollRef = useRef<number | null>(null)

  // "Pause live updates" — persisted across sessions; stops SSE + HW polling
  const [liveUpdatesPaused, setLiveUpdatesPaused] = useState(() =>
    localStorage.getItem('hime_live_paused') === '1'
  )

  const isWindowVisible = useStore(s => s.isWindowVisible)

  const logEndRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)
  const fallbackRef = useRef<number | null>(null)
  const selectedRunRef = useRef<string | null>(null)
  const lastUpdatedRef = useRef<number>(Date.now())
  const hwLastUpdatedRef = useRef<number | null>(null)

  // Mount effect: fetch runs and GGUF models in parallel, then select first run
  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setLoadError('Request timed out after 10 seconds — check that the backend is running.')
      setRunsLoaded(true)
    }, 10_000)

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

  // Load stop config on mount
  useEffect(() => {
    getStopConfig().then(setStopConfig).catch(() => {})
  }, [])

  // Keep selectedRunRef in sync with selectedRun
  useEffect(() => {
    selectedRunRef.current = selectedRun
  }, [selectedRun])

  // Fetch checkpoints for the selected training model when model key changes
  useEffect(() => {
    const loraDir = MODEL_TO_LORA_DIR[selectedModelKey]
    if (!loraDir) return
    getCheckpoints(loraDir)
      .then(cps => {
        setModelCheckpoints(cps)
        // Auto-select based on stored preference
        const pref = localStorage.getItem('hime_default_checkpoint') ?? 'best'
        const valid = cps.filter(c => !c.is_interrupted)
        const chosen = pref === 'latest'
          ? (valid.sort((a, b) => b.step - a.step)[0] ?? null)
          : (valid.find(c => c.is_best) ?? valid.find(c => c.is_last) ?? null)
        setSelectedCheckpoint(chosen ? chosen.name : null)
      })
      .catch(() => { setModelCheckpoints([]); setSelectedCheckpoint(null) })
  }, [selectedModelKey])

  // selectedRun effect: load data and connect SSE for the selected run
  useEffect(() => {
    if (selectedRun === null || !isWindowVisible || liveUpdatesPaused) return

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
      if (lh.status === 'fulfilled') setLossHistory(lh.value.slice(-500))
      if (ll.status === 'fulfilled') setLogLines(ll.value.map(line => ({ id: ++_nextLogId, line, type: 'info' })))
      setRunLoading(false)
    })

    // Status-only SSE handler — log/loss events removed (fetch on demand)
    const statusHandler = (e: MessageEvent<string>) => {
      if (aborted) return
      try {
        const s = JSON.parse(e.data) as TrainingStatus
        setStatus(s)
        setLastUpdated(Date.now())
      } catch { /* ignore parse errors */ }
    }

    // Connect SSE
    console.log('[Training SSE] opening for run:', selectedRun)
    createTrainingEventSource(selectedRun).then(es => {
      if (aborted) {
        es.close()
        return
      }
      esRef.current = es

      es.addEventListener('status', statusHandler)

      es.addEventListener('loss_history_batch', (e: MessageEvent) => {
        if (aborted) return
        try {
          const points = JSON.parse(e.data) as LossPoint[]
          setLossHistory(points.slice(-500))
        } catch { /* ignore parse errors */ }
      })

      es.onopen = () => {
        if (!aborted) {
          console.log('[Training SSE] open')
          setSseConnected(true)
        }
      }

      es.onerror = () => {
        if (aborted) return
        console.log('[Training SSE] error — closing, starting 30s fallback poll')
        setSseConnected(false)
        es.removeEventListener('status', statusHandler)
        es.onopen  = null
        es.onerror = null
        es.close()
        esRef.current = null
        // Fallback: poll status every 30s
        if (fallbackRef.current === null) {
          fallbackRef.current = window.setInterval(() => {
            const currentRun = selectedRunRef.current
            if (currentRun === null) return
            getTrainingStatus(currentRun).then(s => {
              if (!aborted) { setStatus(s); setLastUpdated(Date.now()) }
            }).catch(() => {})
          }, 30_000)
        }
      }
    }).catch(() => {
      if (!aborted) setSseConnected(false)
    })

    return () => {
      aborted = true
      console.log('[Training SSE] close (run:', selectedRun, ')')
      if (esRef.current) {
        esRef.current.removeEventListener('status', statusHandler)
        esRef.current.onopen  = null
        esRef.current.onerror = null
        esRef.current.close()
        esRef.current = null
      }
      if (fallbackRef.current !== null) {
        clearInterval(fallbackRef.current)
        fallbackRef.current = null
      }
      if (stopPollRef.current !== null) {
        clearInterval(stopPollRef.current)
        stopPollRef.current = null
      }
    }
  }, [selectedRun, isWindowVisible, liveUpdatesPaused])

  // Keep timestamp refs in sync — lets the stable 1 Hz intervals below read
  // the latest value without being recreated on every status / HW update.
  useEffect(() => { lastUpdatedRef.current = lastUpdated }, [lastUpdated])
  useEffect(() => { hwLastUpdatedRef.current = hwLastUpdated }, [hwLastUpdated])

  // "X seconds ago" tickers — stop when window is hidden to avoid unnecessary
  // re-renders of the large TrainingMonitor tree (~3600/hour when always-on).
  useInterval(
    () => {
      setSecondsAgo(Math.floor((Date.now() - lastUpdatedRef.current) / 1000))
      if (hwLastUpdatedRef.current !== null) {
        setHwSecondsAgo(Math.floor((Date.now() - hwLastUpdatedRef.current) / 1000))
      }
    },
    1000,
    isWindowVisible,
  )

  // Hardware auto-polling every 10s — stops when hidden or manually paused
  useInterval(
    () => {
      getHardwareStats()
        .then(s => {
          setHwStats(s)
          setHwHistory(prev => [...prev.slice(-59), s])
          setHwLastUpdated(Date.now())
          setHwError(false)
        })
        .catch(() => setHwError(true))
    },
    10_000,
    isWindowVisible && !liveUpdatesPaused,
    'HW polling',
  )

  // Checkpoint polling every 60s — keeps the list fresh during an active training run
  useInterval(
    () => {
      const currentRun = selectedRunRef.current
      if (currentRun === null) return
      getCheckpoints(currentRun).then(cps => setCheckpoints(cps)).catch(() => {})
    },
    60_000,
    isWindowVisible && selectedRun !== null,
    'Checkpoint polling',
  )

  // Memory pressure detection — trim state arrays if JS heap > 500MB
  useEffect(() => {
    const check = setInterval(() => {
      const mem = (performance as any).memory
      if (!mem) return
      const usedMB = mem.usedJSHeapSize / 1024 / 1024
      if (usedMB > 500) {
        console.warn(`High memory: ${usedMB.toFixed(0)}MB — trimming state`)
        setLossHistory(prev => prev.slice(-200))
        setHwHistory(prev => prev.slice(-30))
        setLogLines(prev => prev.slice(-20))
      }
    }, 30_000)
    return () => clearInterval(check)
  }, [])

  // Expose debug state to window for Settings memory profiler
  useEffect(() => {
    ;(window as any).__himeDebug = {
      lossHistoryLength: lossHistory.length,
      hwHistoryLength: hwHistory.length,
      logLinesLength: logLines.length,
      backendLogLinesLength: backendLogLines.length,
    }
  }, [lossHistory.length, hwHistory.length, logLines.length, backendLogLines.length])

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logLines])

  // Chart data: downsample train_loss to ≤200 points; keep ALL eval_loss points (there are few).
  // Bug fix: do NOT apply downsample() to the combined array — it drops ~66% of eval_loss points
  // by index since eval entries are interspersed with much more frequent train entries.
  const chartData = useMemo(() => {
    const trainPoints = lossHistory.filter(p => p.train_loss !== null)
    const trainDownsampled = downsample(trainPoints, 200)
    const trainStepsKept = new Set(trainDownsampled.map(p => p.step))
    const evalStepsAll = new Set(
      lossHistory.filter(p => p.eval_loss !== null).map(p => p.step)
    )
    return lossHistory
      .filter(p => trainStepsKept.has(p.step) || evalStepsAll.has(p.step))
      .map(p => ({
        step: p.step,
        epoch: p.epoch,
        train_loss: trainStepsKept.has(p.step) ? p.train_loss : null,
        eval_loss: evalStepsAll.has(p.step) ? p.eval_loss : null,
        learning_rate: p.learning_rate,
        grad_norm: p.grad_norm,
      }))
  }, [lossHistory])

  // Hardware chart data: already capped at 60, memoized to avoid object churn
  const hwChartData = useMemo(() => downsample(hwHistory, 60), [hwHistory])

  const epochBoundaries = useMemo(() => {
    const boundaries: Array<{ step: number; label: string }> = []
    let lastEpoch = -1
    for (const p of chartData) {
      const e = Math.floor(p.epoch ?? -1)
      if (e > lastEpoch && e > 0) {
        lastEpoch = e
        boundaries.push({ step: p.step, label: `E${e}` })
      }
    }
    return boundaries
  }, [chartData])

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
    const trainingModelName = MODEL_TO_LORA_DIR[selectedModelKey] ?? selectedRun
    try {
      await startTraining({
        model_name: trainingModelName,
        resume_checkpoint: selectedCheckpoint,
        epochs: trainingEpochs,
        model_key: selectedModelKey,
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

  async function handleSaveCheckpoint() {
    if (!selectedRun) return
    setSavingCheckpoint(true)
    setSaveCheckpointFeedback(null)
    try {
      await saveTrainingCheckpoint(selectedRun)
      setSaveCheckpointFeedback('success')
      window.setTimeout(() => setSaveCheckpointFeedback(null), 3000)
    } catch {
      setSaveCheckpointFeedback('error')
      window.setTimeout(() => setSaveCheckpointFeedback(null), 4000)
    } finally {
      setSavingCheckpoint(false)
    }
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
      <div className="flex flex-wrap items-center gap-2 mb-2">
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
        <button
          onClick={() => {
            setConfigDraft(stopConfig ? { ...stopConfig } : { ...DEFAULT_STOP_CONFIG })
            setConfigPanelOpen(true)
          }}
          className="ml-auto flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 transition-colors px-2 py-1 rounded-lg hover:bg-zinc-800"
          title="Training Settings"
        >
          <span>&#9881;</span>
          <span>Training Settings</span>
        </button>
      </div>

      {/* Hardware Monitor */}
      <div className={`rounded-xl border bg-zinc-900 p-5 transition-colors ${hwError ? 'border-zinc-700' : 'border-zinc-800'}`}>
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-medium text-zinc-400">Hardware</h3>
            <span className={`text-xs px-1.5 py-0.5 rounded bg-zinc-800 ${liveUpdatesPaused ? 'text-yellow-500' : hwError ? 'text-zinc-500' : 'text-zinc-500'}`}>
              {liveUpdatesPaused ? 'Updates paused' : hwError ? 'Error — retrying' : 'Polling every 10s'}
            </span>
            {!liveUpdatesPaused && hwSecondsAgo !== null && (
              <span className="text-xs text-zinc-600">
                Updated {hwSecondsAgo}s ago
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                const next = !liveUpdatesPaused
                setLiveUpdatesPaused(next)
                if (next) localStorage.setItem('hime_live_paused', '1')
                else localStorage.removeItem('hime_live_paused')
              }}
              className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${
                liveUpdatesPaused
                  ? 'bg-yellow-800/40 hover:bg-yellow-700/50 text-yellow-400'
                  : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200'
              }`}
            >
              {liveUpdatesPaused ? 'Resume updates' : 'Pause updates'}
            </button>
            <button
              onClick={() => {
                setHwRefreshing(true)
                getHardwareStats()
                  .then(s => {
                    setHwStats(s)
                    setHwHistory(prev => [...prev.slice(-59), s])
                    setHwLastUpdated(Date.now())
                    setHwError(false)
                  })
                  .catch(() => setHwError(true))
                  .finally(() => setHwRefreshing(false))
              }}
              disabled={hwRefreshing}
              className="text-xs px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors disabled:opacity-50"
            >
              {hwRefreshing ? 'Refreshing…' : 'Refresh now'}
            </button>
          </div>
        </div>
        <div className={`grid grid-cols-3 gap-3 sm:grid-cols-6 transition-opacity ${hwError ? 'opacity-50' : 'opacity-100'}`}>
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

        {/* HW History Chart */}
        {hwChartData.length > 1 && (
          <HwChart hwChartData={hwChartData} hwHistoryLength={hwHistory.length} />
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
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={() => setConfirmAction('stop')}
                  className="px-4 py-2 rounded-lg text-sm bg-red-800 hover:bg-red-700 text-white transition-colors"
                >
                  Stop Training
                </button>
                <button
                  onClick={() => void handleSaveCheckpoint()}
                  disabled={savingCheckpoint}
                  className="px-4 py-2 rounded-lg text-sm bg-zinc-700 hover:bg-zinc-600 text-zinc-200 transition-colors disabled:opacity-50"
                  title="Force an immediate checkpoint save"
                >
                  {savingCheckpoint ? 'Saving…' : '💾 Save Checkpoint'}
                </button>
                {saveCheckpointFeedback === 'success' && (
                  <span className="text-green-400 text-xs">Signal sent — checkpoint will save at next step</span>
                )}
                {saveCheckpointFeedback === 'error' && (
                  <span className="text-red-400 text-xs">Failed to send save signal</span>
                )}
              </div>
            </div>
          ) : (
            /* Idle/Interrupted/Complete state */
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">
                    Resume from checkpoint
                    <span className="ml-1 text-zinc-600">({MODEL_TO_LORA_DIR[selectedModelKey]})</span>
                  </label>
                  {modelCheckpoints.filter(c => !c.is_interrupted).length === 0 ? (
                    <div className="w-full bg-zinc-800 border border-zinc-700 text-zinc-600 text-xs rounded-lg px-3 py-2">
                      No checkpoints — will start fresh
                    </div>
                  ) : (
                    <select
                      value={selectedCheckpoint ?? ''}
                      onChange={e => setSelectedCheckpoint(e.target.value || null)}
                      className="w-full bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500"
                    >
                      <option value="">Fresh start</option>
                      {modelCheckpoints.filter(c => !c.is_interrupted).map(cp => (
                        <option key={cp.name} value={cp.name}>
                          {cp.name}
                          {cp.is_best ? ' (best)' : ''}
                          {cp.is_last ? ' (last)' : ''}
                        </option>
                      ))}
                    </select>
                  )}
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
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Model</label>
                <div className="flex gap-1 flex-wrap">
                  {[
                    { key: 'qwen32b', label: 'Qwen2.5-32B' },
                    { key: 'qwen14b', label: 'Qwen2.5-14B' },
                    { key: 'qwen72b', label: 'Qwen2.5-72B' },
                    { key: 'gemma27b', label: 'Gemma 3-27B' },
                    { key: 'deepseek', label: 'DeepSeek-R1-32B' },
                  ].map(opt => (
                    <button
                      key={opt.key}
                      onClick={() => setSelectedModelKey(opt.key)}
                      className={`px-2.5 py-1 rounded-md text-xs transition-colors ${
                        selectedModelKey === opt.key
                          ? 'bg-violet-700 text-white'
                          : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
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
          <SmartStopStatus status={status} stopConfig={stopConfig} />
        </div>

        {/* 3. Loss Chart */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h3 className="text-sm font-medium text-zinc-400 mb-4">Loss History</h3>
          {chartData.length === 0 ? (
            <div className="h-[260px] flex items-center justify-center text-zinc-600 text-sm">
              Loading chart data…
            </div>
          ) : (
            <LossChart
              chartData={chartData}
              visibleMetrics={visibleMetrics}
              epochBoundaries={epochBoundaries}
              onToggleMetric={handleToggleMetric}
            />
          )}

          {/* Metric Info Panel */}
          <div className="mt-3 border-t border-zinc-800 pt-2">
            <button
              onClick={() => setShowMetricInfo(v => !v)}
              className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1"
            >
              <span>ℹ</span>
              <span>Was bedeuten diese Werte?</span>
              <span className="ml-1">{showMetricInfo ? '▲' : '▼'}</span>
            </button>

            {showMetricInfo && (
              <div className="mt-3 rounded-lg bg-zinc-800/90 p-4 text-sm space-y-4">
                <p className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                  📊 Metriken-Erklärung
                </p>
                <div>
                  <p className="font-semibold text-purple-400">Train Loss</p>
                  <p className="text-zinc-400 text-xs mt-1">Wie gut das Modell die Trainingsdaten lernt.</p>
                  <div className="mt-1 space-y-0.5 text-xs text-zinc-400">
                    <p>✅ Gut: &lt; 0.5 (Modell lernt effektiv)</p>
                    <p>⚠️ Okay: 0.5 – 0.8 (lernt noch, braucht mehr Zeit)</p>
                    <p>🔴 Hoch: &gt; 1.0 (Anfang oder Problem)</p>
                    <p>📉 Sollte über die Zeit sinken</p>
                  </div>
                </div>
                <div>
                  <p className="font-semibold text-red-400">Eval Loss</p>
                  <p className="text-zinc-400 text-xs mt-1">Wie gut das Modell auf NEUEN Daten generalisiert.</p>
                  <div className="mt-1 space-y-0.5 text-xs text-zinc-400">
                    <p>✅ Gut: &lt; 0.95 (verbessert sich gegenüber Base Model)</p>
                    <p>⚠️ Stagniert: Mehrere Evals ohne Verbesserung</p>
                    <p>🔴 Steigt: Overfitting — Modell memoriert statt zu lernen</p>
                    <p>📉 Wichtigster Indikator für echte Qualität</p>
                  </div>
                </div>
                <div>
                  <p className="font-semibold text-zinc-400">Learning Rate</p>
                  <p className="text-zinc-400 text-xs mt-1">Schrittgröße beim Lernen.</p>
                  <div className="mt-1 space-y-0.5 text-xs text-zinc-400">
                    <p>📉 Sinkt planmäßig von ~2e-4 gegen 0 (Cosine Schedule)</p>
                    <p>ℹ️ Kein "gut" oder "schlecht" — folgt dem Scheduler</p>
                  </div>
                </div>
                <div>
                  <p className="font-semibold text-amber-400">Grad Norm</p>
                  <p className="text-zinc-400 text-xs mt-1">Wie stark die Gewichte pro Schritt angepasst werden.</p>
                  <div className="mt-1 space-y-0.5 text-xs text-zinc-400">
                    <p>✅ Stabil: 0.3 – 0.7 (gleichmäßiges Lernen)</p>
                    <p>⚠️ Spikes: &gt; 1.0 (schwieriger Batch, normalerweise harmlos)</p>
                    <p>🔴 Explodiert: &gt; 5.0 dauerhaft (Training instabil)</p>
                  </div>
                </div>
                <div>
                  <p className="font-semibold text-zinc-300">Epoch-Marker (E2, E3)</p>
                  <p className="text-zinc-400 text-xs mt-1">Start einer neuen Epoche.</p>
                  <div className="mt-1 space-y-0.5 text-xs text-zinc-400">
                    <p>ℹ️ Loss steigt kurz am Epochenanfang — das ist NORMAL</p>
                    <p>📉 Sollte danach schnell wieder fallen</p>
                  </div>
                </div>
              </div>
            )}
          </div>
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
          <p className="mt-3 text-xs text-zinc-600">
            Hinweis: Aktuelles Training speichert max. 3 Checkpoints (Änderung greift beim nächsten Start)
          </p>
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
            {/* Line count — confirms log lines are never auto-accumulated (cap = 20) */}
            {logTab === 'training' && (
              <span className="text-xs text-zinc-700">{logLines.length} / 20 lines</span>
            )}
            {/* Manual refresh — no automatic polling */}
            <button
              onClick={() => {
                if (logTab === 'training' && selectedRun) {
                  getTrainingLog(20, selectedRun)
                    .then(lines => setLogLines(lines.map(l => ({ id: ++_nextLogId, line: l, type: 'info' }))))
                    .catch(() => {})
                } else if (logTab === 'backend') {
                  getBackendLog(50).then(d => setBackendLogLines(d.lines.slice(-50))).catch(() => {})
                }
              }}
              className="ml-auto text-xs px-2.5 py-1 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors"
            >
              Refresh Log
            </button>
            {logTab === 'training' && (
              <div className="flex items-center gap-1 flex-wrap">
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
                  .slice(-20)
                  .map((entry) => (
                    <div key={entry.id} className={`whitespace-pre-wrap break-all ${logLineClass(entry.type)}`}>
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
                backendLogLines.slice(-20).map((line) => {
                  const t = /\] ERROR\b|\] CRITICAL\b/.test(line) ? 'error' : 'info'
                  return (
                    <div key={line} className={`whitespace-pre-wrap break-all ${logLineClass(t)}`}>
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

      {/* Training Config Panel */}
      {configPanelOpen && configDraft && (
        <div
          className="fixed inset-y-0 right-0 w-80 bg-zinc-950 border-l border-zinc-800 z-50 flex flex-col overflow-hidden"
          style={{ boxShadow: '-4px 0 24px rgba(0,0,0,0.5)' }}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-zinc-800 shrink-0">
            <h3 className="text-sm font-medium text-zinc-200">Training Settings</h3>
            <button
              onClick={() => setConfigPanelOpen(false)}
              className="text-zinc-500 hover:text-zinc-200 transition-colors text-lg leading-none"
            >
              &#10005;
            </button>
          </div>

          {/* Scrollable body */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">

            {/* Stop Mode */}
            <div>
              <label className="block text-xs text-zinc-500 mb-1">Stop Mode</label>
              <select
                value={configDraft.stop_mode}
                onChange={e => setConfigDraft(d => ({ ...d!, stop_mode: e.target.value as StopConfig['stop_mode'] }))}
                className="w-full bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500"
              >
                <option value="none">Fixed Epochs Only</option>
                <option value="threshold">Threshold Only</option>
                <option value="patience">Patience Only</option>
                <option value="both">Both (Threshold + Patience)</option>
              </select>
            </div>

            {/* Threshold section */}
            {(configDraft.stop_mode === 'threshold' || configDraft.stop_mode === 'both') && (
              <div className="space-y-3 rounded-lg border border-zinc-800 p-3">
                <div className="text-xs font-medium text-zinc-400">Threshold</div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Target Loss</label>
                  <input
                    type="number" step="0.01" min="0" max="5"
                    value={configDraft.target_loss ?? ''}
                    onChange={e => {
                      const raw = e.target.value
                      if (raw === '') {
                        setConfigErrors(err => ({ ...err, target_loss: '' }))
                        setConfigDraft(d => ({ ...d!, target_loss: null }))
                        return
                      }
                      const val = parseFloat(raw.replace(',', '.'))
                      if (isNaN(val)) {
                        setConfigErrors(err => ({ ...err, target_loss: 'Nur Zahlen erlaubt' }))
                      } else if (val < 0) {
                        setConfigErrors(err => ({ ...err, target_loss: 'Muss ≥ 0 sein' }))
                      } else {
                        setConfigErrors(err => ({ ...err, target_loss: '' }))
                        setConfigDraft(d => ({ ...d!, target_loss: val }))
                      }
                    }}
                    placeholder="e.g. 0.4"
                    className={`w-full bg-zinc-800 border ${configErrors.target_loss ? 'border-red-500' : 'border-zinc-700'} text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500`}
                  />
                  {configErrors.target_loss && <p className="text-red-400 text-xs mt-1">{configErrors.target_loss}</p>}
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Metric</label>
                  <select
                    value={configDraft.target_loss_metric}
                    onChange={e => setConfigDraft(d => ({ ...d!, target_loss_metric: e.target.value }))}
                    className="w-full bg-zinc-800 border border-zinc-700 text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500"
                  >
                    <option value="loss">Training Loss</option>
                    <option value="eval_loss">Eval Loss</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Confirmations (consecutive hits)</label>
                  <input
                    type="number" step="1" min="1" max="20"
                    value={configDraft.target_confirmations}
                    onChange={e => {
                      const val = parseInt(e.target.value.replace(',', '.'), 10)
                      if (isNaN(val)) {
                        setConfigErrors(err => ({ ...err, target_confirmations: 'Nur Zahlen erlaubt' }))
                      } else if (val < 1) {
                        setConfigErrors(err => ({ ...err, target_confirmations: 'Min: 1' }))
                      } else {
                        setConfigErrors(err => ({ ...err, target_confirmations: '' }))
                        setConfigDraft(d => ({ ...d!, target_confirmations: val }))
                      }
                    }}
                    className={`w-full bg-zinc-800 border ${configErrors.target_confirmations ? 'border-red-500' : 'border-zinc-700'} text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500`}
                  />
                  {configErrors.target_confirmations && <p className="text-red-400 text-xs mt-1">{configErrors.target_confirmations}</p>}
                </div>
              </div>
            )}

            {/* Patience section */}
            {(configDraft.stop_mode === 'patience' || configDraft.stop_mode === 'both') && (
              <div className="space-y-3 rounded-lg border border-zinc-800 p-3">
                <div className="text-xs font-medium text-zinc-400">Early Stopping</div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Patience (evals without improvement)</label>
                  <input
                    type="number" step="1" min="1" max="100"
                    value={configDraft.patience ?? ''}
                    onChange={e => {
                      const raw = e.target.value
                      if (raw === '') {
                        setConfigErrors(err => ({ ...err, patience: '' }))
                        setConfigDraft(d => ({ ...d!, patience: null }))
                        return
                      }
                      const val = parseInt(raw.replace(',', '.'), 10)
                      if (isNaN(val)) {
                        setConfigErrors(err => ({ ...err, patience: 'Nur Zahlen erlaubt' }))
                      } else if (val < 1) {
                        setConfigErrors(err => ({ ...err, patience: 'Min: 1' }))
                      } else {
                        setConfigErrors(err => ({ ...err, patience: '' }))
                        setConfigDraft(d => ({ ...d!, patience: val }))
                      }
                    }}
                    placeholder="e.g. 5"
                    className={`w-full bg-zinc-800 border ${configErrors.patience ? 'border-red-500' : 'border-zinc-700'} text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500`}
                  />
                  {configErrors.patience && <p className="text-red-400 text-xs mt-1">{configErrors.patience}</p>}
                </div>
                <div>
                  <label className="block text-xs text-zinc-500 mb-1">Min Delta (minimum improvement)</label>
                  <input
                    type="number" step="0.001" min="0" max="1"
                    value={configDraft.min_delta}
                    onChange={e => {
                      const val = parseFloat(e.target.value.replace(',', '.'))
                      if (isNaN(val)) {
                        setConfigErrors(err => ({ ...err, min_delta: 'Nur Zahlen erlaubt' }))
                      } else if (val < 0) {
                        setConfigErrors(err => ({ ...err, min_delta: 'Muss ≥ 0 sein' }))
                      } else {
                        setConfigErrors(err => ({ ...err, min_delta: '' }))
                        setConfigDraft(d => ({ ...d!, min_delta: val }))
                      }
                    }}
                    className={`w-full bg-zinc-800 border ${configErrors.min_delta ? 'border-red-500' : 'border-zinc-700'} text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500`}
                  />
                  {configErrors.min_delta && <p className="text-red-400 text-xs mt-1">{configErrors.min_delta}</p>}
                </div>
              </div>
            )}

            {/* General */}
            <div className="space-y-3 rounded-lg border border-zinc-800 p-3">
              <div className="text-xs font-medium text-zinc-400">General</div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Max Epochs (hard cap)</label>
                <input
                  type="number" step="1" min="1" max="100"
                  value={configDraft.max_epochs}
                  onChange={e => {
                    const val = parseInt(e.target.value.replace(',', '.'), 10)
                    if (isNaN(val)) {
                      setConfigErrors(err => ({ ...err, max_epochs: 'Nur Zahlen erlaubt' }))
                    } else if (val < 1) {
                      setConfigErrors(err => ({ ...err, max_epochs: 'Min: 1' }))
                    } else {
                      setConfigErrors(err => ({ ...err, max_epochs: '' }))
                      setConfigDraft(d => ({ ...d!, max_epochs: val }))
                    }
                  }}
                  className={`w-full bg-zinc-800 border ${configErrors.max_epochs ? 'border-red-500' : 'border-zinc-700'} text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500`}
                />
                {configErrors.max_epochs && <p className="text-red-400 text-xs mt-1">{configErrors.max_epochs}</p>}
              </div>
              <div>
                <label className="block text-xs text-zinc-500 mb-1">Min Steps (don't stop before)</label>
                <input
                  type="number" step="1" min="0" max="1000000"
                  value={configDraft.min_steps}
                  onChange={e => {
                    const val = parseInt(e.target.value.replace(',', '.'), 10)
                    if (isNaN(val)) {
                      setConfigErrors(err => ({ ...err, min_steps: 'Nur Zahlen erlaubt' }))
                    } else if (val < 0) {
                      setConfigErrors(err => ({ ...err, min_steps: 'Muss ≥ 0 sein' }))
                    } else {
                      setConfigErrors(err => ({ ...err, min_steps: '' }))
                      setConfigDraft(d => ({ ...d!, min_steps: val }))
                    }
                  }}
                  className={`w-full bg-zinc-800 border ${configErrors.min_steps ? 'border-red-500' : 'border-zinc-700'} text-zinc-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-violet-500`}
                />
                {configErrors.min_steps && <p className="text-red-400 text-xs mt-1">{configErrors.min_steps}</p>}
              </div>
            </div>

            {/* Training active warning */}
            {status?.status === 'training' && (
              <p className="text-yellow-400 text-xs rounded-lg bg-yellow-900/20 border border-yellow-800/40 px-3 py-2">
                Training is running — changes apply to the next training run.
              </p>
            )}
          </div>

          {/* Footer buttons */}
          <div className="flex gap-2 p-4 border-t border-zinc-800 shrink-0">
            <button
              disabled={configSaving || Object.values(configErrors).some(Boolean)}
              onClick={async () => {
                setConfigSaving(true)
                try {
                  const saved = await updateStopConfig(configDraft!)
                  setStopConfig(saved)
                  setConfigPanelOpen(false)
                } catch (e) {
                  console.error('[Config] save failed:', e)
                } finally {
                  setConfigSaving(false)
                }
              }}
              className="flex-1 px-3 py-2 rounded-lg text-xs bg-violet-700 hover:bg-violet-600 text-white transition-colors disabled:opacity-50"
            >
              {configSaving ? 'Saving\u2026' : 'Save'}
            </button>
            <button
              onClick={() => setConfigDraft({ ...DEFAULT_STOP_CONFIG })}
              className="px-3 py-2 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
            >
              Reset
            </button>
          </div>
        </div>
      )}

      {/* Dev-only memory debug overlay — compiles away in production */}
      {import.meta.env.DEV && (
        <div
          className="fixed bottom-2 right-2 text-xs font-mono px-2 py-1 rounded z-50 pointer-events-none"
          style={{ background: 'rgba(0,0,0,0.85)', color: '#22c55e' }}
        >
          lossHistory:{lossHistory.length} hw:{hwHistory.length} log:{logLines.length} SSE:{esRef.current ? '1' : '0'}
        </div>
      )}
    </div>
  )
}
