# WS3: UI/UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Stage 1 streaming visualization, model status dashboard, offline-first UX, and fix model naming (Gemma 27B → 12B) in the Translator and Comparison views.

**Architecture:** The frontend already has a working pipeline (PipelineProgress, usePipeline hook, TranslationWorkspace). This plan adds: a collapsible Stage 1 panel showing 3 model cards with streaming tokens, a reusable ModelStatus dashboard, model_unavailable event handling, and friendly offline states.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Zustand, Tauri

**Dependencies:** The ModelStatusDashboard (Task 4) hits `/api/v1/models` which WS2 expands from 3 to 6 models. If WS2 hasn't run yet, the dashboard still works — it just shows 3 Stage 1 models instead of all 6. The `model_unavailable` WebSocket event (Task 2) is emitted by WS2's pipeline changes.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `app/frontend/src/components/Stage1Panel.tsx` | 3-card Stage 1 streaming panel |
| Create | `app/frontend/src/components/ModelStatusDashboard.tsx` | Health status for all pipeline models |
| Modify | `app/frontend/src/components/epub/TranslationWorkspace.tsx` | Integrate Stage1Panel, offline state |
| Modify | `app/frontend/src/api/websocket.ts` | Add model_unavailable event type |
| Modify | `app/frontend/src/components/comparison/modelConfig.ts` | Fix Gemma 27B → 12B |
| Modify | `app/frontend/src/components/comparison/ModelPanel.tsx` | Offline badge |
| Modify | `app/frontend/src/views/Comparison.tsx` | Unavailable model placeholder |
| Modify | `app/frontend/src/hooks/useModelPolling.ts` | Poll all 6 models |
| Modify | `app/frontend/src/views/Translator.tsx` | Offline-first empty state |

**DO NOT touch:** `app/backend/`, `scripts/`, `.github/`, `app/frontend/src/views/TrainingMonitor.tsx`

---

### Task 1: Fix Model Config Names

**Files:**
- Modify: `app/frontend/src/components/comparison/modelConfig.ts`

- [ ] **Step 1: Update Gemma display name from 27B to 12B**

Replace the full content of `app/frontend/src/components/comparison/modelConfig.ts`:

```typescript
export const MODEL_CONFIG = {
  gemma:    { displayName: 'Gemma 3 12B',     accentColor: 'blue'    as const },
  deepseek: { displayName: 'DeepSeek R1 32B',  accentColor: 'emerald' as const },
  qwen32b:  { displayName: 'Qwen 2.5 32B',    accentColor: 'amber'   as const },
} as const

export type ModelKey = keyof typeof MODEL_CONFIG
export const MODEL_KEYS = ['gemma', 'deepseek', 'qwen32b'] as const
```

- [ ] **Step 2: Commit**

```bash
git add app/frontend/src/components/comparison/modelConfig.ts
git commit -m "fix(ui): correct Gemma model name from 27B to 12B"
```

---

### Task 2: Add model_unavailable Event to WebSocket Hook

**Files:**
- Modify: `app/frontend/src/api/websocket.ts`

- [ ] **Step 1: Add model_unavailable to PipelineEvent union**

In `app/frontend/src/api/websocket.ts`, add to the `PipelineEvent` type union (after `model_error` line):

```typescript
  | { event: 'model_unavailable'; model: string; reason: string }
```

- [ ] **Step 2: Add modelUnavailable to PipelineState interface**

Add to the `PipelineState` interface:

```typescript
export interface PipelineState {
  stage: PipelineStage
  stage1Tokens: Record<string, string>
  stage1Complete: Record<string, string>
  modelErrors: Record<string, string>
  modelUnavailable: Record<string, string>  // NEW
  consensusOutput: string
  stage2Output: string
  finalOutput: string
  durationMs: number | null
  isComplete: boolean
  error: string | null
}
```

- [ ] **Step 3: Update initialState**

```typescript
const initialState: PipelineState = {
  stage: 'idle',
  stage1Tokens: {},
  stage1Complete: {},
  modelErrors: {},
  modelUnavailable: {},  // NEW
  consensusOutput: '',
  stage2Output: '',
  finalOutput: '',
  durationMs: null,
  isComplete: false,
  error: null,
}
```

