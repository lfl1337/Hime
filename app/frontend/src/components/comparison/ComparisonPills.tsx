interface ComparisonPillsProps {
  active: 'comparison' | 'liveview'
  onSelect: (tab: 'comparison' | 'liveview') => void
}

export function ComparisonPills({ active, onSelect }: ComparisonPillsProps) {
  return (
    <div className="flex gap-2">
      {(['comparison', 'liveview'] as const).map((tab) => (
        <button
          key={tab}
          onClick={() => onSelect(tab)}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            active === tab
              ? 'bg-purple-500 text-white'
              : 'bg-zinc-700 text-zinc-400 hover:bg-zinc-600'
          }`}
        >
          {tab === 'comparison' ? '比較' : '生'}
        </button>
      ))}
    </div>
  )
}
