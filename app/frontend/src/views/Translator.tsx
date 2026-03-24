import { useEffect, useRef, useState } from 'react'
import { BackendBanner } from '@/components/BackendBanner'
import { PipelineProgress } from '@/components/PipelineProgress'
import { LiveOutput } from '@/components/LiveOutput'
import { checkBackendOnline } from '@/api/client'
import { createSourceText, startTranslation } from '@/api/translate'
import { usePipeline } from '@/api/websocket'
import { useStore } from '@/store'

const MODEL_LABELS = ['gemma', 'deepseek', 'qwen32b']

export function Translator() {
  const [input, setInput] = useState('')
  const [activeJobId, setActiveJobId] = useState<number | null>(null)
  const [isStarting, setIsStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [showFullPipeline, setShowFullPipeline] = useState(false)

  const backendOnline = useStore((s) => s.backendOnline)
  const setBackendState = useStore((s) => s.setBackendState)
  const lastInput = useStore((s) => s.lastInput)
  const setLastInput = useStore((s) => s.setLastInput)
  const addHistory = useStore((s) => s.addHistory)
  const backendPort = useStore((s) => s.backendPort)

  const pipeline = usePipeline(activeJobId)

  const isRunning =
    pipeline.stage !== 'idle' &&
    pipeline.stage !== 'complete' &&
    pipeline.stage !== 'error'

  // Restore last input on mount
  useEffect(() => {
    if (lastInput) setInput(lastInput)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Check backend online
  useEffect(() => {
    checkBackendOnline().then((online) => {
      setBackendState(online, backendPort)
    })
    const interval = setInterval(() => {
      checkBackendOnline().then((online) => {
        setBackendState(online, backendPort)
      })
    }, 30_000)
    return () => clearInterval(interval)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Save history on completion
  const savedRef = useRef(false)
  useEffect(() => {
    if (pipeline.isComplete && pipeline.finalOutput && !savedRef.current) {
      savedRef.current = true
      addHistory({
        id: activeJobId ?? Date.now(),
        sourceText: input,
        finalOutput: pipeline.finalOutput,
        createdAt: new Date().toISOString(),
      })
    }
  }, [pipeline.isComplete]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleTranslate() {
    if (!input.trim()) return
    setStartError(null)
    setIsStarting(true)
    savedRef.current = false
    setActiveJobId(null)
    setLastInput(input)
    try {
      const title = input.slice(0, 80) || 'Untitled'
      const { id: sourceId } = await createSourceText(title, input)
      const { job_id } = await startTranslation(sourceId)
      setActiveJobId(job_id)
    } catch (err) {
      setStartError(err instanceof Error ? err.message : String(err))
    } finally {
      setIsStarting(false)
    }
  }

  function handleCopy() {
    void navigator.clipboard.writeText(pipeline.finalOutput)
  }

  const stage1Active = pipeline.stage === 'stage1'
  const showStage1 = stage1Active || Object.keys(pipeline.stage1Complete).length > 0

  return (
    <div className="flex flex-col h-full">
      <BackendBanner visible={!backendOnline} />

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Input */}
        <div>
          <textarea
            className="w-full h-40 rounded-xl bg-zinc-900 border border-zinc-700 px-4 py-3 text-zinc-100 text-sm jp-text placeholder-zinc-600 focus:outline-none focus:ring-2 focus:ring-[#7C6FCD] resize-none"
            placeholder="日本語テキストを入力してください…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isRunning || isStarting}
          />
          {startError && (
            <p className="mt-1 text-xs text-red-400">{startError}</p>
          )}
        </div>

        {/* Translate button */}
        <button
          className="rounded-xl bg-[#7C6FCD] hover:bg-[#6a5ebc] px-6 py-2.5 text-sm font-semibold text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          onClick={() => void handleTranslate()}
          disabled={!input.trim() || isRunning || isStarting || !backendOnline}
        >
          {isStarting ? 'Starting…' : isRunning ? 'Translating…' : 'Translate'}
        </button>

        {/* Pipeline progress */}
        {pipeline.stage !== 'idle' && (
          <PipelineProgress currentStage={pipeline.stage} />
        )}

        {/* Stage 1 panels */}
        {showStage1 && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">
                Stage 1 — Parallel Translators
              </span>
              {!stage1Active && (
                <button
                  className="text-xs text-zinc-600 hover:text-zinc-400"
                  onClick={() => setShowFullPipeline((v) => !v)}
                >
                  {showFullPipeline ? 'Hide' : 'Show'}
                </button>
              )}
            </div>
            {(stage1Active || showFullPipeline) && (
              <div className="grid grid-cols-3 gap-3">
                {MODEL_LABELS.map((model) => (
                  <LiveOutput
                    key={model}
                    label={model}
                    text={
                      pipeline.stage1Complete[model] ??
                      pipeline.stage1Tokens[model] ??
                      ''
                    }
                    isActive={stage1Active && !pipeline.stage1Complete[model]}
                    isError={!!pipeline.modelErrors[model]}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Main output panel */}
        {(pipeline.finalOutput || pipeline.stage === 'stage3') && (
          <div className="rounded-xl border border-zinc-700 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-700 bg-zinc-900">
              <span className="text-sm font-medium text-zinc-300">Translation</span>
              {pipeline.finalOutput && (
                <button
                  className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                  onClick={handleCopy}
                >
                  Copy
                </button>
              )}
            </div>
            <div className="min-h-32 max-h-96 overflow-y-auto p-4">
              <p className="text-zinc-100 text-sm jp-text leading-relaxed whitespace-pre-wrap">
                {pipeline.finalOutput || (
                  <span className="text-zinc-600 italic animate-pulse">Translating…</span>
                )}
              </p>
              {pipeline.durationMs && (
                <p className="mt-3 text-xs text-zinc-600">
                  Completed in {(pipeline.durationMs / 1000).toFixed(1)}s
                </p>
              )}
            </div>
          </div>
        )}

        {/* Pipeline error */}
        {pipeline.error && (
          <div className="rounded-xl border border-red-800 bg-red-950/30 px-4 py-3">
            <p className="text-sm text-red-400">
              <span className="font-semibold">Error:</span> {pipeline.error}
            </p>
          </div>
        )}

        {/* View full pipeline toggle (when complete) */}
        {pipeline.isComplete && (
          <button
            className="text-xs text-zinc-600 hover:text-zinc-400 underline"
            onClick={() => setShowFullPipeline((v) => !v)}
          >
            {showFullPipeline ? 'Hide full pipeline' : 'View full pipeline'}
          </button>
        )}

        {/* Full pipeline outputs */}
        {showFullPipeline && pipeline.isComplete && (
          <div className="space-y-3">
            {pipeline.consensusOutput && (
              <LiveOutput
                label="Consensus"
                text={pipeline.consensusOutput}
                isActive={false}
              />
            )}
            {pipeline.stage2Output && (
              <LiveOutput
                label="Stage 2 (72B Refinement)"
                text={pipeline.stage2Output}
                isActive={false}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
