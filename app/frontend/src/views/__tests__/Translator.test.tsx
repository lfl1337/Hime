import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Translator } from '../Translator'

// Mock the API modules that Translator and its children use
vi.mock('@/api/epub', () => ({
  getLibrary: vi.fn(async () => []),
  getChapters: vi.fn(async () => []),
  importEpub: vi.fn(async () => null),
  getParagraphs: vi.fn(async () => []),
  saveTranslation: vi.fn(async () => {}),
  exportChapter: vi.fn(async () => ''),
  rescanBookChapters: vi.fn(async () => null),
  updateBookSeries: vi.fn(async () => null),
  getEpubSettings: vi.fn(async () => ({ epub_watch_folder: '', auto_scan_interval: '' })),
  updateEpubSetting: vi.fn(async () => {}),
}))

vi.mock('@/api/translate', () => ({
  createSourceText: vi.fn(async () => ({ id: 1 })),
  startTranslation: vi.fn(async () => ({ job_id: 1 })),
  getTranslation: vi.fn(async () => null),
  listTranslations: vi.fn(async () => []),
}))

vi.mock('@/api/websocket', () => ({
  usePipeline: vi.fn(() => ({
    stage: 'idle',
    outputs: {},
    final: null,
    error: null,
    start: vi.fn(),
    reset: vi.fn(),
  })),
}))

vi.mock('@/api/useBookPipelineV2', () => ({
  useBookPipelineV2: vi.fn(() => ({
    status: null,
    start: vi.fn(),
    stop: vi.fn(),
    reset: vi.fn(),
  })),
}))

vi.mock('@/api/client', () => ({
  getBaseUrl: vi.fn(async () => 'http://localhost:18420'),
  apiFetch: vi.fn(async () => new Response('{}', { status: 200 })),
  createWebSocket: vi.fn(async () => null),
  createBookPipelineWebSocket: vi.fn(async () => null),
  getHealthInfo: vi.fn(async () => ({ status: 'ok', app: 'hime', version: '1.1.2' })),
  checkBackendOnline: vi.fn(async () => false),
}))

// Mock complex child components to avoid deep dependency trees
vi.mock('@/components/epub/LeftPanel', () => ({
  LeftPanel: () => <div data-testid="left-panel">LeftPanel</div>,
}))

vi.mock('@/components/epub/TranslationWorkspace', () => ({
  TranslationWorkspace: () => <div data-testid="translation-workspace">TranslationWorkspace</div>,
}))

describe('Translator', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <Translator />
      </MemoryRouter>
    )
    expect(document.body.textContent?.length).toBeGreaterThan(0)
  })

  it('renders the left panel and workspace', () => {
    const { getByTestId } = render(
      <MemoryRouter>
        <Translator />
      </MemoryRouter>
    )
    expect(getByTestId('left-panel')).toBeInTheDocument()
    expect(getByTestId('translation-workspace')).toBeInTheDocument()
  })
})
