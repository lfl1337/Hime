# Plan: Comparison Tab (比) — Full Implementation

**Target version after completion:** 1.0.0 (minor bump via `python scripts/bump_version.py minor`)
**Current version:** 0.9.10
**Milestone:** All 4 main views implemented

---

## Phase 0 — Documentation Discovery (COMPLETE)

### Key Facts Established

| Finding | Source | Impact |
|---------|--------|--------|
| Store is **Zustand** (`src/store.ts`), NOT Redux Toolkit | `app/frontend/package.json`, `src/store.ts` | Prompt's `comparisonSlice.ts` → add comparison state to existing Zustand store instead |
| `/api/v1/compare` does **NOT exist** | `app/backend/app/main.py` router list | Must create `routers/compare.py` |
| `/api/v1/models` does **NOT exist** | `app/backend/app/main.py` router list | Must create `routers/models.py` |
| WebSocket at `/ws/translate/{job_id}` **already works** for Stage 1 streaming | `app/backend/app/websocket/streaming.py` | Re-use this WS for compare; no new WS needed |
| `GET /api/v1/training/runs` **already exists** and returns `RunInfo[]` | `app/backend/app/routers/training.py` | Sub-Tab 2 Live View uses this directly |
| `httpx` is available in backend dependencies | `app/backend/pyproject.toml` | Use for async inference server health checks |
| `src/hooks/`, `src/types/`, `src/components/comparison/` — **none exist yet** | directory listing | Create them as part of Phase 2/3 |
| `Comparison.tsx` is a **stub placeholder** (16 lines) | `src/views/Comparison.tsx` | Replace in Phase 5 |

### WebSocket Event Reference (pipeline/runner.py)

Events emitted to the WebSocket client during a translation job:

```
Stage 1 (3 models parallel):
  {"event": "stage1_start",    "models": ["gemma", "deepseek", "qwen32b"]}
  {"event": "stage1_token",    "model": "gemma"|"deepseek"|"qwen32b", "token": "..."}
  {"event": "stage1_complete", "model": "gemma"|"deepseek"|"qwen32b", "output": "..."}
  {"event": "model_error",     "stage": "stage1", "model": "...", "detail": "..."}

Consensus:
  {"event": "consensus_start"}
  {"event": "consensus_token",    "token": "..."}
  {"event": "consensus_complete", "output": "..."}

(Stage 2 & 3 events also emitted but not needed for Comparison Tab)

Final / Error:
  {"event": "pipeline_complete", "final_output": "...", "duration_ms": N}
  {"event": "pipeline_error",    "detail": "..."}
```

The frontend should:
1. Listen for `stage1_token` → append to per-model output buffer
2. Listen for `stage1_complete` → mark model done
3. Listen for `consensus_complete` → show consensus panel
4. Close WebSocket after consensus (or let it continue — closing is clean)

### Inference Server Config (config.py)

```python
# Stage 1 — three models used by Comparison Tab
hime_gemma_url    = "http://127.0.0.1:8001/v1"  # model key: "gemma"
hime_deepseek_url = "http://127.0.0.1:8002/v1"  # model key: "deepseek"
hime_qwen32b_url  = "http://127.0.0.1:8003/v1"  # model key: "qwen32b"
```

Health check: GET `{url}/models` → llama.cpp returns `{"object":"list","data":[{"id":"..."}]}`

### `RunInfo` shape (training/runs endpoint)

```typescript
interface RunInfo {
  run_name: string        // e.g. "Qwen2.5-32B-Instruct"
  display_name: string    // e.g. "Qwen 2.5 32B"
  status: 'idle' | 'training' | 'interrupted' | 'complete'
  current_step: number
  max_steps: number
  progress_pct: number
  best_eval_loss: number | null
  has_active_log: boolean
}
```

---

## Phase 1 — Backend: Two New Endpoints

**Files to create/modify:**
- CREATE `app/backend/app/routers/compare.py`
- CREATE `app/backend/app/routers/models.py`
- MODIFY `app/backend/app/main.py` — register both routers

### 1a. `POST /api/v1/compare`

**Purpose:** Accept raw Japanese text, create a SourceText + Translation DB record, return job_id.
The existing WebSocket `/ws/translate/{job_id}` then handles streaming — no new WS needed.

