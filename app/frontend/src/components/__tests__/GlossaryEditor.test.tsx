import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { GlossaryEditor } from '../GlossaryEditor'

vi.mock('@/api/glossary', () => ({
  getGlossary: vi.fn(async () => ({ glossary_id: 1, terms: [] })),
  addTerm: vi.fn(async () => null),
  updateTerm: vi.fn(async () => null),
  deleteTerm: vi.fn(async () => {}),
  autoExtract: vi.fn(async () => []),
}))

vi.mock('@/api/client', () => ({
  getBaseUrl: vi.fn(async () => 'http://localhost:18420'),
  apiFetch: vi.fn(async () => new Response('{}', { status: 200 })),
  createWebSocket: vi.fn(async () => null),
  createBookPipelineWebSocket: vi.fn(async () => null),
  getHealthInfo: vi.fn(async () => ({ status: 'ok', app: 'hime', version: '1.1.2' })),
  checkBackendOnline: vi.fn(async () => false),
}))

describe('GlossaryEditor', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <GlossaryEditor book_id={1} />
      </MemoryRouter>
    )
    expect(document.body.textContent?.length).toBeGreaterThan(0)
  })

  it('shows loading state initially', () => {
    const { getByText } = render(
      <MemoryRouter>
        <GlossaryEditor book_id={1} />
      </MemoryRouter>
    )
    // GlossaryEditor shows a loading pulse text while fetching
    expect(getByText(/Lade Glossar/)).toBeInTheDocument()
  })
})
