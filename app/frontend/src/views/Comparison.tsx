import { useEffect } from 'react'
import { useStore } from '../store'
import { fetchModelEndpoints } from '../api/compare'
import { ComparisonPills } from '../components/comparison/ComparisonPills'
import { ModelComparisonTab } from '../components/comparison/ModelComparisonTab'
import { LiveViewTab } from '../components/comparison/LiveViewTab'

export function Comparison() {
  const activeSubTab = useStore(s => s.comparison.activeSubTab)
  const setComparisonSubTab = useStore(s => s.setComparisonSubTab)
  const setModelEndpoints = useStore(s => s.setModelEndpoints)

  // Initial model endpoint fetch on mount
  useEffect(() => {
    fetchModelEndpoints()
      .then(setModelEndpoints)
      .catch(console.error)
  }, [setModelEndpoints])

  return (
    <div className="p-6 space-y-4 overflow-y-auto h-full">
      <ComparisonPills
        active={activeSubTab}
        onSelect={setComparisonSubTab}
      />
      <div className="transition-opacity duration-200">
        {activeSubTab === 'comparison'
          ? <ModelComparisonTab />
          : <LiveViewTab active={true} />
        }
      </div>
    </div>
  )
}
