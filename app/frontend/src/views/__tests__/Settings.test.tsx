import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Settings } from '../Settings'

// Settings imports useTheme from @/App
vi.mock('@/App', () => ({
  useTheme: vi.fn(() => ({
    current: 'dark',
    applyTheme: vi.fn(),
  })),
}))

vi.mock('@/api/training', () => ({
  getTrainingConfig: vi.fn(async () => ({
    models_base_path: '',
    lora_path: '',
    training_log_path: '',
    scripts_path: '',
  })),
  updateTrainingConfig: vi.fn(async () => ({
    models_base_path: '',
    lora_path: '',
    training_log_path: '',
    scripts_path: '',
  })),
  getMemoryDetail: vi.fn(async () => null),
  getHardwareStats: vi.fn(async () => null),
  getHardwareHistory: vi.fn(async () => []),
  createHardwareEventSource: vi.fn(async () => null),
}))

vi.mock('@/api/epub', () => ({
  getEpubSettings: vi.fn(async () => ({ epub_watch_folder: '', auto_scan_interval: '' })),
  updateEpubSetting: vi.fn(async () => {}),
  getLibrary: vi.fn(async () => []),
  getChapters: vi.fn(async () => []),
  importEpub: vi.fn(async () => null),
}))

vi.mock('@/api/client', () => ({
  getBaseUrl: vi.fn(async () => 'http://localhost:18420'),
  apiFetch: vi.fn(async () => new Response('{}', { status: 200 })),
  createWebSocket: vi.fn(async () => null),
  createBookPipelineWebSocket: vi.fn(async () => null),
  getHealthInfo: vi.fn(async () => ({ status: 'ok', app: 'hime', version: '1.1.2' })),
  checkBackendOnline: vi.fn(async () => false),
}))

// ModelStatusDashboard has its own API calls — mock it
vi.mock('@/components/ModelStatusDashboard', () => ({
  ModelStatusDashboard: () => <div data-testid="model-status-dashboard">ModelStatusDashboard</div>,
}))

vi.mock('@/utils/connectionRegistry', () => ({
  connectionRegistry: {
    getAll: vi.fn(() => []),
    register: vi.fn(),
    unregister: vi.fn(),
    incrementEvents: vi.fn(),
  },
}))

describe('Settings', () => {
  it('renders without crashing', () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    )
    expect(document.body.textContent?.length).toBeGreaterThan(0)
  })

  it('renders the Settings heading', () => {
    const { getByText } = render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    )
    expect(getByText('Settings')).toBeInTheDocument()
  })

  it('renders Appearance section', () => {
    const { getByText } = render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>
    )
    expect(getByText('Appearance')).toBeInTheDocument()
  })
})
