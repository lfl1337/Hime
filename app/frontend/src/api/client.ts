// Port discovery for local-first backend
//
// DEV mode  (npm run vite  OR  tauri dev):
//   getBaseUrl() returns window.location.origin so requests go to the
//   Vite dev server, which proxies /api, /health, /ws to the backend.
//
// PROD mode (packaged Tauri app):
//   getPort() reads .runtime_port from %APPDATA%\dev.hime.app\ via
//   appDataDir() + readTextFile(), matching where run.py writes it.

let cachedPort: number | null = null

async function tryReadFile(filePath: string): Promise<string | null> {
  try {
    const { readTextFile } = await import('@tauri-apps/plugin-fs')
    const content = await readTextFile(filePath)
    console.debug(`[client] tryReadFile OK: ${filePath}`)
    return content
  } catch (err) {
    console.debug(`[client] tryReadFile failed: ${filePath}`, err)
    return null
  }
}

async function probePort(port: number): Promise<boolean> {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/health`, {
      signal: AbortSignal.timeout(500),
    })
    return res.ok
  } catch {
    return false
  }
}

// Only used in production Tauri mode where there is no Vite proxy.
async function getPort(): Promise<number> {
  if (cachedPort !== null) return cachedPort

  // 1. Read from AppData dir (matches where run.py --data-dir writes it)
  try {
    const { appDataDir } = await import('@tauri-apps/api/path')
    const dir = await appDataDir()
    const content = await tryReadFile(`${dir}.runtime_port`)
    if (content) {
      const port = parseInt(content.trim(), 10)
      if (!isNaN(port)) {
        console.log(`[client] Port ${port} from appDataDir`)
        cachedPort = port
        return port
      }
    }
  } catch (err) {
    console.debug('[client] appDataDir() unavailable:', err)
  }

  console.warn('[client] Could not read .runtime_port — probing 8000–8010')

  // 2. Probe ports sequentially as final fallback
  for (let port = 8000; port <= 8010; port++) {
    if (await probePort(port)) {
      console.log(`[client] Backend found via probe at port ${port}`)
      cachedPort = port
      return port
    }
  }

  console.error('[client] No backend found on 8000–8010 — defaulting to 8004')
  cachedPort = 8004
  return 8004
}

export async function getBaseUrl(): Promise<string> {
  if (import.meta.env.DEV) {
    console.debug(`[client] baseUrl = ${window.location.origin} (dev/proxy mode)`)
    return window.location.origin
  }

  // Production Tauri: discover the real backend port directly
  try {
    const port = await getPort()
    const url = `http://127.0.0.1:${port}`
    console.debug(`[client] baseUrl = ${url} (prod/direct mode)`)
    return url
  } catch (err) {
    console.error('[client] getBaseUrl() threw:', err)
    return 'http://127.0.0.1:8004'
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const baseUrl = await getBaseUrl()
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body) {
    headers.set('Content-Type', 'application/json')
  }
  return fetch(`${baseUrl}${path}`, { ...init, headers })
}

export async function createWebSocket(jobId: number): Promise<WebSocket> {
  if (import.meta.env.DEV) {
    const wsOrigin = window.location.origin.replace(/^http/, 'ws')
    return new WebSocket(`${wsOrigin}/ws/translate/${jobId}`)
  }
  const port = await getPort()
  return new WebSocket(`ws://127.0.0.1:${port}/ws/translate/${jobId}`)
}

export async function checkBackendOnline(): Promise<boolean> {
  try {
    const baseUrl = await getBaseUrl()
    const res = await fetch(`${baseUrl}/health`, {
      signal: AbortSignal.timeout(2000),
    })
    return res.ok
  } catch {
    return false
  }
}