- [ ] **Step 4: Handle model_unavailable in applyEvent**

Add a case in the `applyEvent` switch:

```typescript
    case 'model_unavailable':
      return {
        ...prev,
        modelUnavailable: { ...prev.modelUnavailable, [ev.model]: ev.reason },
      }
```

- [ ] **Step 5: Commit**

```bash
git add app/frontend/src/api/websocket.ts
git commit -m "feat(ui): handle model_unavailable pipeline event in WebSocket hook"
```

---

### Task 3: Create Stage 1 Streaming Panel

**Files:**
- Create: `app/frontend/src/components/Stage1Panel.tsx`

- [ ] **Step 1: Create the Stage1Panel component**

```typescript
// app/frontend/src/components/Stage1Panel.tsx
import { useState, memo } from 'react'
import { MODEL_CONFIG, type ModelKey, MODEL_KEYS } from './comparison/modelConfig'

interface Stage1PanelProps {
  stage1Tokens: Record<string, string>
  stage1Complete: Record<string, string>
  modelErrors: Record<string, string>
  modelUnavailable: Record<string, string>
  isStage1Active: boolean
  isStage1Done: boolean
}

const ACCENT_CLASSES: Record<string, { border: string; text: string; bg: string }> = {
  blue:    { border: 'border-blue-600',    text: 'text-blue-400',    bg: 'bg-blue-900/20' },
  emerald: { border: 'border-emerald-600', text: 'text-emerald-400', bg: 'bg-emerald-900/20' },
  amber:   { border: 'border-amber-600',   text: 'text-amber-400',  bg: 'bg-amber-900/20' },
}

const ModelCard = memo(function ModelCard({
  modelKey,
  tokens,
  complete,
  error,
  unavailable,
  isActive,
}: {
  modelKey: ModelKey
  tokens: string
  complete: string
  error: string | null
  unavailable: string | null
  isActive: boolean
}) {
  const config = MODEL_CONFIG[modelKey]
  const accent = ACCENT_CLASSES[config.accentColor] ?? ACCENT_CLASSES.blue
  const output = complete || tokens
  const isDone = !!complete
  const isOffline = !!unavailable
  const hasError = !!error

  return (
    <div className={`flex-1 min-w-0 rounded-lg border ${accent.border} bg-zinc-900 overflow-hidden`}>
      {/* Header */}
      <div className={`px-3 py-1.5 flex items-center justify-between ${accent.bg}`}>
        <span className={`text-xs font-medium ${accent.text}`}>{config.displayName}</span>
        {isOffline && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-400">Offline</span>
        )}
        {hasError && !isOffline && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/50 text-red-400">Error</span>
        )}
        {isDone && !hasError && !isOffline && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-900/50 text-green-400">Done</span>
        )}
        {isActive && !isDone && !hasError && !isOffline && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/50 text-violet-400 animate-pulse">Streaming</span>
        )}
      </div>
      {/* Content */}
      <div className="px-3 py-2 h-32 overflow-y-auto text-xs text-zinc-300 leading-relaxed">
        {isOffline ? (
          <p className="text-zinc-600 italic">{unavailable}</p>
        ) : hasError ? (
          <p className="text-red-400 italic">{error}</p>
        ) : output ? (
          <>
            {output}
            {isActive && !isDone && <span className="text-violet-400 animate-pulse">▋</span>}
          </>
        ) : isActive ? (
          <p className="text-zinc-600 italic animate-pulse">Waiting for tokens…</p>
        ) : (
          <p className="text-zinc-700 italic">Idle</p>
        )}
      </div>
    </div>
  )
})

export function Stage1Panel({
  stage1Tokens,
  stage1Complete,
  modelErrors,
  modelUnavailable,
  isStage1Active,
  isStage1Done,
}: Stage1PanelProps) {
  const [collapsed, setCollapsed] = useState(false)

  // Auto-collapse when Stage 1 is done and user hasn't manually toggled
  const showCollapsed = collapsed || (isStage1Done && collapsed !== false)

  if (!isStage1Active && !isStage1Done) return null

  return (
    <div className="space-y-2">
      <button
        onClick={() => setCollapsed(prev => !prev)}
        className="flex items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <span className="transform transition-transform" style={{ transform: showCollapsed ? 'rotate(-90deg)' : 'rotate(0deg)' }}>
          ▼
        </span>
        Stage 1 — Parallel Translation
        {isStage1Done && (
          <span className="text-green-500 text-[10px]">✓ Complete</span>
        )}
      </button>

      {!showCollapsed && (
        <div className="flex gap-2">
          {MODEL_KEYS.map(key => (
            <ModelCard
              key={key}
              modelKey={key}
              tokens={stage1Tokens[key] ?? ''}
              complete={stage1Complete[key] ?? ''}
              error={modelErrors[key] ?? null}
              unavailable={modelUnavailable[key] ?? null}
              isActive={isStage1Active}
            />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify component renders without errors**

Run: `cd app/frontend && npx tsc --noEmit`
Expected: No TypeScript errors.

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/components/Stage1Panel.tsx
git commit -m "feat(ui): add Stage 1 streaming panel with 3 model cards, offline badges, and collapse"
```

