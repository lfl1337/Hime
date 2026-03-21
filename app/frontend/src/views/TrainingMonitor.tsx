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
import type { CheckpointInfo, GGUFModelInfo, LossPoint, RunInfo, TrainingStatus } from '../api/training'
import {
  createTrainingEventSource,
  fetchAllRuns,
  fetchGGUFModels,
  getCheckpoints,
  getLossHistory,
  getTrainingLog,
  getTrainingStatus,
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
  const [logLines, setLogLines] = useState<string[]>([])
  const [lastUpdated, setLastUpdated] = useState<number>(Date.now())
  const [sseConnected, setSseConnected] = useState(false)
  const [secondsAgo, setSecondsAgo] = useState(0)

  const isWindowVisible = useStore(s => s.isWindowVisible)

  const logEndRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)
  const fallbackRef = useRef<number | null>(null)
  const selectedRunRef = useRef<string | null>(null)

  // Mount effect: fetch runs and GGUF models in parallel, then select first run
  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setLoadError('Request timed out after 10 seconds — check that the backend is running and the API key is valid.')
      setRunsLoaded(true)
    }, 10_000)

    Promise.allSettled([fetchAllRuns(), fetchGGUFModels()]).then(([runsResult, ggufResult]) => {
      clearTimeout(timeoutId)
      if (runsResult.status === 'rejected') {
        setLoadError(String(runsResult.reason))
      }
      const loadedRuns = runsResult.status === 'fulfilled' ? runsResult.value : []
      const loadedGguf = ggufResult.status === 'fulfilled' ? ggufResult.value : []
      setRuns(loadedRuns)
      setGgufModels(loadedGguf)
      setSelectedRun(loadedRuns[0]?.run_name ?? null)
      setRunsLoaded(true)
    })

    return () => clearTimeout(timeoutId)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Keep selectedRunRef in sync with selectedRun
  useEffect(() => {
    selectedRunRef.current = selectedRun
  }, [selectedRun])

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
      if (ll.status === 'fulfilled') setLogLines(ll.value)
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
          const { line } = JSON.parse(e.data) as { line: string }
          setLogLines(prev => {
            const next = [...prev, line]
            return next.length > 100 ? next.slice(-100) : next
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
              if (ll.status === 'fulfilled') setLogLines(ll.value)
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
            <p className="text-zinc-600 text-xs">
              Check that the API key is valid and the backend is reachable.
            </p>
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

      {/* Content: fades when switching runs */}
      <div className={`space-y-6 transition-opacity duration-200 ${runLoading ? 'opacity-40' : 'opacity-100'}`}>

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
                    onClick={() =>
                      copy(
                        `python ${status?.scripts_path ?? ''}\\train_hime.py --resume_from_checkpoint ${cp.full_path}`,
                        `resume-${cp.name}`
                      )
                    }
                    className="ml-4 shrink-0 px-3 py-1.5 rounded-lg text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
                  >
                    {copied === `resume-${cp.name}` ? 'Copied!' : 'Copy resume command'}
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

        {/* 5. Live Log Feed */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h3 className="text-sm font-medium text-zinc-400 mb-3">Live Log</h3>
          <div
            className="h-48 overflow-y-auto rounded-lg p-3 font-mono text-xs leading-relaxed"
            style={{ background: '#0d0d0d' }}
          >
            {logLines.length === 0 ? (
              <div className="text-zinc-600">
                <div>No log file yet. Start training with:</div>
                <div className="mt-2 text-zinc-500">
                  {'  '}cd C:\Projekte\Hime\scripts
                </div>
                <div className="text-zinc-500">
                  {'  '}python train_hime.py --log-file ..\app\backend\logs\training\{selectedRun ?? 'run'}.log
                </div>
              </div>
            ) : (
              logLines.map((line, i) => (
                <div key={i} className="text-zinc-400 whitespace-pre-wrap break-all">
                  {line}
                </div>
              ))
            )}
            <div ref={logEndRef} />
          </div>
        </div>

        {/* 6. Quick Actions */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <h3 className="text-sm font-medium text-zinc-400 mb-4">Quick Actions</h3>
          {/* TODO: replace with tauri shell open() when @tauri-apps/plugin-shell is added */}
          <div className="flex flex-wrap gap-3">
            {bestCp && (
              <button
                onClick={() =>
                  copy(
                    `python ${status?.scripts_path ?? ''}\\train_hime.py --resume_from_checkpoint ${bestCp.full_path}`,
                    'quick-resume'
                  )
                }
                className="px-4 py-2 rounded-lg text-sm bg-violet-700 hover:bg-violet-600 text-white transition-colors"
              >
                {copied === 'quick-resume' ? 'Copied!' : 'Copy resume command'}
              </button>
            )}
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
          </div>
        </div>

      </div>
    </div>
  )
}
