import { useEffect, useRef } from 'react'
import { useStore } from '../../store'
import { startCompare, fetchModelEndpoints } from '../../api/compare'
import { createWebSocket } from '../../api/client'
import { ModelPanel } from './ModelPanel'
import { ConsensusPanel } from './ConsensusPanel'
import { MODEL_CONFIG, MODEL_KEYS } from './modelConfig'
import type { ModelKey } from './modelConfig'

export function ModelComparisonTab() {
  const {
    comparison,
    setComparisonInput,
    setIsComparing,
    setCurrentJobId,
    appendModelToken,
    setModelComplete,
    setModelError,
    setConsensus,
    resetComparison,
    setModelEndpoints,
  } = useStore()

  const wsRef = useRef<WebSocket | null>(null)
  const timeoutsRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})
  const consensusBufferRef = useRef<string>('')

  // Fetch model endpoints on mount
  useEffect(() => {
    fetchModelEndpoints()
      .then(setModelEndpoints)
      .catch(console.error)
  }, [setModelEndpoints])

  // Cleanup WebSocket on unmount
  useEffect(() => {
    const timeouts = timeoutsRef.current
    return () => {
      wsRef.current?.close()
      Object.values(timeouts).forEach(clearTimeout)
    }
  }, [])

  async function startComparison() {
    if (!comparison.inputText.trim()) return

    // Reset previous state
    resetComparison()
    consensusBufferRef.current = ''
    setIsComparing(true)

    try {
      // Create job via HTTP
      const { job_id } = await startCompare(comparison.inputText)
      setCurrentJobId(job_id)

      // Open WebSocket
      const ws = await createWebSocket(job_id)
      wsRef.current = ws

      ws.onmessage = (e: MessageEvent) => {
        const event = JSON.parse(e.data as string) as {
          event: string
          model?: ModelKey
          token?: string
          output?: string
          detail?: string
        }

        if (event.event === 'stage1_token' && event.model) {
          appendModelToken(event.model, event.token ?? '')
          // Reset per-model timeout
          clearTimeout(timeoutsRef.current[event.model])
          timeoutsRef.current[event.model] = setTimeout(() => {
            setModelError(event.model!, 'Timed out')
          }, 120_000)
        } else if (event.event === 'stage1_complete' && event.model) {
          clearTimeout(timeoutsRef.current[event.model])
          setModelComplete(event.model, event.output ?? '')
        } else if (event.event === 'model_error' && event.model) {
          clearTimeout(timeoutsRef.current[event.model])
          setModelError(event.model, event.detail ?? 'Error')
        } else if (event.event === 'consensus_token') {
          consensusBufferRef.current += event.token ?? ''
          setConsensus(consensusBufferRef.current, false)
        } else if (event.event === 'consensus_complete') {
          setConsensus(event.output ?? consensusBufferRef.current, true)
          ws.close()
          setIsComparing(false)
        } else if (event.event === 'pipeline_error') {
          ws.close()
          setIsComparing(false)
        } else if (event.event === 'pipeline_complete') {
          ws.close()
          setIsComparing(false)
        }
      }

      ws.onerror = () => {
        setIsComparing(false)
      }

      ws.onclose = () => {
        setIsComparing(false)
      }
    } catch (err) {
      console.error('startComparison error:', err)
      setIsComparing(false)
    }
  }

  const onlineCount = comparison.modelEndpoints.filter(e => e.online).length
  const allOffline = comparison.modelEndpoints.length > 0 && onlineCount === 0
  const noInput = !comparison.inputText.trim()
  const btnDisabled = noInput || allOffline || comparison.isComparing

  return (
    <div className="space-y-6">
      {/* Input area */}
      <div className="space-y-3">
        <textarea
          value={comparison.inputText}
          onChange={(e) => setComparisonInput(e.target.value)}
          placeholder="日本語テキストを入力してください…"
          className="w-full h-32 bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-zinc-200 text-sm resize-none focus:outline-none focus:border-purple-500 placeholder:text-zinc-600"
          disabled={comparison.isComparing}
        />
        <div className="flex items-center justify-between">
          <span className="text-xs text-zinc-600">
            {comparison.modelEndpoints.length > 0
              ? `${onlineCount}/3 models online`
              : 'Checking model status…'}
          </span>
          <button
            onClick={() => void startComparison()}
            disabled={btnDisabled}
            title={allOffline ? 'Start inference servers to enable comparison' : undefined}
            className="px-5 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-zinc-700 disabled:text-zinc-500 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
          >
            {comparison.isComparing && (
              <span className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {comparison.isComparing ? 'Translating…' : '比較する'}
          </button>
        </div>
      </div>

      {/* Model panels — 1 col mobile, 3 col xl+ */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {MODEL_KEYS.map((key) => {
          const ep = comparison.modelEndpoints.find(e => e.key === key)
          return (
            <ModelPanel
              key={key}
              modelKey={key}
              displayName={MODEL_CONFIG[key].displayName}
              accentColor={MODEL_CONFIG[key].accentColor}
              online={ep?.online ?? false}
              isTraining={false}
              output={comparison.modelOutputs[key]}
            />
          )
        })}
      </div>

      {/* Consensus panel */}
      <ConsensusPanel
        text={comparison.consensusText}
        done={comparison.consensusDone}
        onlineModelCount={onlineCount}
      />
    </div>
  )
}
