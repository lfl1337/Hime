// Inference model health
export interface ModelEndpoint {
  key: 'qwen32b' | 'translategemma' | 'qwen35_9b' | 'sarashina2'
  name: string
  endpoint: string
  online: boolean
  loaded_model: string | null
}

// Per-model streaming output (Sub-Tab 1)
export interface ModelOutput {
  text: string
  done: boolean
  error: string | null
  timedOut: boolean
}

// Sub-Tab 2 live status
export interface ModelLiveStatus {
  inferenceOnline: boolean
  inferenceEndpoint: string | null
  loadedModel: string | null
  isTraining: boolean
  trainingProgress: {
    currentStep: number
    totalSteps: number
    progressPct: number
    loss: number | null
    eta: string | null
    epoch: number | null
  } | null
}

// Zustand slice shape
export interface ComparisonState {
  activeSubTab: 'comparison' | 'liveview'
  inputText: string
  isComparing: boolean
  currentJobId: number | null
  modelOutputs: Record<'qwen32b' | 'translategemma' | 'qwen35_9b' | 'sarashina2', ModelOutput>
  consensusText: string
  consensusDone: boolean
  modelEndpoints: ModelEndpoint[]
  liveStatuses: Record<'qwen32b' | 'translategemma' | 'qwen35_9b' | 'sarashina2', ModelLiveStatus>
}