**File:** `app/backend/app/routers/compare.py`

```python
"""Compare endpoint — thin wrapper that creates a pipeline job from raw text."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import verify_api_key
from ..database import get_session
from ..models import SourceText, Translation
from ..utils.sanitize import sanitize_text

router = APIRouter(prefix="/compare", tags=["compare"], dependencies=[Depends(verify_api_key)])


class CompareRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=50_000)
    notes: str | None = Field(default=None, max_length=2_000)


@router.post("")
async def start_compare(
    body: CompareRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Create a pipeline job from raw text (no pre-existing SourceText needed).
    Returns {"job_id": int}.
    Connect to /ws/translate/{job_id} for live streaming.
    """
    text = sanitize_text(body.text, "text")
    notes = sanitize_text(body.notes, "notes") if body.notes else None

    source = SourceText(title="[compare]", content=text, language="ja")
    session.add(source)
    await session.flush()

    translation = Translation(
        source_text_id=source.id,
        content="",
        model="compare",
        notes=notes,
        current_stage="pending",
    )
    session.add(translation)
    await session.commit()
    await session.refresh(translation)
    return {"job_id": translation.id}
```

**Anti-patterns:**
- Do NOT import `run_pipeline` here — pipeline starts via WebSocket, not HTTP
- Do NOT skip `verify_api_key` dependency

### 1b. `GET /api/v1/models`

**Purpose:** Health-check the 3 Stage-1 inference servers (ports 8001/8002/8003).
Used by Sub-Tab 2 Live View and Sub-Tab 1 model-online checks.

**File:** `app/backend/app/routers/models.py`

```python
"""Inference server health check endpoint."""
import httpx
from fastapi import APIRouter, Depends

from ..auth import verify_api_key
from ..config import settings

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(verify_api_key)])

_STAGE1_ENDPOINTS = [
    {"key": "gemma",    "name": "Gemma 3 27B",    "url": None},   # filled at runtime from settings
    {"key": "deepseek", "name": "DeepSeek R1 32B", "url": None},
    {"key": "qwen32b",  "name": "Qwen 2.5 32B",    "url": None},
]


@router.get("")
async def list_models() -> list[dict]:
    """
    Check each Stage-1 inference server and return online status.
    Uses llama.cpp's /v1/models endpoint (OpenAI-compatible).
    Timeout: 2 seconds per server.
    """
    endpoints = [
        {"key": "gemma",    "name": "Gemma 3 27B",    "url": settings.hime_gemma_url},
        {"key": "deepseek", "name": "DeepSeek R1 32B", "url": settings.hime_deepseek_url},
        {"key": "qwen32b",  "name": "Qwen 2.5 32B",    "url": settings.hime_qwen32b_url},
    ]
    results = []
    async with httpx.AsyncClient(timeout=2.0) as client:
        for ep in endpoints:
            try:
                r = await client.get(f"{ep['url']}/models")
                online = r.status_code < 500
                loaded_model = None
                if online:
                    data = r.json()
                    models_list = data.get("data", [])
                    if models_list:
                        loaded_model = models_list[0].get("id")
            except Exception:
                online = False
                loaded_model = None
            results.append({
                "key": ep["key"],
                "name": ep["name"],
                "endpoint": ep["url"],
                "online": online,
                "loaded_model": loaded_model,
            })
    return results
```

**Anti-patterns:**
- Do NOT use `httpx.Client` (sync) — use `httpx.AsyncClient`
- Do NOT let an exception from one server crash the whole endpoint (already handled above)

### 1c. Register routers in `main.py`

