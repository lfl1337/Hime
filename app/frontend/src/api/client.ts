// Port discovery for local-first backend
//
// DEV mode  (npm run vite  OR  tauri dev):
//   getBaseUrl() returns window.location.origin so requests go to the
//   Vite dev server, which proxies /api, /health, /ws to the backend.
//
// PROD mode (packaged Tauri app):
//   getPort() reads hime-backend.lock from %APPDATA%\dev.lfl.hime\ via
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
    const content = await tryReadFile(`${dir}hime-backend.lock`)
    if (content) {
      const lock = JSON.parse(content) as { port?: number; pid?: number }
      const port = lock.port
      if (typeof port === 'number' && !isNaN(port)) {
        console.log(`[client] Port ${port} (pid ${lock.pid ?? '?'}) from hime-backend.lock`)
        cachedPort = port
        return port
      }
    }
  } catch (err) {
    console.debug('[client] hime-backend.lock unavailable:', err)
  }

  console.warn('[client] Could not read hime-backend.lock — probing 18420–18430')

  // 2. Probe ports sequentially as final fallback
  for (let port = 18420; port <= 18430; port++) {
    if (await probePort(port)) {
      console.log(`[client] Backend found via probe at port ${port}`)
      cachedPort = port
      return port
    }
  }

  console.error('[client] No backend found on 18420–18430 — defaulting to 18420')
  cachedPort = 18420
  return 18420
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
    return 'http://127.0.0.1:18420'
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

export async function getHealthInfo(): Promise<{ status: string; app: string; version: string }> {
  const res = await apiFetch('/health')
  if (!res.ok) throw new Error('health check failed')
  return res.json() as Promise<{ status: string; app: string; version: string }>
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
