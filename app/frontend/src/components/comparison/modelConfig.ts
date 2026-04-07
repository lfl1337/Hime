export const MODEL_CONFIG = {
  gemma:    { displayName: 'Gemma 3 12B',     accentColor: 'blue'    as const },
  deepseek: { displayName: 'DeepSeek R1 32B',  accentColor: 'emerald' as const },
  qwen32b:  { displayName: 'Qwen 2.5 32B',    accentColor: 'amber'   as const },
} as const

export type ModelKey = keyof typeof MODEL_CONFIG
export const MODEL_KEYS = ['gemma', 'deepseek', 'qwen32b'] as const
