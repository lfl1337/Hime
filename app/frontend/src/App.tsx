import { Component, lazy, Suspense, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Sidebar } from '@/components/Sidebar'

const Translator = lazy(() => import('@/views/Translator').then((m) => ({ default: m.Translator })))
const Comparison = lazy(() => import('@/views/Comparison').then((m) => ({ default: m.Comparison })))
const Editor = lazy(() => import('@/views/Editor').then((m) => ({ default: m.Editor })))
const TrainingMonitor = lazy(() => import('@/views/TrainingMonitor').then((m) => ({ default: m.TrainingMonitor })))
const Settings = lazy(() => import('@/views/Settings').then((m) => ({ default: m.Settings })))
import { checkBackendOnline } from '@/api/client'
import { importEpub } from '@/api/epub'
import { useStore } from '@/store'

// ---------------------------------------------------------------------------
// ErrorBoundary — catches render errors and shows them instead of black screen
// ---------------------------------------------------------------------------
interface ErrorBoundaryState { error: Error | null }
class ErrorBoundary extends Component<{ children: ReactNode; label: string }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode; label: string }) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-6 space-y-4">
          <p className="text-red-400 font-semibold text-sm">{this.props.label} crashed</p>
          <pre className="text-xs font-mono text-zinc-400 bg-zinc-900 rounded-lg p-4 overflow-auto max-h-96 whitespace-pre-wrap break-all">
            {this.state.error.message}
            {'\n\n'}
            {this.state.error.stack}
          </pre>
          <button
            onClick={() => this.setState({ error: null })}
            className="px-4 py-2 rounded-lg text-sm bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export function useTheme() {
  const applyTheme = (pref: 'dark' | 'light' | 'system') => {
    localStorage.setItem('hime_theme', pref)
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const useDark = pref === 'dark' || (pref === 'system' && prefersDark)
    document.documentElement.classList.toggle('dark', useDark)
    document.documentElement.classList.toggle('light', !useDark)
  }
  const current = (localStorage.getItem('hime_theme') ?? 'dark') as 'dark' | 'light' | 'system'
  return { current, applyTheme }
}

function AppShell() {
  const setBackendState = useStore((s) => s.setBackendState)
  const setWindowVisible = useStore((s) => s.setWindowVisible)

  useEffect(() => {
    void checkBackendOnline().then((online) => setBackendState(online, null))

    const interval = setInterval(() => {
      if (document.hidden) return
      void checkBackendOnline().then((online) => setBackendState(online, null))
    }, 30_000)
    return () => clearInterval(interval)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Pause polling/SSE when window is hidden
  useEffect(() => {
    const handler = () => {
      console.log('[App] visibilitychange:', document.visibilityState)
      setWindowVisible(!document.hidden)
    }
    document.addEventListener('visibilitychange', handler)
    return () => document.removeEventListener('visibilitychange', handler)
  }, [setWindowVisible])

  // Drag & drop EPUB import
  useEffect(() => {
    const handleDragOver = (e: DragEvent) => { e.preventDefault() }
    const handleDrop = (e: DragEvent) => {
      e.preventDefault()
      const file = e.dataTransfer?.files[0]
      if (file?.name.endsWith('.epub')) {
        // @ts-expect-error - Electron/Tauri file objects may have .path
        void importEpub((file as { path?: string }).path ?? file.name)
      }
    }
    window.addEventListener('dragover', handleDragOver)
    window.addEventListener('drop', handleDrop)
    return () => {
      window.removeEventListener('dragover', handleDragOver)
      window.removeEventListener('drop', handleDrop)
    }
  }, [])

  return (
    <div className="flex h-screen bg-zinc-950 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-auto relative">
        <Suspense fallback={<div className="flex h-screen items-center justify-center text-sm text-gray-400">Laden…</div>}>
          <Routes>
            <Route path="/" element={<Translator />} />
            <Route path="/comparison" element={<Comparison />} />
            <Route path="/editor" element={<Editor />} />
            <Route path="/monitor" element={<ErrorBoundary label="Training Monitor"><TrainingMonitor /></ErrorBoundary>} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </Suspense>
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

    // Production: trust the Tauri "backend-ready" event emitted by lib.rs
    // once .runtime_port appears — avoids a CORS fetch from the webview.
    let unlistenFn: (() => void) | null = null
    const timeoutId = window.setTimeout(() => {
      setStartupError('Backend failed to start. Please restart the app.')
    }, 15_000)

    void import('@tauri-apps/api/event').then(({ listen }) => {
      void listen<void>('backend-ready', () => {
        clearTimeout(timeoutId)
        setBackendReady(true)
      }).then((unlisten) => {
        unlistenFn = unlisten
      })
    })

    return () => {
      clearTimeout(timeoutId)
      unlistenFn?.()
    }
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
