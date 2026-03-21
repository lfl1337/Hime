import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@/styles/globals.css'
import App from './App.tsx'

// Theme initialization from localStorage (default: dark)
const stored = localStorage.getItem('hime_theme') ?? 'dark'
function applyTheme(pref: string) {
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  const useDark = pref === 'dark' || (pref === 'system' && prefersDark)
  document.documentElement.classList.toggle('dark', useDark)
  document.documentElement.classList.toggle('light', !useDark)
}
applyTheme(stored)
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if ((localStorage.getItem('hime_theme') ?? 'dark') === 'system') {
    applyTheme('system')
  }
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
