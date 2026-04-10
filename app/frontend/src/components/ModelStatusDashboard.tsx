import { useEffect, useState } from 'react'
import { apiFetch } from '@/api/client'

interface ModelStatus {
  key: string
  name: string
  endpoint: string
  online: boolean
  loaded_model: string | null
  latency_ms: number | null
  stage: string
  installed: boolean
}

interface Props {
  compact?: boolean
}

const STAGE_LABELS: Record<string, string> = {
  stage1: 'Stage 1',
  consensus: 'Consensus',
  stage2: 'Stage 2',
  stage3: 'Stage 3',
}

export function ModelStatusDashboard({ compact = false }: Props) {
  const [models, setModels] = useState<ModelStatus[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      try {
        const resp = await apiFetch('/api/v1/models', {})
        if (!resp.ok) return
        const data = await resp.json() as ModelStatus[]
        if (!cancelled) setModels(data)
      } catch {
        // Backend offline
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    poll()
    const interval = setInterval(poll, 10_000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  if (loading) {
    return <div className="text-xs text-zinc-500 animate-pulse">Checking models…</div>
  }

  if (models.length === 0) {
    return <div className="text-xs text-zinc-500">No model information available</div>
  }

  if (compact) {
    const onlineCount = models.filter(m => m.online).length
    return (
      <div className="flex items-center gap-2 text-xs text-zinc-400">
        <div className="flex gap-1">
          {models.map(m => (
            <span
              key={m.key}
              title={`${m.name} — ${m.online ? 'online' : m.installed === false ? 'not installed' : 'offline'}`}
              className={`w-2 h-2 rounded-full ${
                m.installed === false ? 'bg-zinc-600'
                : m.online ? 'bg-green-500'
                : 'bg-red-500'
              }`}
            />
          ))}
        </div>
        <span>{onlineCount}/{models.length} online</span>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Pipeline Models</h3>
      <div className="grid grid-cols-2 xl:grid-cols-3 gap-2">
        {models.map(m => (
          <div
            key={m.key}
            className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 space-y-1"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-zinc-200">{m.name}</span>
              <span className={`w-2 h-2 rounded-full ${
                m.installed === false ? 'bg-zinc-600'
                : m.online ? 'bg-green-500'
                : 'bg-red-500'
              }`} title={
                m.installed === false ? 'Not installed'
                : m.online ? 'Online'
                : 'Offline'
              } />
            </div>
            {m.installed === false && (
              <DownloadModelButton modelKey={m.key} />
            )}
            {m.installed !== false && !m.online && (
              <p className="text-[10px] text-zinc-500 italic">
                Endpoint nicht erreichbar — Inferenz-Server starten
              </p>
            )}
            {m.installed !== false && (
              <>
                <div className="text-[10px] text-zinc-500 truncate" title={m.endpoint}>
                  {m.endpoint}
                </div>
                <div className="flex items-center gap-2 text-[10px]">
                  <span className="text-zinc-600">{STAGE_LABELS[m.stage] ?? m.stage}</span>
                  {m.online && m.latency_ms != null && (
                    <span className={`${m.latency_ms < 500 ? 'text-green-500' : m.latency_ms < 2000 ? 'text-yellow-500' : 'text-red-500'}`}>
                      {m.latency_ms}ms
                    </span>
                  )}
                  {m.loaded_model && (
                    <span className="text-zinc-500 truncate" title={m.loaded_model}>
                      {m.loaded_model}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function DownloadModelButton({ modelKey }: { modelKey: string }) {
  const [status, setStatus] = useState<'idle' | 'queued' | 'error'>('idle')

  async function handleClick() {
    try {
      const resp = await apiFetch(`/api/v1/models/${modelKey}/download`, { method: 'POST' })
      if (resp.status === 507) {
        setStatus('error')
        return
      }
      const data = await resp.json() as { status: string }
      setStatus(data.status === 'queued' ? 'queued' : 'error')
    } catch {
      setStatus('error')
    }
  }

  if (status === 'queued') {
    return (
      <p className="text-[10px] text-amber-400 italic">
        In Warteschlange — Download startet sobald Speicherplatz verfügbar
      </p>
    )
  }
  if (status === 'error') {
    return (
      <p className="text-[10px] text-red-400 italic">
        Fehler beim Anfordern des Downloads
      </p>
    )
  }

  return (
    <button
      onClick={() => void handleClick()}
      title="Downloads disabled — set HIME_ALLOW_DOWNLOADS=true after disk migration"
      className="text-[10px] px-2 py-0.5 rounded bg-violet-900/40 hover:bg-violet-900/60 text-violet-300 transition-colors"
    >
      Download now
    </button>
  )
}
