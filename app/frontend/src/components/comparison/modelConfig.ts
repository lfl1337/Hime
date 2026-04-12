export const MODEL_CONFIG = {
  qwen32b:        { displayName: 'Qwen2.5-32B (v2 LoRA)',         accentColor: 'amber'   as const },
  translategemma: { displayName: 'TranslateGemma-12B',            accentColor: 'blue'    as const },
  qwen35_9b:      { displayName: 'Qwen3.5-9B',                   accentColor: 'emerald' as const },
  sarashina2:     { displayName: 'Sarashina2-7B (coming soon)',   accentColor: 'purple'  as const },
} as const

export type ModelKey = keyof typeof MODEL_CONFIG
export const MODEL_KEYS = ['qwen32b', 'translategemma', 'qwen35_9b', 'sarashina2'] as const
