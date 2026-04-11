import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Comparison } from '../Comparison'

vi.mock('@/api/compare', () => ({
  startCompare: vi.fn(async () => ({ job_id: 1 })),
  fetchModelEndpoints: vi.fn(async () => []),
}))

vi.mock('../../../api/compare', () => ({
  startCompare: vi.fn(async () => ({ job_id: 1 })),
  fetchModelEndpoints: vi.fn(async () => []),
}))

// Mock complex child components
vi.mock('@/components/comparison/ComparisonPills', () => ({
  ComparisonPills: () => <div data-testid="comparison-pills">ComparisonPills</div>,
}))

vi.mock('@/components/comparison/ModelComparisonTab', () => ({
  ModelComparisonTab: () => <div data-testid="model-comparison-tab">ModelComparisonTab</div>,
}))

vi.mock('@/components/comparison/LiveViewTab', () => ({
  LiveViewTab: () => <div data-testid="live-view-tab">LiveViewTab</div>,
}))

// Comparison.tsx uses `../api/compare` (relative import, not @/ alias)
// Stub via the actual module path
vi.mock('../../api/compare', () => ({
  startCompare: vi.fn(async () => ({ job_id: 1 })),
  fetchModelEndpoints: vi.fn(async () => []),
}))

describe('Comparison', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <Comparison />
      </MemoryRouter>
    )
    expect(document.body.textContent?.length).toBeGreaterThan(0)
  })

  it('renders comparison pills', () => {
    const { getByTestId } = render(
      <MemoryRouter>
        <Comparison />
      </MemoryRouter>
    )
    expect(getByTestId('comparison-pills')).toBeInTheDocument()
  })
})
