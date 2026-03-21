import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

// ESM-safe equivalent of __dirname (not available in "type": "module" projects)
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Read the backend port from .runtime_port at Vite startup.
// Node.js can read the file directly — no Tauri plugin or CORS involved.
function readBackendPort(): number {
  const filePath = path.resolve(__dirname, '../backend/.runtime_port')
  try {
    const content = readFileSync(filePath, 'utf8')
    const port = parseInt(content.trim(), 10)
    if (!isNaN(port)) {
      console.log(`[vite] Backend port: ${port} (from ${filePath})`)
      return port
    }
    console.error(`[vite] .runtime_port is not a number: "${content.trim()}"`)
  } catch {
    // .runtime_port absent during production build — fallback is correct
  }
  return 8004
}

// Read the API key written by run.py so it can be injected as a build
// constant (__DEV_API_KEY__) for browser dev mode where Tauri fs is absent.
function readDevApiKey(): string {
  const filePath = path.resolve(__dirname, '../backend/.api_key')
  try {
    const key = readFileSync(filePath, 'utf8').trim()
    if (key) {
      console.log(`[vite] Dev API key loaded (length=${key.length})`)
      return key
    }
  } catch {
    console.warn('[vite] backend/.api_key not found — start the backend first, then restart Vite')
  }
  return ''
}

const BACKEND_PORT = readBackendPort()
const BACKEND_ORIGIN = `http://127.0.0.1:${BACKEND_PORT}`
const DEV_API_KEY = readDevApiKey()

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // Injected at build time; client.ts reads this in DEV mode to avoid
    // needing the Tauri fs API (unavailable in a plain browser).
    __DEV_API_KEY__: JSON.stringify(DEV_API_KEY),
  },
  server: {
    port: 1420,
    host: '127.0.0.1',
    strictPort: false,
    proxy: {
      // Forwarded server-side — no CORS, no port discovery needed in the browser.
      '/api':    { target: BACKEND_ORIGIN, changeOrigin: true },
      '/health': { target: BACKEND_ORIGIN, changeOrigin: true },
      '/ws':     { target: BACKEND_ORIGIN.replace('http', 'ws'), ws: true, changeOrigin: true },
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
  },
})
