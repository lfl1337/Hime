import { useState } from 'react'
import { setApiKey } from '@/api/client'
import { useStore } from '@/store'

interface ApiKeyPromptProps {
  visible: boolean
}

export function ApiKeyPrompt({ visible }: ApiKeyPromptProps) {
  const [value, setValue] = useState('')
  const setApiKeySet = useStore((s) => s.setApiKeySet)

  if (!visible) return null

  function handleSave() {
    const trimmed = value.trim()
    if (!trimmed) return
    setApiKey(trimmed)
    setApiKeySet(true)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="w-full max-w-md rounded-xl bg-zinc-900 border border-zinc-700 p-6 shadow-2xl">
        <h2 className="text-lg font-semibold text-zinc-100 mb-1">
          API Key Required
        </h2>
        <p className="text-sm text-zinc-400 mb-4">
          Enter the <code className="bg-zinc-800 px-1 rounded text-zinc-300">API_KEY</code>{' '}
          from <code className="bg-zinc-800 px-1 rounded text-zinc-300">backend/.env</code>.
        </p>
        <input
          type="password"
          className="w-full rounded-lg bg-zinc-800 border border-zinc-600 px-3 py-2 text-zinc-100 text-sm focus:outline-none focus:ring-2 focus:ring-[#7C6FCD] mb-3"
          placeholder="Paste API key…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSave()}
          autoFocus
        />
        <button
          className="w-full rounded-lg bg-[#7C6FCD] hover:bg-[#6a5ebc] px-4 py-2 text-sm font-medium text-white transition-colors disabled:opacity-50"
          onClick={handleSave}
          disabled={!value.trim()}
        >
          Save Key
        </button>
      </div>
    </div>
  )
}
