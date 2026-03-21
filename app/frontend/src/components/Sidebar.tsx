import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useStore } from '@/store'
import { StatusBadge } from './StatusBadge'
import { getRunningProcesses } from '../api/training'

interface NavItem {
  to: string
  label: string
  icon: string
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Translator', icon: '翻' },
  { to: '/comparison', label: 'Comparison', icon: '比' },
  { to: '/editor', label: 'Editor', icon: '編' },
  { to: '/monitor', label: 'Monitor', icon: '監' },
]

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)
  const backendOnline = useStore((s) => s.backendOnline)
  const [trainingRun, setTrainingRun] = useState<string | null>(null)

  useEffect(() => {
    const check = () =>
      getRunningProcesses()
        .then(procs => setTrainingRun(procs[0]?.model_name ?? null))
        .catch(() => {})
    void check()
    const id = setInterval(check, 10_000)
    return () => clearInterval(id)
  }, [])

  return (
    <aside
      className={`flex flex-col bg-zinc-900 border-r border-zinc-800 transition-all duration-200 ${
        collapsed ? 'w-14' : 'w-48'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-4 border-b border-zinc-800">
        {!collapsed && (
          <span className="text-base font-bold text-zinc-100 tracking-wide">姫</span>
        )}
        <button
          onClick={() => setCollapsed((c) => !c)}
          className="ml-auto rounded p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      {/* Nav items */}
      <nav className="flex-1 py-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 mx-1 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-[#7C6FCD]/20 text-[#7C6FCD]'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
              }`
            }
          >
            <span className="text-lg w-6 text-center flex-shrink-0 relative">
              {item.icon}
              {item.to === '/monitor' && trainingRun && (
                <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-green-400 animate-pulse" />
              )}
            </span>
            {!collapsed && (
              <span className="flex items-center gap-1.5">
                {item.label}
                {item.to === '/monitor' && trainingRun && (
                  <span className="text-green-400 text-xs font-mono truncate max-w-[80px]" title={trainingRun}>
                    ●
                  </span>
                )}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer — backend status */}
      <div className="px-3 py-3 border-t border-zinc-800">
        {collapsed ? (
          <span
            className={`block h-2 w-2 rounded-full mx-auto ${
              backendOnline ? 'bg-green-400' : 'bg-zinc-600'
            }`}
          />
        ) : (
          <div className="flex flex-col gap-1">
            <span className="text-xs text-zinc-600">Backend</span>
            <StatusBadge online={backendOnline} />
            <p className="mt-1 text-xs text-zinc-600">Hime v0.6.1</p>
          </div>
        )}
      </div>
    </aside>
  )
}
