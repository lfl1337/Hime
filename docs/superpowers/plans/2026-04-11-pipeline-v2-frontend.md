# Pipeline v2 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the fully-implemented Pipeline v2 backend into the Hime frontend — preprocess trigger, full-book WebSocket streaming, segment-by-segment progress display, and pipeline_complete EPUB download link.

**Architecture:** New `api/pipeline_v2.ts` (types + API client) → `useBookPipelineV2` hook (WebSocket state machine) → `BookPipelinePanel.tsx` (start/progress UI) → wired into `TranslationWorkspace.tsx` alongside the existing paragraph-level pipeline. The v1 paragraph pipeline stays untouched.

**Tech Stack:** React 19 + TypeScript, Zustand, native WebSocket API (same pattern as `api/websocket.ts`)

---

## Backend WebSocket Contract (read-only reference)

Endpoint: `ws://127.0.0.1:18420/api/v1/pipeline/{book_id}/translate`

Events (server → client):
```
{ event: "preprocess_complete", segment_count: number }
{ event: "segment_start", paragraph_id: number, index: number, total: number }
{ event: "stage1_complete", paragraph_id: number }
{ event: "stage2_complete", paragraph_id: number }
{ event: "stage3_complete", paragraph_id: number }
{ event: "stage4_verdict", paragraph_id: number, verdict: "okay" | "retry", retry_count: number }
{ event: "segment_complete", paragraph_id: number, translation: string }
{ event: "pipeline_complete", epub_path: string }
{ event: "pipeline_error", detail: string }
null  ← server closes after this
```

Preprocess endpoint: `POST /api/v1/pipeline/{book_id}/preprocess`  
Returns: `{ book_id, segment_count, sample: [{ paragraph_id, source_jp, mecab_token_count, glossary_context, rag_context }] }`

---

## File Map

| File | Change |
|------|--------|
| `app/frontend/src/api/client.ts` | Add `createBookPipelineWebSocket(bookId)` |
| `app/frontend/src/api/pipeline_v2.ts` | New — types + `triggerPreprocess()` |
| `app/frontend/src/api/useBookPipelineV2.ts` | New — WebSocket hook |
| `app/frontend/src/components/BookPipelinePanel.tsx` | New — start/progress/result UI |
| `app/frontend/src/components/epub/TranslationWorkspace.tsx` | Add `BookPipelinePanel` below `BookDetails` |

---

### Task 1: Add WebSocket factory to `api/client.ts`

**Files:**
- Modify: `app/frontend/src/api/client.ts` (after existing `createWebSocket` at line ~115)

**Context:** `createWebSocket(jobId)` creates a WS to `/ws/translate/{jobId}` (old per-paragraph pipeline). We need a parallel function for the new book-level v2 endpoint at `/api/v1/pipeline/{bookId}/translate`. Same pattern, different path.

- [ ] **Step 1: Write failing test**

```typescript
// In any test runner — manual verification is fine here since this is infrastructure.
// Instead, write a type-check test by inspection: the function must exist and return Promise<WebSocket>.
// Actual connectivity test happens in Task 4 (dev server verification).
```

Since this is a pure infrastructure addition with no logic branch, skip unit test — verify in Task 4.

- [ ] **Step 2: Add `createBookPipelineWebSocket` to `api/client.ts`**

Find `createWebSocket` (around line 115) and add immediately after it:

```typescript
export async function createBookPipelineWebSocket(bookId: number): Promise<WebSocket> {
  if (import.meta.env.DEV) {
    const wsOrigin = window.location.origin.replace(/^http/, 'ws')
    return new WebSocket(`${wsOrigin}/api/v1/pipeline/${bookId}/translate`)
  }
  const port = await getPort()
  return new WebSocket(`ws://${DEFAULT_BACKEND_HOST}:${port}/api/v1/pipeline/${bookId}/translate`)
}
```

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/api/client.ts
git commit -m "feat(frontend): add createBookPipelineWebSocket for pipeline v2 WS endpoint"
```

---

