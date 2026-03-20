interface StatusBadgeProps {
  online: boolean
  label?: string
}

export function StatusBadge({ online, label }: StatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${
        online
          ? 'bg-green-900/50 text-green-400'
          : 'bg-zinc-800 text-zinc-500'
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          online ? 'bg-green-400' : 'bg-zinc-500'
        }`}
      />
      {label ?? (online ? 'Online' : 'Offline')}
    </span>
  )
}
