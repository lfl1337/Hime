import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface HistoryEntry {
  id: number
  sourceText: string
  finalOutput: string
  createdAt: string
}

interface AppStore {
  // Backend connectivity
  backendOnline: boolean
  backendPort: number | null
  apiKeySet: boolean
  setBackendState: (online: boolean, port: number | null) => void
  setApiKeySet: (v: boolean) => void

  // Persistent input
  lastInput: string
  setLastInput: (text: string) => void

  // Local translation history (last 10)
  history: HistoryEntry[]
  addHistory: (entry: HistoryEntry) => void
  clearHistory: () => void
}

export const useStore = create<AppStore>()(
  persist(
    (set) => ({
      backendOnline: false,
      backendPort: null,
      apiKeySet: false,
      setBackendState: (online, port) =>
        set({ backendOnline: online, backendPort: port }),
      setApiKeySet: (v) => set({ apiKeySet: v }),

      lastInput: '',
      setLastInput: (text) => set({ lastInput: text }),

      history: [],
      addHistory: (entry) =>
        set((state) => ({
          history: [entry, ...state.history].slice(0, 10),
        })),
      clearHistory: () => set({ history: [] }),
    }),
    {
      name: 'hime-storage',
      partialize: (state) => ({
        lastInput: state.lastInput,
        history: state.history,
      }),
    },
  ),
)
