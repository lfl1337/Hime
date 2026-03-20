interface ModelSelectorProps {
  value: string
  onChange: (value: string) => void
  disabled?: boolean
}

const MODELS = [
  { value: 'qwen2.5-14b', label: 'Qwen 2.5 14B' },
  { value: 'qwen2.5-32b', label: 'Qwen 2.5 32B' },
  { value: 'qwen2.5-72b', label: 'Qwen 2.5 72B' },
]

export function ModelSelector({ value, onChange, disabled }: ModelSelectorProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      className="rounded-lg bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-sm text-zinc-200 focus:outline-none focus:ring-2 focus:ring-[#7C6FCD] disabled:opacity-50"
    >
      {MODELS.map((m) => (
        <option key={m.value} value={m.value}>
          {m.label}
        </option>
      ))}
    </select>
  )
}
