import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { BookLibrary } from '../BookLibrary'

vi.mock('@/api/epub', () => ({
  getLibrary: vi.fn(async () => []),
  importEpub: vi.fn(async () => null),
  getChapters: vi.fn(async () => []),
  getParagraphs: vi.fn(async () => []),
  saveTranslation: vi.fn(async () => {}),
  exportChapter: vi.fn(async () => ''),
  rescanBookChapters: vi.fn(async () => null),
  updateBookSeries: vi.fn(async () => null),
  getEpubSettings: vi.fn(async () => ({ epub_watch_folder: '', auto_scan_interval: '' })),
  updateEpubSetting: vi.fn(async () => {}),
}))

vi.mock('@/api/client', () => ({
  getBaseUrl: vi.fn(async () => 'http://localhost:18420'),
  apiFetch: vi.fn(async () => new Response('{}', { status: 200 })),
  createWebSocket: vi.fn(async () => null),
  createBookPipelineWebSocket: vi.fn(async () => null),
  getHealthInfo: vi.fn(async () => ({ status: 'ok', app: 'hime', version: '1.1.2' })),
  checkBackendOnline: vi.fn(async () => false),
}))

describe('BookLibrary', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <BookLibrary onBookSelected={vi.fn()} />
      </MemoryRouter>
    )
    expect(document.body.textContent?.length).toBeGreaterThan(0)
  })

  it('renders the Import EPUB button', () => {
    const { getAllByText } = render(
      <MemoryRouter>
        <BookLibrary onBookSelected={vi.fn()} />
      </MemoryRouter>
    )
    // There are two "Import EPUB" buttons - toolbar and empty state
    const importButtons = getAllByText('Import EPUB')
    expect(importButtons.length).toBeGreaterThan(0)
  })

  it('renders the search input', () => {
    const { getByPlaceholderText } = render(
      <MemoryRouter>
        <BookLibrary onBookSelected={vi.fn()} />
      </MemoryRouter>
    )
    expect(getByPlaceholderText('Search…')).toBeInTheDocument()
  })
})
