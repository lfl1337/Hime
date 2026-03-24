interface BackendBannerProps {
  visible: boolean
}

export function BackendBanner({ visible }: BackendBannerProps) {
  if (!visible) return null

  return (
    <div className="w-full bg-amber-900/60 border-b border-amber-700 px-4 py-2 text-sm text-amber-200">
      <span className="font-semibold">Backend offline</span>
      {' — start with: '}
      <code className="bg-amber-950/50 px-1.5 py-0.5 rounded text-amber-300 text-xs">
        cd backend &amp;&amp; uv run python run.py
      </code>
    </div>
  )
}
