import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// ESM-safe equivalent of __dirname (not available in "type": "module" projects)
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Read the backend port from hime-backend.lock at Vite startup.
// Node.js can read the file directly — no Tauri plugin or CORS involved.
// The lock file is JSON: {"port": N, "pid": N} (written by run.py on startup).
function readBackendPort(): number {
  const filePath = path.resolve(__dirname, '../backend/hime-backend.lock')
  try {
    const content = readFileSync(filePath, 'utf8')
    const lock = JSON.parse(content) as { port?: number; pid?: number }
    if (typeof lock.port === 'number' && !isNaN(lock.port)) {
      console.log(`[vite] Backend port: ${lock.port} (pid ${lock.pid ?? '?'}) from ${filePath}`)
      return lock.port
    }
    console.error(`[vite] hime-backend.lock has no valid port field: ${content.trim()}`)
  } catch {
    console.warn(`[vite] hime-backend.lock not found at ${filePath} — defaulting to 18420`)
  }
  return 18420
}

// Keep BACKEND_PORT as the initial fallback only
const BACKEND_PORT = readBackendPort()
const BACKEND_ORIGIN = `http://127.0.0.1:${BACKEND_PORT}`

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 1420,
    host: '127.0.0.1',
    strictPort: true,
    proxy: {
      // router() is called per-request — re-reads .runtime_port each time so
      // the proxy stays correct even if the backend starts after Vite or restarts.
      '/api': {
        target: BACKEND_ORIGIN,
        changeOrigin: true,
        router: () => `http://127.0.0.1:${readBackendPort()}`,
      },
      '/health': {
        target: BACKEND_ORIGIN,
        changeOrigin: true,
        router: () => `http://127.0.0.1:${readBackendPort()}`,
      },
      '/ws': {
        target: BACKEND_ORIGIN.replace('http', 'ws'),
        ws: true,
        changeOrigin: true,
        router: () => `ws://127.0.0.1:${readBackendPort()}`,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Suppress Tauri-related warnings in browser dev mode
  build: {
    target: 'esnext',
    sourcemap: false,
  },
})
