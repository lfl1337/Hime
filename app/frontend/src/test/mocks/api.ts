/**
 * Re-usable vi.fn() stubs for the Hime API modules.
 * Import these in test files after setting up vi.mock() for the relevant module.
 *
 * Usage in a test file:
 *   import { clientMocks } from '@/test/mocks/api'
 *   vi.mock('@/api/client', () => clientMocks)
 */

import { vi } from 'vitest'

// --- @/api/client ----------------------------------------------------------
export const clientMocks = {
  getBaseUrl: vi.fn(async () => 'http://localhost:18420'),
  apiFetch: vi.fn(async () => new Response('{}', { status: 200 })),
  createWebSocket: vi.fn(async () => null),
  createBookPipelineWebSocket: vi.fn(async () => null),
  getHealthInfo: vi.fn(async () => ({ status: 'ok', app: 'hime', version: '1.1.2' })),
  checkBackendOnline: vi.fn(async () => false),
}

// --- @/api/translate -------------------------------------------------------
export const translateMocks = {
  createSourceText: vi.fn(async () => ({ id: 1 })),
  startTranslation: vi.fn(async () => ({ job_id: 1 })),
  getTranslation: vi.fn(async () => null),
  listTranslations: vi.fn(async () => []),
}

// --- @/api/epub ------------------------------------------------------------
export const epubMocks = {
  importEpub: vi.fn(async () => null),
  getLibrary: vi.fn(async () => []),
  getChapters: vi.fn(async () => []),
  getParagraphs: vi.fn(async () => []),
  saveTranslation: vi.fn(async () => {}),
  exportChapter: vi.fn(async () => ''),
  rescanBookChapters: vi.fn(async () => null),
  updateBookSeries: vi.fn(async () => null),
  getEpubSettings: vi.fn(async () => ({ epub_watch_folder: '', auto_scan_interval: '' })),
  updateEpubSetting: vi.fn(async () => {}),
}

// --- @/api/models ----------------------------------------------------------
export const modelsMocks = {
  checkHealth: vi.fn(async () => ({ status: 'ok', app: 'hime' })),
}

// --- @/api/glossary --------------------------------------------------------
export const glossaryMocks = {
  getGlossary: vi.fn(async () => ({ glossary_id: 1, terms: [] })),
  addTerm: vi.fn(async () => null),
  updateTerm: vi.fn(async () => null),
  deleteTerm: vi.fn(async () => {}),
  autoExtract: vi.fn(async () => []),
}

// --- @/api/training --------------------------------------------------------
export const trainingMocks = {
  getTrainingStatus: vi.fn(async () => null),
  getCheckpoints: vi.fn(async () => []),
  getLossHistory: vi.fn(async () => []),
  getTrainingLog: vi.fn(async () => []),
  fetchAllRuns: vi.fn(async () => []),
  fetchGGUFModels: vi.fn(async () => []),
  createTrainingEventSource: vi.fn(async () => null),
  startTraining: vi.fn(async () => null),
  stopTraining: vi.fn(async () => ({ stopped: false, graceful: false })),
  saveTrainingCheckpoint: vi.fn(async () => null),
  getRunningProcesses: vi.fn(async () => []),
  getAvailableCheckpoints: vi.fn(async () => []),
  getBackendLog: vi.fn(async () => ({ lines: [] })),
  getTrainingConfig: vi.fn(async () => ({
    models_base_path: '',
    lora_path: '',
    training_log_path: '',
    scripts_path: '',
  })),
  getCondaEnvs: vi.fn(async () => []),
  updateTrainingConfig: vi.fn(async () => ({
    models_base_path: '',
    lora_path: '',
    training_log_path: '',
    scripts_path: '',
  })),
  getStopConfig: vi.fn(async () => null),
  updateStopConfig: vi.fn(async () => null),
  getMemoryDetail: vi.fn(async () => null),
  getHardwareStats: vi.fn(async () => null),
  getHardwareHistory: vi.fn(async () => []),
  createHardwareEventSource: vi.fn(async () => null),
}

// --- @/api/compare ---------------------------------------------------------
export const compareMocks = {
  startCompare: vi.fn(async () => ({ job_id: 1 })),
  fetchModelEndpoints: vi.fn(async () => []),
}
