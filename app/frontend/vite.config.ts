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

const BACKEND_PORT = readBackendPort()
const BACKEND_ORIGIN = `http://127.0.0.1:${BACKEND_PORT}`

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
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
