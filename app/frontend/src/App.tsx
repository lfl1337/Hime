import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Sidebar } from '@/components/Sidebar'
import { ApiKeyPrompt } from '@/components/ApiKeyPrompt'
import { Translator } from '@/views/Translator'
import { Comparison } from '@/views/Comparison'
import { Editor } from '@/views/Editor'
import { TrainingMonitor } from '@/views/TrainingMonitor'
import { checkBackendOnline, getApiKey } from '@/api/client'
import { useStore } from '@/store'

function AppShell() {
  const setBackendState = useStore((s) => s.setBackendState)
  const setApiKeySet = useStore((s) => s.setApiKeySet)
  const apiKeySet = useStore((s) => s.apiKeySet)

  useEffect(() => {
    void (async () => {
      const [online, key] = await Promise.all([
        checkBackendOnline(),
        getApiKey(),
      ])
      setBackendState(online, null)
      setApiKeySet(!!key)
    })()

    const interval = setInterval(() => {
      void checkBackendOnline().then((online) => setBackendState(online, null))
    }, 30_000)
    return () => clearInterval(interval)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex h-screen bg-zinc-950 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-auto relative">
        <ApiKeyPrompt visible={!apiKeySet} />
        <Routes>
          <Route path="/" element={<Translator />} />
          <Route path="/comparison" element={<Comparison />} />
          <Route path="/editor" element={<Editor />} />
          <Route path="/monitor" element={<TrainingMonitor />} />
        </Routes>
      </main>
    </div>
  )
}

function StartupSplash({ error }: { error: string | null }) {
  return (
    <div className="flex h-screen items-center justify-center bg-zinc-950 text-zinc-300">
      {error ? (
        <p className="text-red-400">{error}</p>
      ) : (
        <>
          <span className="mr-3 inline-block h-5 w-5 animate-spin rounded-full border-2 border-zinc-600 border-t-zinc-300" />
          Starting Hime…
        </>
      )}
    </div>
  )
}

export default function App() {
  // In dev mode the backend is already running — skip the splash entirely.
  const [backendReady, setBackendReady] = useState(import.meta.env.DEV)
  const [startupError, setStartupError] = useState<string | null>(null)

  useEffect(() => {
    if (import.meta.env.DEV) return

    let attempts = 0
    const id = window.setInterval(async () => {
      attempts++
      if (await checkBackendOnline()) {
        clearInterval(id)
        setBackendReady(true)
      } else if (attempts >= 20) {
        // 20 × 500 ms = 10 s timeout
        clearInterval(id)
        setStartupError('Backend failed to start. Please restart the app.')
      }
    }, 500)
    return () => clearInterval(id)
  }, [])

  if (!backendReady) {
    return <StartupSplash error={startupError} />
  }

  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  )
}
