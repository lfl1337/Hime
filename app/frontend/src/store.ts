import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ComparisonState, ModelEndpoint, ModelLiveStatus, ModelOutput } from './types/comparison'

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

  // Comparison tab state
  comparison: ComparisonState
  setComparisonSubTab: (tab: 'comparison' | 'liveview') => void
  setComparisonInput: (text: string) => void
  setIsComparing: (v: boolean) => void
  setCurrentJobId: (id: number | null) => void
  appendModelToken: (model: 'qwen32b' | 'translategemma' | 'qwen35_9b' | 'sarashina2', token: string) => void
  setModelComplete: (model: 'qwen32b' | 'translategemma' | 'qwen35_9b' | 'sarashina2', output: string) => void
  setModelError: (model: 'qwen32b' | 'translategemma' | 'qwen35_9b' | 'sarashina2', error: string) => void
  setConsensus: (text: string, done: boolean) => void
  resetComparison: () => void
  setModelEndpoints: (endpoints: ModelEndpoint[]) => void
  setLiveStatus: (model: 'qwen32b' | 'translategemma' | 'qwen35_9b' | 'sarashina2', status: ModelLiveStatus) => void
}

const INITIAL_MODEL_OUTPUT: ModelOutput = { text: '', done: false, error: null, timedOut: false }
const INITIAL_LIVE_STATUS: ModelLiveStatus = {
  inferenceOnline: false, inferenceEndpoint: null, loadedModel: null,
  isTraining: false, trainingProgress: null
}
const INITIAL_COMPARISON_STATE: ComparisonState = {
  activeSubTab: 'comparison',
  inputText: '',
  isComparing: false,
  currentJobId: null,
  modelOutputs: {
    qwen32b:        { ...INITIAL_MODEL_OUTPUT },
    translategemma: { ...INITIAL_MODEL_OUTPUT },
    qwen35_9b:      { ...INITIAL_MODEL_OUTPUT },
    sarashina2:     { ...INITIAL_MODEL_OUTPUT },
  },
  consensusText: '',
  consensusDone: false,
  modelEndpoints: [],
  liveStatuses: {
    qwen32b:        { ...INITIAL_LIVE_STATUS },
    translategemma: { ...INITIAL_LIVE_STATUS },
    qwen35_9b:      { ...INITIAL_LIVE_STATUS },
    sarashina2:     { ...INITIAL_LIVE_STATUS },
  },
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

      comparison: { ...INITIAL_COMPARISON_STATE },
      setComparisonSubTab: (tab) => set(s => ({ comparison: { ...s.comparison, activeSubTab: tab } })),
      setComparisonInput: (text) => set(s => ({ comparison: { ...s.comparison, inputText: text } })),
      setIsComparing: (v) => set(s => ({ comparison: { ...s.comparison, isComparing: v } })),
      setCurrentJobId: (id) => set(s => ({ comparison: { ...s.comparison, currentJobId: id } })),
      appendModelToken: (model, token) => set(s => ({
        comparison: {
          ...s.comparison,
          modelOutputs: {
            ...s.comparison.modelOutputs,
            [model]: { ...s.comparison.modelOutputs[model], text: s.comparison.modelOutputs[model].text + token }
          }
        }
      })),
      setModelComplete: (model, output) => set(s => ({
        comparison: {
          ...s.comparison,
          modelOutputs: {
            ...s.comparison.modelOutputs,
            [model]: { ...s.comparison.modelOutputs[model], text: output, done: true }
          }
        }
      })),
      setModelError: (model, error) => set(s => ({
        comparison: {
          ...s.comparison,
          modelOutputs: {
            ...s.comparison.modelOutputs,
            [model]: { ...s.comparison.modelOutputs[model], error, done: true }
          }
        }
      })),
      setConsensus: (text, done) => set(s => ({ comparison: { ...s.comparison, consensusText: text, consensusDone: done } })),
      resetComparison: () => set(s => ({
        comparison: {
          ...INITIAL_COMPARISON_STATE,
          modelEndpoints: s.comparison.modelEndpoints,
          liveStatuses: s.comparison.liveStatuses,
        }
      })),
      setModelEndpoints: (endpoints) => set(s => ({ comparison: { ...s.comparison, modelEndpoints: endpoints } })),
      setLiveStatus: (model, status) => set(s => ({
        comparison: {
          ...s.comparison,
          liveStatuses: { ...s.comparison.liveStatuses, [model]: status }
        }
      })),
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