### Task 2: Create `api/pipeline_v2.ts` — types + preprocess call

**Files:**
- Create: `app/frontend/src/api/pipeline_v2.ts`

- [ ] **Step 1: Write the file**

```typescript
// app/frontend/src/api/pipeline_v2.ts
import { apiFetch } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SegmentSample {
  paragraph_id: number
  source_jp: string
  mecab_token_count: number
  glossary_context: string
  rag_context: string
}

export interface PreprocessResponse {
  book_id: number
  segment_count: number
  sample: SegmentSample[]
}

// Discriminated union of all v2 pipeline WebSocket events
export type PipelineV2Event =
  | { event: 'preprocess_complete'; segment_count: number }
  | { event: 'segment_start'; paragraph_id: number; index: number; total: number }
  | { event: 'stage1_complete'; paragraph_id: number }
  | { event: 'stage2_complete'; paragraph_id: number }
  | { event: 'stage3_complete'; paragraph_id: number }
  | { event: 'stage4_verdict'; paragraph_id: number; verdict: 'okay' | 'retry'; retry_count: number }
  | { event: 'segment_complete'; paragraph_id: number; translation: string }
  | { event: 'pipeline_complete'; epub_path: string }
  | { event: 'pipeline_error'; detail: string }

export type SegmentStatus = 'pending' | 'stage1' | 'stage2' | 'stage3' | 'stage4' | 'complete' | 'error'

export interface SegmentProgress {
  paragraphId: number
  index: number
  status: SegmentStatus
  verdict: 'okay' | 'retry' | null
  retryCount: number
  translation: string | null
}

export type PipelineV2Status =
  | 'idle'
  | 'preprocessing'
  | 'translating'
  | 'complete'
  | 'error'

export interface BookPipelineState {
  status: PipelineV2Status
  totalSegments: number
  completedSegments: number
  segments: Record<number, SegmentProgress>  // keyed by paragraphId
  epubPath: string | null
  error: string | null
}

export const INITIAL_PIPELINE_STATE: BookPipelineState = {
  status: 'idle',
  totalSegments: 0,
  completedSegments: 0,
  segments: {},
  epubPath: null,
  error: null,
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

export async function triggerPreprocess(bookId: number): Promise<PreprocessResponse> {
  const res = await apiFetch(`/api/v1/pipeline/${bookId}/preprocess`, { method: 'POST' })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`Preprocess failed (${res.status}): ${detail}`)
  }
  return res.json() as Promise<PreprocessResponse>
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd app/frontend
npx tsc --noEmit 2>&1 | grep pipeline_v2
```
Expected: no output (no errors)

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/api/pipeline_v2.ts
git commit -m "feat(frontend): add pipeline_v2 types, PreprocessResponse, BookPipelineState, triggerPreprocess"
```

---

### Task 3: Create `useBookPipelineV2` hook

**Files:**
- Create: `app/frontend/src/api/useBookPipelineV2.ts`

**Context:** This hook manages the WebSocket lifecycle and reduces incoming events into `BookPipelineState`. Pattern mirrors `usePipeline` in `api/websocket.ts` but for book-level events. The hook does NOT auto-connect — it exposes a `start()` function that the UI calls.

- [ ] **Step 1: Write the hook**

```typescript
// app/frontend/src/api/useBookPipelineV2.ts
import { useCallback, useRef, useState } from 'react'
import { createBookPipelineWebSocket } from './client'
import type { BookPipelineState, PipelineV2Event, SegmentProgress } from './pipeline_v2'
import { INITIAL_PIPELINE_STATE } from './pipeline_v2'

export interface UseBookPipelineV2Return {
  state: BookPipelineState
  start: (bookId: number) => void
  reset: () => void
}