---

### Task 4: Create Model Status Dashboard

**Files:**
- Create: `app/frontend/src/components/ModelStatusDashboard.tsx`

- [ ] **Step 1: Create the ModelStatusDashboard component**

```typescript
// app/frontend/src/components/ModelStatusDashboard.tsx
import { useEffect, useState } from 'react'
import { apiFetch } from '@/api/client'

interface ModelStatus {
  key: string
  name: string
  endpoint: string
  online: boolean
  loaded_model: string | null
  latency_ms: number | null
  stage: string
}

const STAGE_LABELS: Record<string, string> = {
  stage1: 'Stage 1',
  consensus: 'Consensus',
  stage2: 'Stage 2',
  stage3: 'Stage 3',
}

export function ModelStatusDashboard() {
  const [models, setModels] = useState<ModelStatus[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      try {
        const resp = await apiFetch('/api/v1/models', {})
        if (!resp.ok) return
        const data = await resp.json() as ModelStatus[]
        if (!cancelled) setModels(data)
      } catch {
        // Backend offline
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    poll()
    const interval = setInterval(poll, 10_000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  if (loading) {
    return <div className="text-xs text-zinc-500 animate-pulse">Checking models…</div>
  }

  if (models.length === 0) {
    return <div className="text-xs text-zinc-500">No model information available</div>
  }

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wider">Pipeline Models</h3>
      <div className="grid grid-cols-2 xl:grid-cols-3 gap-2">
        {models.map(m => (
          <div
            key={m.key}
            className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 space-y-1"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-zinc-200">{m.name}</span>
              <span className={`w-2 h-2 rounded-full ${
                m.online ? 'bg-green-500' : 'bg-red-500'
              }`} title={m.online ? 'Online' : 'Offline'} />
            </div>
            <div className="text-[10px] text-zinc-500 truncate" title={m.endpoint}>
              {m.endpoint}
            </div>
            <div className="flex items-center gap-2 text-[10px]">
              <span className="text-zinc-600">{STAGE_LABELS[m.stage] ?? m.stage}</span>
              {m.online && m.latency_ms != null && (
                <span className={`${m.latency_ms < 500 ? 'text-green-500' : m.latency_ms < 2000 ? 'text-yellow-500' : 'text-red-500'}`}>
                  {m.latency_ms}ms
                </span>
              )}
              {m.loaded_model && (
                <span className="text-zinc-500 truncate" title={m.loaded_model}>
                  {m.loaded_model}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd app/frontend && npx tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/components/ModelStatusDashboard.tsx
git commit -m "feat(ui): add ModelStatusDashboard with health, latency, and loaded model display"
```

---

### Task 5: Integrate Stage1Panel into TranslationWorkspace

**Files:**
- Modify: `app/frontend/src/components/epub/TranslationWorkspace.tsx`

- [ ] **Step 1: Add Stage1Panel import**

At the top of `TranslationWorkspace.tsx`, add:

```typescript
import { Stage1Panel } from '@/components/Stage1Panel'
```

- [ ] **Step 2: Add Stage1Panel in the translation output area**

In the right panel's scrollable area, after the PipelineProgress section (around line 218-220), add the Stage1Panel:

