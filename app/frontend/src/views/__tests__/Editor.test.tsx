import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Editor } from '../Editor'

vi.mock('@/api/epub', () => ({
  getLibrary: vi.fn(async () => []),
  getChapters: vi.fn(async () => []),
  getParagraphs: vi.fn(async () => []),
  saveTranslation: vi.fn(async () => {}),
  importEpub: vi.fn(async () => null),
  exportChapter: vi.fn(async () => ''),
  rescanBookChapters: vi.fn(async () => null),
  updateBookSeries: vi.fn(async () => null),
  getEpubSettings: vi.fn(async () => ({ epub_watch_folder: '', auto_scan_interval: '' })),
  updateEpubSetting: vi.fn(async () => {}),
}))

vi.mock('@/api/verify', () => ({
  verifyTranslation: vi.fn(async () => ({ score: 1.0, feedback: '' })),
}))

vi.mock('@/api/client', () => ({
  getBaseUrl: vi.fn(async () => 'http://localhost:18420'),
  apiFetch: vi.fn(async () => new Response('{}', { status: 200 })),
  createWebSocket: vi.fn(async () => null),
  createBookPipelineWebSocket: vi.fn(async () => null),
  getHealthInfo: vi.fn(async () => ({ status: 'ok', app: 'hime', version: '1.1.2' })),
  checkBackendOnline: vi.fn(async () => false),
}))

describe('Editor', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <Editor />
      </MemoryRouter>
    )
    expect(document.body.textContent?.length).toBeGreaterThan(0)
  })

  it('shows the no-book-selected message when no book is selected', () => {
    const { getByText } = render(
      <MemoryRouter>
        <Editor />
      </MemoryRouter>
    )
    // Store default has selectedBookId = null
    expect(getByText('Translation Editor')).toBeInTheDocument()
  })
})