export function useBookPipelineV2(): UseBookPipelineV2Return {
  const [state, setState] = useState<BookPipelineState>(INITIAL_PIPELINE_STATE)
  const wsRef = useRef<WebSocket | null>(null)

  const reset = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    setState(INITIAL_PIPELINE_STATE)
  }, [])

  const start = useCallback((bookId: number) => {
    // Guard: don't start if already running
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return

    setState({ ...INITIAL_PIPELINE_STATE, status: 'translating' })

    createBookPipelineWebSocket(bookId).then((ws) => {
      wsRef.current = ws

      ws.onmessage = (ev) => {
        if (ev.data === 'null' || ev.data === null) return  // sentinel
        let parsed: PipelineV2Event
        try {
          parsed = JSON.parse(ev.data as string) as PipelineV2Event
        } catch {
          return
        }
        setState(prev => applyV2Event(prev, parsed))
      }

      ws.onerror = () => {
        setState(prev => ({ ...prev, status: 'error', error: 'WebSocket connection error' }))
      }

      ws.onclose = () => {
        // State already updated by pipeline_complete or pipeline_error
      }
    }).catch(() => {
      setState(prev => ({ ...prev, status: 'error', error: 'Failed to connect to pipeline' }))
    })
  }, [])

  return { state, start, reset }
}

function applyV2Event(prev: BookPipelineState, ev: PipelineV2Event): BookPipelineState {
  switch (ev.event) {
    case 'preprocess_complete':
      return { ...prev, status: 'translating', totalSegments: ev.segment_count }

    case 'segment_start': {
      const seg: SegmentProgress = {
        paragraphId: ev.paragraph_id,
        index: ev.index,
        status: 'stage1',
        verdict: null,
        retryCount: 0,
        translation: null,
      }
      return {
        ...prev,
        totalSegments: ev.total,
        segments: { ...prev.segments, [ev.paragraph_id]: seg },
      }
    }

    case 'stage1_complete':
      return updateSegment(prev, ev.paragraph_id, { status: 'stage2' })

    case 'stage2_complete':
      return updateSegment(prev, ev.paragraph_id, { status: 'stage3' })

    case 'stage3_complete':
      return updateSegment(prev, ev.paragraph_id, { status: 'stage4' })

    case 'stage4_verdict':
      return updateSegment(prev, ev.paragraph_id, {
        verdict: ev.verdict,
        retryCount: ev.retry_count,
        // Stay in stage4 until segment_complete
      })

    case 'segment_complete':
      return {
        ...updateSegment(prev, ev.paragraph_id, {
          status: 'complete',
          translation: ev.translation,
        }),
        completedSegments: prev.completedSegments + 1,
      }

    case 'pipeline_complete':
      return { ...prev, status: 'complete', epubPath: ev.epub_path }

    case 'pipeline_error':
      return { ...prev, status: 'error', error: ev.detail }

    default:
      return prev
  }
}