Insert after the PipelineProgress block:
```tsx
            {/* Stage 1 streaming detail */}
            <Stage1Panel
              stage1Tokens={pipeline.stage1Tokens}
              stage1Complete={pipeline.stage1Complete}
              modelErrors={pipeline.modelErrors}
              modelUnavailable={pipeline.modelUnavailable}
              isStage1Active={pipeline.stage === 'stage1'}
              isStage1Done={
                pipeline.stage !== 'idle' &&
                pipeline.stage !== 'stage1' &&
                Object.keys(pipeline.stage1Complete).length > 0
              }
            />
```

- [ ] **Step 3: Verify it renders**

Run: `cd app/frontend && npm run vite`
Open browser to `http://localhost:1420`, navigate to Translator view.
Expected: No console errors. Stage 1 panel hidden when idle.

- [ ] **Step 4: Commit**

```bash
git add app/frontend/src/components/epub/TranslationWorkspace.tsx
git commit -m "feat(ui): integrate Stage 1 streaming panel into translation workspace"
```

---

### Task 6: Offline-First UX

**Files:**
- Modify: `app/frontend/src/views/Translator.tsx`
- Modify: `app/frontend/src/components/epub/TranslationWorkspace.tsx`

- [ ] **Step 1: Read current Translator.tsx**

Read `app/frontend/src/views/Translator.tsx` to understand the current structure.

- [ ] **Step 2: Add offline-friendly state to TranslationWorkspace**

In `TranslationWorkspace.tsx`, update the "Click Translate to start" empty state (around line 268) to check for backend availability and show a friendly message:

Replace the current idle state block:
```tsx
            {/* Not translated, not running */}
            {!currentParagraph?.is_translated && !isRunning && !pipeline.finalOutput && activeJobId === null && (
              <p className="text-zinc-600 text-sm">Click Translate to start</p>
            )}
```

With:
```tsx
            {/* Not translated, not running — show translate hint or offline message */}
            {!currentParagraph?.is_translated && !isRunning && !pipeline.finalOutput && activeJobId === null && (
              <div className="space-y-2">
                <p className="text-zinc-500 text-sm">Click Translate to start the pipeline</p>
                <p className="text-zinc-700 text-xs">
                  The translation pipeline sends your text through 3 models in parallel,
                  merges the results, and then refines the output in two passes.
                </p>
              </div>
            )}
```

- [ ] **Step 3: Add import and offline banner to Translator.tsx**

In `app/frontend/src/views/Translator.tsx`, add a check for the case where the EPUB library works but models are offline. The EPUB library and translation history should always work — only the "Translate" button should be disabled when models are unavailable. This is already handled by the pipeline error events, so no change is needed here.

The key offline-first principle: translation history, EPUB browsing, editing saved translations — all work without models. Only the "Translate" button triggers model inference.

**No code change needed** — the existing architecture already supports this. The `handleTranslate()` function in TranslationWorkspace will receive a pipeline_error if models are offline, and the error message will display.

- [ ] **Step 4: Commit**

```bash
git add app/frontend/src/components/epub/TranslationWorkspace.tsx
git commit -m "feat(ui): improve offline-first UX with descriptive pipeline hints"
```

---

### Task 7: Update Comparison View for Unavailable Models

**Note on spec §3.4 diff highlighting:** The spec marks diff highlighting between model panels as "optional, if feasible without heavy deps." Adding a diff library (e.g., diff-match-patch) is out of scope for v1.2.0. The Comparison view already shows side-by-side panels; users can visually compare outputs.

**Files:**
- Modify: `app/frontend/src/components/comparison/ModelPanel.tsx`

- [ ] **Step 1: Read current ModelPanel.tsx**

Read `app/frontend/src/components/comparison/ModelPanel.tsx`.

- [ ] **Step 2: Add offline placeholder**

In `ModelPanel.tsx`, add a prop for unavailability and render a placeholder when the model is offline.

Add to the props interface:
```typescript
interface ModelPanelProps {
  modelKey: ModelKey
  output: ModelOutput
  unavailable?: boolean  // NEW
}
```

