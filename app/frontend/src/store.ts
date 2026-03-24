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
  setBackendState: (online: boolean, port: number | null) => void

  // Window visibility (for pausing SSE/polling when hidden)
  isWindowVisible: boolean
  setWindowVisible: (v: boolean) => void

  // Persistent input
  lastInput: string
  setLastInput: (text: string) => void

  // Local translation history (last 10)
  history: HistoryEntry[]
  addHistory: (entry: HistoryEntry) => void
  clearHistory: () => void

  // EPUB library state
  selectedBookId: number | null
  selectedChapterId: number | null
  selectedParagraphIndex: number
  setSelectedBook: (id: number | null) => void
  setSelectedChapter: (id: number | null) => void
  setSelectedParagraph: (index: number) => void
  libraryTab: 'library' | 'chapters'
  setLibraryTab: (tab: 'library' | 'chapters') => void
}

export const useStore = create<AppStore>()(
  persist(
    (set) => ({
      backendOnline: false,
      backendPort: null,
      setBackendState: (online, port) =>
        set({ backendOnline: online, backendPort: port }),

      isWindowVisible: true,
      setWindowVisible: (v) => set({ isWindowVisible: v }),

      lastInput: '',
      setLastInput: (text) => set({ lastInput: text }),

      history: [],
      addHistory: (entry) =>
        set((state) => ({
          history: [entry, ...state.history].slice(0, 10),
        })),
      clearHistory: () => set({ history: [] }),

      selectedBookId: null,
      selectedChapterId: null,
      selectedParagraphIndex: 0,
      setSelectedBook: (id) => set({ selectedBookId: id }),
      setSelectedChapter: (id) => set({ selectedChapterId: id }),
      setSelectedParagraph: (index) => set({ selectedParagraphIndex: index }),
      libraryTab: 'library',
      setLibraryTab: (tab) => set({ libraryTab: tab }),
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