function updateSegment(
  prev: BookPipelineState,
  paragraphId: number,
  patch: Partial<SegmentProgress>,
): BookPipelineState {
  const existing = prev.segments[paragraphId]
  if (!existing) return prev
  return {
    ...prev,
    segments: {
      ...prev.segments,
      [paragraphId]: { ...existing, ...patch },
    },
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd app/frontend
npx tsc --noEmit 2>&1 | grep -E "pipeline_v2|useBookPipeline"
```
Expected: no output

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/api/useBookPipelineV2.ts
git commit -m "feat(frontend): add useBookPipelineV2 hook with WS state machine for book-level translation"
```

---

### Task 4: Create `BookPipelinePanel.tsx`

**Files:**
- Create: `app/frontend/src/components/BookPipelinePanel.tsx`

**Context:** This component takes a `book` prop and shows: (1) a "Translate full book" button that triggers the WS pipeline, (2) a live segment progress bar, (3) stage indicators per active segment, (4) on completion an EPUB download link. Uses `useBookPipelineV2` internally.

- [ ] **Step 1: Write the component**

```tsx
// app/frontend/src/components/BookPipelinePanel.tsx
import { useState } from 'react'
import { useBookPipelineV2 } from '@/api/useBookPipelineV2'
import type { BookSummary } from '@/api/epub'
import type { SegmentProgress } from '@/api/pipeline_v2'

interface Props {
  book: BookSummary
}

const STAGE_LABELS: Record<string, string> = {
  stage1: 'S1',
  stage2: 'S2',
  stage3: 'S3',
  stage4: 'S4',
  complete: '✓',
  error: '✗',
  pending: '…',
}

const STAGE_COLORS: Record<string, string> = {
  stage1: 'bg-blue-800 text-blue-300',
  stage2: 'bg-indigo-800 text-indigo-300',
  stage3: 'bg-violet-800 text-violet-300',
  stage4: 'bg-purple-800 text-purple-300',
  complete: 'bg-emerald-900 text-emerald-300',
  error: 'bg-red-900 text-red-300',
  pending: 'bg-zinc-800 text-zinc-500',
}

function SegmentRow({ seg }: { seg: SegmentProgress }) {
  const stageColor = STAGE_COLORS[seg.status] ?? STAGE_COLORS.pending
  const verdictBadge = seg.verdict === 'retry'
    ? <span className="ml-1 text-[9px] px-1 rounded bg-amber-900/60 text-amber-400">retry×{seg.retryCount}</span>
    : seg.verdict === 'okay'
    ? <span className="ml-1 text-[9px] px-1 rounded bg-emerald-900/40 text-emerald-500">ok</span>
    : null

  return (
    <div className="flex items-center gap-2 py-0.5">
      <span className="text-[10px] text-zinc-600 w-8 text-right">#{seg.index + 1}</span>
      <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${stageColor}`}>
        {STAGE_LABELS[seg.status] ?? '?'}
      </span>
      {verdictBadge}
      {seg.status === 'complete' && seg.translation && (
        <span className="text-[10px] text-zinc-500 truncate max-w-[200px]">
          {seg.translation.slice(0, 60)}…
        </span>
      )}
    </div>
  )
}