Read `app/backend/app/main.py` to find the existing `include_router` calls (they're in a block together). Add:

```python
from .routers import compare as compare_router
from .routers import models as models_router

app.include_router(compare_router.router, prefix="/api/v1")
app.include_router(models_router.router, prefix="/api/v1")
```

### Verification (Phase 1)

After coding:
1. Start the backend: `cd app/backend && python run.py`
2. Test: `curl -H "X-API-Key: ..." http://127.0.0.1:PORT/api/v1/models` → returns list (all offline is OK)
3. Test: `curl -X POST -H "X-API-Key: ..." -H "Content-Type: application/json" -d '{"text":"日本語"}' http://127.0.0.1:PORT/api/v1/compare` → returns `{"job_id": N}`
4. Grep check: `grep -r "compare_router\|models_router" app/backend/app/main.py` → both present

---

## Phase 2 — Frontend Foundation: Types, API, Zustand State

**Files to create/modify:**
- CREATE `app/frontend/src/types/comparison.ts`
- CREATE `app/frontend/src/api/compare.ts`
- MODIFY `app/frontend/src/store.ts` — add comparison state

### 2a. TypeScript types

**File:** `app/frontend/src/types/comparison.ts`

Use the actual API shapes from Phase 0 documentation:

```typescript
// Inference model health
export interface ModelEndpoint {
  key: 'gemma' | 'deepseek' | 'qwen32b'
  name: string
  endpoint: string
  online: boolean
  loaded_model: string | null
}

// Per-model streaming output (Sub-Tab 1)
export interface ModelOutput {
  text: string
  done: boolean
  error: string | null
  timedOut: boolean
}

// Sub-Tab 2 live status
export interface ModelLiveStatus {
  inferenceOnline: boolean
  inferenceEndpoint: string | null
  loadedModel: string | null
  isTraining: boolean
  trainingProgress: {
    currentStep: number
    totalSteps: number
    progressPct: number
    loss: number | null
    eta: string | null
    epoch: number | null
  } | null
}

// Zustand slice shape (for reference)
export interface ComparisonState {
  activeSubTab: 'comparison' | 'liveview'
  inputText: string
  isComparing: boolean
  currentJobId: number | null
  modelOutputs: Record<'gemma' | 'deepseek' | 'qwen32b', ModelOutput>
  consensusText: string
  consensusDone: boolean
  modelEndpoints: ModelEndpoint[]
  liveStatuses: Record<'gemma' | 'deepseek' | 'qwen32b', ModelLiveStatus>
}
```

### 2b. API client

**File:** `app/frontend/src/api/compare.ts`

Pattern to follow: copy patterns from `src/api/training.ts` (apiFetch wrapper, getBaseUrl for WS).

```typescript
import { apiFetch, getBaseUrl } from './client'
import type { ModelEndpoint } from '../types/comparison'

export async function startCompare(text: string, notes?: string): Promise<{ job_id: number }> {
  const res = await apiFetch('/api/v1/compare', {
    method: 'POST',
    body: JSON.stringify({ text, notes: notes ?? null }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText })) as { detail: string }
    throw new Error(err.detail || res.statusText)
  }
  return res.json() as Promise<{ job_id: number }>
}

export async function fetchModelEndpoints(): Promise<ModelEndpoint[]> {
  const res = await apiFetch('/api/v1/models')
  if (!res.ok) throw new Error(`models failed: ${res.statusText}`)
  return res.json() as Promise<ModelEndpoint[]>
}

export async function createCompareWebSocket(jobId: number): Promise<WebSocket> {
  const baseUrl = await getBaseUrl()
  const wsUrl = baseUrl.replace(/^http/, 'ws') + `/ws/translate/${jobId}`
  return new WebSocket(wsUrl)
}
```

**Anti-patterns:**
- Do NOT hardcode port numbers — always use `getBaseUrl()` / `apiFetch`
- Do NOT use native `fetch` — use `apiFetch` from `./client` (handles API key injection)

### 2c. Zustand store extension

**File:** `app/frontend/src/store.ts`

Read the full current file (app/frontend/src/store.ts) first. Then add a `ComparisonSlice` to the Zustand store following the existing patterns:

```typescript
// Add to AppStore interface:
comparison: ComparisonState
setComparisonSubTab: (tab: 'comparison' | 'liveview') => void
setComparisonInput: (text: string) => void
setIsComparing: (v: boolean) => void
setCurrentJobId: (id: number | null) => void
appendModelToken: (model: 'gemma' | 'deepseek' | 'qwen32b', token: string) => void
setModelComplete: (model: 'gemma' | 'deepseek' | 'qwen32b', output: string) => void
setModelError: (model: 'gemma' | 'deepseek' | 'qwen32b', error: string) => void
setConsensus: (text: string) => void
resetComparison: () => void
setModelEndpoints: (endpoints: ModelEndpoint[]) => void
setLiveStatus: (model: 'gemma' | 'deepseek' | 'qwen32b', status: ModelLiveStatus) => void
```

Initial comparison state:
```typescript
const INITIAL_MODEL_OUTPUT = { text: '', done: false, error: null, timedOut: false }
const INITIAL_LIVE_STATUS: ModelLiveStatus = {
  inferenceOnline: false, inferenceEndpoint: null, loadedModel: null,
  isTraining: false, trainingProgress: null
}

comparison: {
  activeSubTab: 'comparison',
  inputText: '',
  isComparing: false,
  currentJobId: null,
  modelOutputs: { gemma: {...INITIAL_MODEL_OUTPUT}, deepseek: {...INITIAL_MODEL_OUTPUT}, qwen32b: {...INITIAL_MODEL_OUTPUT} },
  consensusText: '',
  consensusDone: false,
  modelEndpoints: [],
  liveStatuses: { gemma: {...INITIAL_LIVE_STATUS}, deepseek: {...INITIAL_LIVE_STATUS}, qwen32b: {...INITIAL_LIVE_STATUS} },
},
```

**Important:** The comparison state is NOT added to the `partialize` persist list — it should NOT persist between sessions.

### Verification (Phase 2)

```bash
cd app/frontend && npx tsc --noEmit
```
Must produce no errors on the new files.

---

## Phase 3 — Shared Components: ModelPanel + ConsensusPanel

**Files to create:**
- CREATE `app/frontend/src/components/comparison/ModelPanel.tsx`
- CREATE `app/frontend/src/components/comparison/ConsensusPanel.tsx`
- CREATE `app/frontend/src/components/comparison/ComparisonPills.tsx`

Design reference: match the dark-theme style of `src/views/TrainingMonitor.tsx` (zinc-800 cards, zinc-700 borders, purple-500 accents).

### 3a. `ModelPanel.tsx`

Props:
```typescript
interface ModelPanelProps {
  modelKey: 'gemma' | 'deepseek' | 'qwen32b'
  displayName: string
  accentColor: 'blue' | 'emerald' | 'amber'
  online: boolean
  isTraining: boolean
  output: ModelOutput  // from types/comparison.ts
}
```

Layout (see `comparison-tab-prompt.md` §"Jedes Panel enthält"):
- Header: model name badge + status indicator (Online/Offline/Training)
- Output area: `min-h-[200px] max-h-[400px] overflow-y-auto` — show streaming text OR offline placeholder
- Blinking cursor at end while `!output.done && !output.error`: `after:content-['▋'] after:animate-pulse`
- Footer: copy button (disabled if no output), "Copied!" feedback for 2s
- Offline state: whole panel `opacity-60`

### 3b. `ConsensusPanel.tsx`

Props:
```typescript
interface ConsensusPanelProps {
  text: string
  done: boolean
  onlineModelCount: number  // 0-3 — drives "Partial consensus" message
}
```

### 3c. `ComparisonPills.tsx`

Props:
```typescript
interface ComparisonPillsProps {
  active: 'comparison' | 'liveview'
  onSelect: (tab: 'comparison' | 'liveview') => void
}
```

Two pills: `比較` (comparison) and `生` (liveview). Active: `bg-purple-500 text-white`. Inactive: `bg-zinc-700 text-zinc-400 hover:bg-zinc-600`. Corner radius: `rounded-lg`.

---

## Phase 4 — Sub-Tab 1: Model Comparison + Streaming

**File to create:** `app/frontend/src/components/comparison/ModelComparisonTab.tsx`

This is the complex component. It orchestrates:
1. Textarea + "比較する" button
2. 3 `ModelPanel` components
3. `ConsensusPanel`
4. WebSocket streaming logic

### Streaming logic

```typescript
// On "Compare" click:
async function startComparison() {
  // 1. Reset previous comparison state
  dispatch resetComparison()
  setIsComparing(true)

  // 2. POST to /api/v1/compare
  const { job_id } = await startCompare(inputText)
  setCurrentJobId(job_id)

  // 3. Open WebSocket to /ws/translate/{job_id}
  const ws = await createCompareWebSocket(job_id)
  wsRef.current = ws

  // 4. Set timeout per model (120s)
  const timeouts: Record<string, NodeJS.Timeout> = {}

  ws.onmessage = (e) => {
    const event = JSON.parse(e.data)

    if (event.event === 'stage1_token') {
      appendModelToken(event.model, event.token)
      // Reset timeout for this model
      clearTimeout(timeouts[event.model])
      timeouts[event.model] = setTimeout(() => setModelError(event.model, 'timed out'), 120_000)
    }
    else if (event.event === 'stage1_complete') {
      clearTimeout(timeouts[event.model])
      setModelComplete(event.model, event.output)
    }
    else if (event.event === 'model_error') {
      clearTimeout(timeouts[event.model])
      setModelError(event.model, event.detail)
    }
    else if (event.event === 'consensus_complete') {
      setConsensus(event.output)
      // Close WS — we have what we need
      ws.close()
      setIsComparing(false)
    }
    else if (event.event === 'pipeline_error') {
      ws.close()
      setIsComparing(false)
    }
  }

  ws.onerror = () => { setIsComparing(false) }
  ws.onclose = () => { setIsComparing(false) }
}

// Cleanup on unmount:
useEffect(() => () => wsRef.current?.close(), [])
```

**MODEL_CONFIG mapping** (use in ModelPanel to get displayName and accentColor):
```typescript
export const MODEL_CONFIG = {
  gemma:    { displayName: 'Gemma 3 27B',    accentColor: 'blue'    as const },
  deepseek: { displayName: 'DeepSeek R1 32B', accentColor: 'emerald' as const },
  qwen32b:  { displayName: 'Qwen 2.5 32B',   accentColor: 'amber'   as const },
} as const
```

### Compare button state rules

| Condition | Button state |
|-----------|-------------|
| `inputText.trim() === ''` | disabled |
| All 3 models offline | disabled + tooltip "Start inference servers to enable comparison" |
| `isComparing` | disabled + spinner + text "Translating…" |
| Otherwise | enabled, text "比較する" |

**Anti-patterns:**
- Do NOT start a WebSocket without a `job_id`
- Do NOT forget to call `ws.close()` in the cleanup effect
- Do NOT show mock/demo output

---

## Phase 5 — Sub-Tab 2: Live View

**Files to create:**
- CREATE `app/frontend/src/hooks/useModelPolling.ts`
- CREATE `app/frontend/src/components/comparison/LiveModelCard.tsx`
- CREATE `app/frontend/src/components/comparison/LiveViewTab.tsx`

### 5a. `useModelPolling.ts`

Polls `/api/v1/models` and `/api/v1/training/runs` every 10 seconds when `active` is true.
Stop polling when `active` becomes false (cleanup function in useEffect).

```typescript
// Returns { liveStatuses, isLoading, error } for the 3 Stage-1 models
export function useModelPolling(active: boolean): {
  liveStatuses: Record<'gemma' | 'deepseek' | 'qwen32b', ModelLiveStatus>
  isLoading: boolean
}
```

Mapping from `RunInfo.run_name` → model key:
- `run_name` contains "Qwen2.5-32B" → key `qwen32b`
- `run_name` contains "gemma" (case-insensitive) → key `gemma`
- `run_name` contains "DeepSeek" → key `deepseek`

Use the `RunInfo` fields from Phase 0 (`status === 'training'` for isTraining, `current_step / max_steps` for progress).

### 5b. `LiveModelCard.tsx`

Props:
```typescript
interface LiveModelCardProps {
  modelKey: 'gemma' | 'deepseek' | 'qwen32b'
  displayName: string
  status: ModelLiveStatus
  onNavigateToMonitor: () => void
}
```

Layout (see `comparison-tab-prompt.md` §"Card-Aufbau"):
- Header: model name + status badge (Training/Online/Idle/Offline)
- Training section (shown if `status.isTraining`): progress bar, loss, ETA, epoch, "View in Monitor →" link
- Inference section (shown if `status.inferenceOnline`): "Ready for translation" badge, endpoint URL, loaded model
- Empty state (neither training nor inference): dimmed card, "Not active" text, two buttons

**Navigation to Monitor tab:** Use `useNavigate` from `react-router-dom` and navigate to `/monitor`.

```typescript
import { useNavigate } from 'react-router-dom'
const navigate = useNavigate()
// In "View in Monitor →" or "Start Training":
<button onClick={() => navigate('/monitor')}>View in Monitor →</button>
```

### 5c. `LiveViewTab.tsx`

Composes three `LiveModelCard` components. Uses `useModelPolling(active)` where `active` is whether this sub-tab is currently shown.

---

## Phase 6 — Wire up `Comparison.tsx`

**File to modify:** `app/frontend/src/views/Comparison.tsx`

Replace the entire placeholder content. The component:
1. Reads `activeSubTab` from Zustand store
2. Renders `ComparisonPills` at top
3. Fades between sub-tabs with `transition-opacity duration-200`
4. Renders `ModelComparisonTab` or `LiveViewTab` depending on active sub-tab
5. On mount: fetch model endpoints once (to initialize online/offline status for button state)

```typescript
export function Comparison() {
  const { comparison, setComparisonSubTab } = useStore(s => ({
    comparison: s.comparison,
    setComparisonSubTab: s.setComparisonSubTab,
  }))

  return (
    <div className="p-6 space-y-4 overflow-y-auto h-full">
      <ComparisonPills
        active={comparison.activeSubTab}
        onSelect={setComparisonSubTab}
      />
      <div className="transition-opacity duration-200">
        {comparison.activeSubTab === 'comparison'
          ? <ModelComparisonTab />
          : <LiveViewTab active={true} />
        }
      </div>
    </div>
  )
}
```

**Responsive layout** (prompt §"Responsive Verhalten"):
- 3-column grid for panels: `grid grid-cols-3 gap-4`
- Below 1200px: `grid-cols-1` — use `xl:grid-cols-3 grid-cols-1` (Tailwind breakpoint `xl` = 1280px, close enough)

---

## Phase 7 — Verification + Version Bump

### 7a. TypeScript build check
```bash
cd app/frontend
npm run build
```
Must complete with zero TypeScript errors. Fix any type errors before continuing.

### 7b. Lint check
```bash
npm run lint
```
Must produce zero ESLint errors.

### 7c. Smoke test checklist

1. **Navigate to Comparison tab** → pill navigation visible, defaults to Sub-Tab 1 (比較)
2. **Sub-Tab 1:** Textarea is visible. Button shows `比較する` and is **disabled** (all models offline). 3 model panels show "Model offline". No mock text anywhere.
3. **Sub-Tab 2 (生):** Switch pill → 3 cards show "Not active" / "Offline" state. "Start Training" and "Start Inference" buttons are present.
4. **No regressions:** Switch to Translator, Editor, Monitor tabs → all still work normally.

### 7d. Version bump
```bash
python scripts/bump_version.py minor
```
This bumps 0.9.10 → 1.0.0 and pushes to GitHub. Only run after Steps 7a–7c pass cleanly.

---

## Summary Checklist

- [ ] Phase 1: `routers/compare.py` + `routers/models.py` + registered in `main.py`
- [ ] Phase 2: `src/types/comparison.ts` + `src/api/compare.ts` + Zustand store extended
- [ ] Phase 3: `ComparisonPills`, `ModelPanel`, `ConsensusPanel` components
- [ ] Phase 4: `ModelComparisonTab` with WebSocket streaming (stage1_token, consensus_complete)
- [ ] Phase 5: `useModelPolling` hook + `LiveModelCard` + `LiveViewTab`
- [ ] Phase 6: `Comparison.tsx` wired up with pill nav + sub-tab routing
- [ ] Phase 7: build ✓ · lint ✓ · smoke test ✓ · version bumped to 1.0.0

---

## Anti-Pattern Guards

| Anti-pattern | Where it bites | Prevention |
|---|---|---|
| Hardcoded port numbers | `api/compare.ts` | Always use `getBaseUrl()` |
| Redux imports | `store.ts` | Project uses Zustand — no `@reduxjs/toolkit` |
| `httpx.Client` (sync) | `routers/models.py` | Use `httpx.AsyncClient` |
| Mock/demo text in outputs | `ModelPanel`, `ConsensusPanel` | Leave outputs empty until actual WS data arrives |
| Opening WS before getting job_id | `ModelComparisonTab` | `await startCompare(text)` first, then `createCompareWebSocket(job_id)` |
| Forgetting WS cleanup | `ModelComparisonTab` | `useEffect(() => () => wsRef.current?.close(), [])` |
| `npm run build` before Phase 7 check | All phases | Run `npx tsc --noEmit` after each phase to catch type errors early |
