/**
 * TrainingMonitor smoke test — render-only.
 * DO NOT add interaction or state manipulation here.
 * The source file had recent memory leak fixes and must not be touched.
 *
 * NOTE: TrainingMonitor is intentionally not rendered in this test.
 * The component has ~600 lines with complex EventSource/SSE connections,
 * multiple setInterval timers, and recharts that crash jsdom's worker process.
 * Rendering it in jsdom causes a Worker crash even with full mocking.
 * Full E2E testing of TrainingMonitor is deferred to Phase 9 browser smoke test.
 */
import { describe, it, expect } from 'vitest'

describe('TrainingMonitor', () => {
  it('module exports TrainingMonitor function (import-level smoke test)', async () => {
    // Just verify the module exports correctly without rendering
    const mod = await import('../TrainingMonitor')
    expect(typeof mod.TrainingMonitor).toBe('function')
  })
})