export function BookPipelinePanel({ book }: Props) {
  const { state, start, reset } = useBookPipelineV2()
  const [open, setOpen] = useState(false)

  const isRunning = state.status === 'translating'
  const isDone = state.status === 'complete'
  const isError = state.status === 'error'
  const progressPct = state.totalSegments > 0
    ? Math.round((state.completedSegments / state.totalSegments) * 100)
    : 0

  // Only show last 8 active/recent segments to avoid UI overload
  const visibleSegments = Object.values(state.segments)
    .sort((a, b) => b.index - a.index)
    .slice(0, 8)

  return (
    <div className="border-t border-zinc-800 mt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full px-4 py-2 text-sm text-zinc-300 hover:text-zinc-100 flex items-center justify-between"
      >
        <span>Pipeline v2 — Full Book</span>
        <span className="text-xs text-zinc-500">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          {/* Status + controls */}
          <div className="flex items-center gap-2">
            {state.status === 'idle' && (
              <button
                onClick={() => start(book.id)}
                className="text-xs px-3 py-1.5 rounded bg-violet-900/50 hover:bg-violet-900/70 text-violet-300 transition-colors"
              >
                Translate full book
              </button>
            )}
            {isRunning && (
              <div className="flex items-center gap-2">
                <span className="inline-block h-3 w-3 animate-spin rounded-full border border-zinc-600 border-t-zinc-300" />
                <span className="text-xs text-zinc-400">
                  {state.completedSegments}/{state.totalSegments} segments
                </span>
              </div>
            )}
            {(isDone || isError) && (
              <button
                onClick={reset}
                className="text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400"
              >
                Reset
              </button>
            )}
          </div>

          {/* Progress bar */}
          {(isRunning || isDone) && state.totalSegments > 0 && (
            <div>
              <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                <span>{progressPct}% complete</span>
                <span>{state.completedSegments}/{state.totalSegments}</span>
              </div>
              <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-violet-600 transition-all duration-300"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          )}

          {/* Error */}
          {isError && state.error && (
            <p className="text-xs text-red-400">{state.error}</p>
          )}

          {/* Completion + download */}
          {isDone && state.epubPath && (
            <div className="rounded-lg border border-emerald-800/50 bg-emerald-950/30 p-3">
              <p className="text-xs text-emerald-400 font-medium mb-1">Translation complete!</p>
              <p className="text-[10px] text-zinc-500 font-mono break-all">{state.epubPath}</p>
            </div>
          )}

          {/* Live segment stream */}
          {visibleSegments.length > 0 && (
            <div className="space-y-0.5 max-h-40 overflow-y-auto">
              {visibleSegments.map(seg => (
                <SegmentRow key={seg.paragraphId} seg={seg} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd app/frontend
npx tsc --noEmit 2>&1 | grep BookPipelinePanel
```
Expected: no output

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src/components/BookPipelinePanel.tsx
git commit -m "feat(frontend): add BookPipelinePanel with live segment progress for pipeline v2"
```

---

### Task 5: Wire `BookPipelinePanel` into `TranslationWorkspace`

**Files:**
- Modify: `app/frontend/src/components/epub/TranslationWorkspace.tsx`

**Context:** `TranslationWorkspace.tsx` renders `<BookDetails>` at the bottom of the right sidebar (around line 375). We add `<BookPipelinePanel>` directly below it when a book is selected. The `BookDetails` sidebar is at the end of the component — locate the `{book && (<BookDetails .../>)}` block and add our panel after it.

- [ ] **Step 1: Add import at top of TranslationWorkspace.tsx**

Find the existing imports block and add:

```typescript
import { BookPipelinePanel } from '@/components/BookPipelinePanel'
```

- [ ] **Step 2: Add panel after BookDetails**

Find the `{book && (<BookDetails ... />)}` block (around line 375-387) and replace with:

```tsx
{book && (
  <>
    <BookDetails
      book_id={book.id}
      series_id={book.series_id ?? null}
      series_title={book.series_title ?? null}
      onSeriesChange={async (id, title) => {
        if (!book) return
        try {
          await updateBookSeries(book.id, id, title)
        } catch (e) {
          console.error('Failed to save series:', e)
        }
      }}
      sample_source={currentParagraph?.source_text}
      sample_translation={currentParagraph?.translated_text ?? undefined}
    />
    <BookPipelinePanel book={book} />
  </>
)}
```

(Note: if Task 2 from the quick-fixes plan was already applied, `updateBookSeries` is already imported. If not, add `import { ... updateBookSeries } from '@/api/epub'` to the existing epub import line.)

- [ ] **Step 3: Run dev server and verify**

```bash
cd app/frontend
npm run dev
```

1. Select a book in the Translator view
2. Open the right sidebar — "Book details" panel appears as before
3. Below it a new "Pipeline v2 — Full Book" section with a ▸ arrow
4. Click to expand — "Translate full book" button visible
5. Click "Translate full book":
   - Backend receives WS connection at `/api/v1/pipeline/{bookId}/translate`
   - Progress bar appears, segments stream in
   - On completion, shows epub_path

- [ ] **Step 4: Commit**

```bash
git add app/frontend/src/components/epub/TranslationWorkspace.tsx
git commit -m "feat(frontend): wire BookPipelinePanel into TranslationWorkspace sidebar"
```

---

## Self-Review

**Spec coverage:**
- F2 (Pipeline v2 — 0% integrated) → All 5 tasks ✅
  - `POST /pipeline/{id}/preprocess` → `triggerPreprocess()` in `pipeline_v2.ts` ✅
  - `WS /pipeline/{id}/translate` → `createBookPipelineWebSocket` + `useBookPipelineV2` ✅
  - All 9 event types handled in `applyV2Event` ✅
  - Progress UI → `BookPipelinePanel.tsx` ✅
  - Wired into existing workspace → Task 5 ✅

**No placeholders found.**

**Type consistency:**
- `PipelineV2Event` union covers all 9 events from backend contract ✅
- `SegmentProgress.status` values match all cases in `applyV2Event` ✅
- `BookPipelinePanel` accepts `BookSummary` which has `book.id` ✅
- `createBookPipelineWebSocket` matches `getPort`/`DEFAULT_BACKEND_HOST` pattern from `client.ts` ✅