In the render body, before the output content, add:
```tsx
        {unavailable && !output.text && (
          <div className="flex items-center gap-2 text-zinc-600 text-sm italic">
            <span className="w-2 h-2 rounded-full bg-zinc-600" />
            Model unavailable — output will be skipped in consensus
          </div>
        )}
```

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/components/comparison/ModelPanel.tsx
git commit -m "feat(ui): add offline placeholder for unavailable models in comparison view"
```

---

### Task 8: Extend Model Polling to All 6 Pipeline Models

**Files:**
- Modify: `app/frontend/src/hooks/useModelPolling.ts`

- [ ] **Step 1: Read current useModelPolling.ts**

Read the current implementation at `app/frontend/src/hooks/useModelPolling.ts`.

- [ ] **Step 2: Update to handle all 6 models from new /models endpoint**

The backend's `/api/v1/models` endpoint (updated in WS2) now returns all 6 pipeline models. The `useModelPolling` hook calls `fetchModelEndpoints()` which hits this endpoint. Since WS2 expands the endpoint to return all 6 models, the hook will automatically pick them up.

**However**, the `ModelLiveStatus` type currently only maps `gemma | deepseek | qwen32b`. The type needs to be extended.

In `useModelPolling.ts`, update the Record type to use `string` instead of `ModelKey`:

Replace:
```typescript
liveStatuses: Record<ModelKey, ModelLiveStatus>
```

With:
```typescript
liveStatuses: Record<string, ModelLiveStatus>
```

This allows the hook to handle any model key returned by the backend without type errors.

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/hooks/useModelPolling.ts
git commit -m "feat(ui): extend model polling to support all 6 pipeline models"
```

---

### Task 9: Frontend Hardcoded Path Audit

**Files:**
- Audit: all `app/frontend/src/` files

- [ ] **Step 1: Search for hardcoded paths**

Run:
```bash
grep -rn "C:" app/frontend/src/ --include="*.ts" --include="*.tsx"
grep -rn "localhost:8" app/frontend/src/ --include="*.ts" --include="*.tsx"
grep -rn "127.0.0.1" app/frontend/src/ --include="*.ts" --include="*.tsx"
```

- [ ] **Step 2: Verify all URLs come from config**

Expected findings:
- `client.ts`: Port discovery reads from `hime-backend.lock` — this is correct, not hardcoded
- `vite.config.ts`: Reads port dynamically from lock file — correct
- `Sidebar.tsx`: Version string `v1.1.2` — this is updated by bump_version.py, acceptable

If any hardcoded backend URLs are found in components (not in client.ts), they should be replaced with `apiFetch()` calls that go through the proxy.

- [ ] **Step 3: Verify VITE_API_BASE_URL pattern**

Check if `VITE_API_BASE_URL` is used. In the current architecture, the Vite proxy handles all API routing, so there's no need for a separate env var. The `getBaseUrl()` function in `client.ts` handles both dev and prod modes.

**No changes needed** if all API calls go through `apiFetch()` or `createWebSocket()` from client.ts.

- [ ] **Step 4: Commit (if any changes were needed)**

```bash
git add -A app/frontend/src/
git commit -m "fix(ui): remove hardcoded paths in frontend code"
```

---

### Task 10: Final UI/UX Verification

- [ ] **Step 1: TypeScript check**

Run: `cd app/frontend && npx tsc --noEmit`
Expected: Zero errors.

- [ ] **Step 2: Build check**

Run: `cd app/frontend && npm run vite build`
Expected: Build succeeds with no errors.

- [ ] **Step 3: Visual verification**

Run: `cd app/frontend && npm run vite`

Verify:
1. Translator view: EPUB library loads, chapters load, paragraph navigation works
2. Stage 1 panel: Hidden when idle, visible during pipeline (if models were running)
3. Comparison view: Model names show "Gemma 3 12B" (not 27B)
4. Settings view: Paths are editable, memory profiler works

- [ ] **Step 4: Confirm file ownership — no backend or TrainingMonitor changes**

Run: `git diff --name-only HEAD~8` (adjust count)
Confirm no files outside WS3 ownership were modified. Specifically:
- No `app/backend/` files
- No `TrainingMonitor.tsx`
- No `scripts/`
- No `.github/`
