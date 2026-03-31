# Hime — Training Improvements Implementation Plan
Generated: 2026-03-29

## Phase 0: Discovery Summary (Completed)

### Confirmed APIs & File Locations

| File | Key Facts |
|---|---|
| `scripts/train_hime.py:269` | `SFTTrainer(..., callbacks=[SaveCheckpointCallback()])` |
| `scripts/train_hime.py:44` | `EPOCHS = 3`, `EVAL_STEPS = 100`, `LOGGING_STEPS = 10` |
| `scripts/train_hime.py:410` | CLI: only `--log-file` and `--resume_from_checkpoint` |
| `scripts/train_generic.py:262` | Same SFTTrainer pattern |
| `scripts/train_generic.py:316` | CLI: `--model`, `--epochs`, `--run-name`, `--resume`, `--log-file`, etc. |
| `app/backend/app/services/training_monitor.py:112` | `LossPoint(step, epoch, train_loss, eval_loss, learning_rate)` — **grad_norm missing** |
| `app/backend/app/services/training_monitor.py:445` | `get_loss_history()` already merges by step |
| `app/backend/app/services/training_monitor.py:638` | SSE sends `loss_history_batch` (last 200) + `status` every 30s |
| `app/backend/app/routers/training.py:108` | `StartTrainingRequest(model_name, epochs, model_key, resume_checkpoint)` |
| `app/backend/app/services/training_runner.py:97` | Builds cmd with `--model`, `--epochs`, `--run-name` |
| `app/frontend/src/views/TrainingMonitor.tsx:1028` | `ComposedChart` with `train_loss` + `eval_loss` lines |
| `app/frontend/src/views/TrainingMonitor.tsx:339` | SSE via `esRef.current`, proper cleanup at line 441 |
| `app/frontend/src/views/TrainingMonitor.tsx:500` | Memory cap: heap > 500MB → trim arrays |
| `app/frontend/src/api/training.ts:130` | `createTrainingEventSource(run?)` |

### Allowed APIs
- `transformers.TrainerCallback` with hooks: `on_log()`, `on_evaluate()`, `on_train_end()`
- `control.should_training_stop = True` to signal stop
- `state.log_history`, `state.global_step`, `state.best_metric` in callbacks
- `SFTTrainer(..., callbacks=[...])` — extend existing callbacks list
- FastAPI `APIRouter` with `@router.get()` / `@router.put()` — match pattern in `training.py`
- Recharts `ComposedChart` (already used), `ReferenceLine` for epoch markers, `YAxis yAxisId` for dual axes
- Zustand `useStore` — TrainingMonitor uses local state, not Zustand

### Anti-Patterns to Avoid
- Do NOT use `EarlyStoppingCallback` from `transformers` — it requires `load_best_model_at_end=True` and has quirks; build custom
- Do NOT downsample eval_loss points (there are few; only downsample train_loss)
- Do NOT add a second `EventSource` — use the existing `esRef` pattern
- Do NOT read config file in the callback — read it in the training script and pass via constructor args
- Do NOT import from `app/` in `scripts/` — they're separate environments

---

## Phase 1: SmartStoppingCallback (Python)

**Goal:** Create `scripts/callbacks/smart_stopping.py` with two-mode stopping logic.

### Files to Create/Edit
- **Create:** `scripts/callbacks/__init__.py` (empty)
- **Create:** `scripts/callbacks/smart_stopping.py`

### Implementation

**`scripts/callbacks/smart_stopping.py`:**
```python
from transformers import TrainerCallback, TrainerControl, TrainerState, TrainingArguments
import logging

logger = logging.getLogger(__name__)

class SmartStoppingCallback(TrainerCallback):
    """
    Two modes, both configurable:

    Mode 1 — Hard Threshold:
      Stop when `target_loss_metric` <= target_loss for N consecutive checks.
      Checked in on_log() (train_loss) or on_evaluate() (eval_loss).

    Mode 2 — Patience (Early Stopping):
      Stop when `patience_metric` has not improved by at least `min_delta`
      for `patience` consecutive evaluations.
      Checked in on_evaluate().

    Both modes can be active simultaneously — first to trigger wins.
    """

    def __init__(
        self,
        target_loss: float | None = None,
        target_loss_metric: str = "loss",          # "loss" = training loss, "eval_loss" = eval
        target_confirmations: int = 3,
        patience: int | None = None,
        patience_metric: str = "eval_loss",
        min_delta: float = 0.001,
        min_steps: int = 0,
    ):
        self.target_loss = target_loss
        self.target_loss_metric = target_loss_metric
        self.target_confirmations = target_confirmations
        self.patience = patience
        self.patience_metric = patience_metric
        self.min_delta = min_delta
        self.min_steps = min_steps

        # Internal state
        self._target_hit_count = 0
        self._best_metric: float | None = None
        self._patience_counter = 0
        self._stop_reason: str | None = None

    def on_log(self, args: TrainingArguments, state: TrainerState, control: TrainerControl, logs=None, **kwargs):
        if logs is None or state.global_step < self.min_steps:
            return
        if self.target_loss is None or self.target_loss_metric != "loss":
            return

        current = logs.get("loss")
        if current is None:
            return

        if current <= self.target_loss:
            self._target_hit_count += 1
            logger.info(
                f"[SMART STOP] Train loss {current:.4f} <= target {self.target_loss} "
                f"({self._target_hit_count}/{self.target_confirmations})"
            )
            if self._target_hit_count >= self.target_confirmations:
                self._stop_reason = (
                    f"train_loss {current:.4f} <= target {self.target_loss} "
                    f"for {self.target_confirmations} consecutive checks"
                )
                control.should_training_stop = True
        else:
            self._target_hit_count = 0

    def on_evaluate(self, args: TrainingArguments, state: TrainerState, control: TrainerControl, metrics=None, **kwargs):
        if metrics is None or state.global_step < self.min_steps:
            return

        # --- Hard threshold on eval_loss ---
        if self.target_loss is not None and self.target_loss_metric == "eval_loss":
            current = metrics.get("eval_loss")
            if current is not None and current <= self.target_loss:
                self._target_hit_count += 1
                logger.info(
                    f"[SMART STOP] Eval loss {current:.4f} <= target {self.target_loss} "
                    f"({self._target_hit_count}/{self.target_confirmations})"
                )
                if self._target_hit_count >= self.target_confirmations:
                    self._stop_reason = (
                        f"eval_loss {current:.4f} <= target {self.target_loss} "
                        f"for {self.target_confirmations} consecutive checks"
                    )
                    control.should_training_stop = True
                    return
            elif current is not None:
                self._target_hit_count = 0

        # --- Patience mode ---
        if self.patience is None:
            return

        current = metrics.get(self.patience_metric)
        if current is None:
            return

        if self._best_metric is None or current < self._best_metric - self.min_delta:
            self._best_metric = current
            self._patience_counter = 0
            logger.info(f"[SMART STOP] New best {self.patience_metric}: {current:.4f}")
        else:
            self._patience_counter += 1
            logger.info(
                f"[SMART STOP] No improvement in {self.patience_metric}: "
                f"{current:.4f} (best: {self._best_metric:.4f}, "
                f"patience: {self._patience_counter}/{self.patience})"
            )
            if self._patience_counter >= self.patience:
                self._stop_reason = (
                    f"{self.patience_metric} did not improve by {self.min_delta} "
                    f"for {self.patience} evaluations. Best: {self._best_metric:.4f}"
                )
                control.should_training_stop = True

    def on_train_end(self, args: TrainingArguments, state: TrainerState, control: TrainerControl, **kwargs):
        if self._stop_reason:
            logger.info(f"[SMART STOP] Training stopped early: {self._stop_reason}")
        else:
            logger.info("[SMART STOP] Training completed all epochs (no early stop triggered)")
```

### Verification
- `grep -n "SmartStoppingCallback" scripts/callbacks/smart_stopping.py` → finds class
- `python -c "from scripts.callbacks.smart_stopping import SmartStoppingCallback; print('OK')"` → no import errors

---

## Phase 2: Training Script Integration

**Goal:** Add CLI args and config file support to both training scripts.

### Files to Edit
- `scripts/train_hime.py`
- `scripts/train_generic.py`
- **Create:** `scripts/training_config.json` (default config)

### training_config.json (default)
```json
{
  "stop_mode": "none",
  "target_loss": null,
  "target_loss_metric": "loss",
  "target_confirmations": 3,
  "patience": null,
  "patience_metric": "eval_loss",
  "min_delta": 0.001,
  "min_steps": 0,
  "max_epochs": 3
}
```

### Changes to `scripts/train_hime.py`

**1. Add imports at top (after existing imports):**
```python
import json
import sys
from pathlib import Path
# Add scripts dir to path for callbacks
sys.path.insert(0, str(Path(__file__).parent))
from callbacks.smart_stopping import SmartStoppingCallback
```

**2. Add config loader function (before `train()`):**
```python
_CONFIG_PATH = Path(__file__).parent / "training_config.json"

def _load_stop_config(cli_args) -> dict:
    """Load stop config from JSON file, then override with CLI args."""
    defaults = {
        "stop_mode": "none",
        "target_loss": None,
        "target_loss_metric": "loss",
        "target_confirmations": 3,
        "patience": None,
        "patience_metric": "eval_loss",
        "min_delta": 0.001,
        "min_steps": 0,
        "max_epochs": EPOCHS,
    }
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            file_config = json.load(f)
        defaults.update({k: v for k, v in file_config.items() if v is not None})

    # CLI args override config file (only if explicitly provided)
    if getattr(cli_args, "target_loss", None) is not None:
        defaults["target_loss"] = cli_args.target_loss
        defaults["stop_mode"] = "threshold"
    if getattr(cli_args, "patience", None) is not None:
        defaults["patience"] = cli_args.patience
        defaults["stop_mode"] = "patience"
    if getattr(cli_args, "min_delta", None) is not None:
        defaults["min_delta"] = cli_args.min_delta
    if getattr(cli_args, "min_steps", None) is not None:
        defaults["min_steps"] = cli_args.min_steps
    if getattr(cli_args, "max_epochs", None) is not None:
        defaults["max_epochs"] = cli_args.max_epochs

    return defaults
```

**3. Update `train()` function signature and internals:**
- Accept `stop_config: dict` parameter
- Set `num_train_epochs = stop_config["max_epochs"]` in TrainingArguments
- Build callbacks list:
```python
callbacks = [SaveCheckpointCallback()]
mode = stop_config.get("stop_mode", "none")
if mode != "none" and (stop_config.get("target_loss") is not None or stop_config.get("patience") is not None):
    callbacks.append(SmartStoppingCallback(
        target_loss=stop_config.get("target_loss"),
        target_loss_metric=stop_config.get("target_loss_metric", "loss"),
        target_confirmations=stop_config.get("target_confirmations", 3),
        patience=stop_config.get("patience"),
        patience_metric=stop_config.get("patience_metric", "eval_loss"),
        min_delta=stop_config.get("min_delta", 0.001),
        min_steps=stop_config.get("min_steps", 0),
    ))
```

**4. Add CLI args to `_parser` (lines 410-413 area):**
```python
_parser.add_argument("--target-loss",   type=float, default=None, help="Stop when loss <= this value")
_parser.add_argument("--patience",      type=int,   default=None, help="Evals without improvement before stopping")
_parser.add_argument("--min-delta",     type=float, default=None, help="Min improvement for patience mode (default: 0.001)")
_parser.add_argument("--min-steps",     type=int,   default=None, help="Don't stop before this step (default: 0)")
_parser.add_argument("--max-epochs",    type=int,   default=None, help="Max epochs (cap for smart stopping)")
```

**5. Update `main()` to pass stop_config to `train()`:**
```python
stop_config = _load_stop_config(_args)
train(stop_config=stop_config, ...)
```

### Same Changes to `scripts/train_generic.py`
- Same import, same `_load_stop_config()`, same CLI args, same callback injection
- Note: `train_generic.py` already has `--epochs` arg → `max_epochs` CLI arg can override it

### Verification Checklist
- [ ] `python scripts/train_hime.py --help` shows `--target-loss`, `--patience`, `--min-delta`, `--min-steps`, `--max-epochs`
- [ ] `python scripts/train_generic.py --help` shows same new args
- [ ] `scripts/training_config.json` exists with defaults
- [ ] `python -c "from scripts.callbacks.smart_stopping import SmartStoppingCallback"` succeeds

---

## Phase 3: Backend API Extensions

**Goal:** Add `grad_norm` to LossPoint, add `stop_config` to status, add config CRUD endpoints.

### Files to Edit
- `app/backend/app/services/training_monitor.py`
- `app/backend/app/routers/training.py`

### 3A: Extend LossPoint in `training_monitor.py`

**At line 112-117, add `grad_norm` field:**
```python
class LossPoint(BaseModel):
    step: int
    epoch: float | None = None
    train_loss: float | None = None
    eval_loss: float | None = None
    learning_rate: float | None = None
    grad_norm: float | None = None  # ADD THIS
```

**In `get_loss_history()` at the training entry parse block (~line 465):**
```python
if "loss" in entry:
    points[step].train_loss = entry["loss"]
    points[step].learning_rate = entry.get("learning_rate")
    points[step].grad_norm = entry.get("grad_norm")  # ADD THIS
```

### 3B: Add stop_config to TrainingStatus

**Add new model before or near `TrainingStatus`:**
```python
class StopConfigStatus(BaseModel):
    mode: str = "none"                  # "none" | "threshold" | "patience" | "both"
    target_loss: float | None = None
    patience: int | None = None
    patience_remaining: int | None = None   # filled by callback state if accessible
    target_reached_count: int = 0
```

**Extend `TrainingStatus` with optional field:**
```python
class TrainingStatus(BaseModel):
    # ... existing fields ...
    stop_config: StopConfigStatus | None = None  # ADD
```

**In `get_training_status()`, after building the status object, read config file and attach:**
```python
config_path = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "training_config.json"
# Adjust path to reach scripts/training_config.json from services/
if config_path.exists():
    with open(config_path) as f:
        cfg = json.load(f)
    status.stop_config = StopConfigStatus(
        mode=cfg.get("stop_mode", "none"),
        target_loss=cfg.get("target_loss"),
        patience=cfg.get("patience"),
    )
```
Note: Find the correct relative path by reading where `training_monitor.py` is located vs. `scripts/`.

### 3C: Config CRUD endpoints in `training.py`

**Add near existing endpoint definitions:**
```python
from pathlib import Path
import json

TRAINING_CONFIG_PATH = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "training_config.json"

class TrainingConfig(BaseModel):
    stop_mode: str = "none"
    target_loss: float | None = None
    target_loss_metric: str = "loss"
    target_confirmations: int = 3
    patience: int | None = None
    patience_metric: str = "eval_loss"
    min_delta: float = 0.001
    min_steps: int = 0
    max_epochs: int = 3

@router.get("/config", response_model=TrainingConfig)
async def get_training_config():
    if TRAINING_CONFIG_PATH.exists():
        with open(TRAINING_CONFIG_PATH) as f:
            return TrainingConfig(**json.load(f))
    return TrainingConfig()

@router.put("/config", response_model=TrainingConfig)
async def update_training_config(config: TrainingConfig):
    # Validate
    if config.target_loss is not None and config.target_loss <= 0:
        raise HTTPException(400, "target_loss must be > 0")
    if config.patience is not None and config.patience <= 0:
        raise HTTPException(400, "patience must be > 0")
    if config.max_epochs <= 0:
        raise HTTPException(400, "max_epochs must be > 0")
    TRAINING_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRAINING_CONFIG_PATH, "w") as f:
        json.dump(config.model_dump(), f, indent=2)
    return config
```

### 3D: Pass stop config when starting training in `training_runner.py`

**In `start_training()`, after building the base `cmd` list, append stop config args:**
```python
config_path = Path(__file__).parent.parent.parent.parent.parent / "scripts" / "training_config.json"
if config_path.exists():
    with open(config_path) as f:
        cfg = json.load(f)
    if cfg.get("target_loss") is not None:
        cmd += ["--target-loss", str(cfg["target_loss"])]
    if cfg.get("patience") is not None:
        cmd += ["--patience", str(cfg["patience"])]
    if cfg.get("min_delta") is not None:
        cmd += ["--min-delta", str(cfg["min_delta"])]
    if cfg.get("min_steps"):
        cmd += ["--min-steps", str(cfg["min_steps"])]
    if cfg.get("max_epochs") is not None:
        cmd += ["--max-epochs", str(cfg["max_epochs"])]
```
Note: This applies to BOTH the model_key branch (line 97) and legacy branch (line 119).

### Verification Checklist
- [ ] `GET /api/v1/training/config` returns 200 with defaults
- [ ] `PUT /api/v1/training/config` with `{"stop_mode":"patience","patience":5}` writes file + returns 200
- [ ] `GET /api/v1/training/loss-history?run=...` response includes `grad_norm` field in JSON
- [ ] `GET /api/v1/training/status?run=...` response includes `stop_config` object

---

## Phase 4: Frontend Chart Enhancements

**Goal:** Add learning_rate secondary axis, metric toggles, epoch markers, improved tooltip, larger eval_loss dots.

### Files to Edit
- `app/frontend/src/views/TrainingMonitor.tsx`
- `app/frontend/src/api/training.ts` (add config fetch/update functions)

### 4A: Update TypeScript types

**In `training.ts` (or types file), extend `LossPoint`:**
```typescript
export interface LossPoint {
  step: number
  epoch?: number | null
  train_loss?: number | null
  eval_loss?: number | null
  learning_rate?: number | null
  grad_norm?: number | null  // ADD
}
```

**Add config API functions to `training.ts`:**
```typescript
export interface TrainingConfig {
  stop_mode: 'none' | 'threshold' | 'patience' | 'both'
  target_loss: number | null
  target_loss_metric: string
  target_confirmations: number
  patience: number | null
  patience_metric: string
  min_delta: number
  min_steps: number
  max_epochs: number
}

export async function getTrainingConfig(): Promise<TrainingConfig> {
  const baseUrl = await getBaseUrl()
  const res = await fetch(`${baseUrl}/api/v1/training/config`)
  if (!res.ok) throw new Error('Failed to fetch training config')
  return res.json()
}

export async function updateTrainingConfig(config: TrainingConfig): Promise<TrainingConfig> {
  const baseUrl = await getBaseUrl()
  const res = await fetch(`${baseUrl}/api/v1/training/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!res.ok) throw new Error('Failed to update training config')
  return res.json()
}
```

### 4B: Add metric toggle state to TrainingMonitor.tsx

**Near existing useState declarations, add:**
```typescript
const [visibleMetrics, setVisibleMetrics] = useState({
  trainLoss: true,
  evalLoss: true,
  learningRate: false,
  gradNorm: false,
})
```

### 4C: Update Loss Chart (around line 1028)

**Replace current `ComposedChart` with enhanced version:**

Key changes:
1. Add `YAxis yAxisId="lr"` (right side) for learning_rate
2. Add `ReferenceLine` for each epoch boundary (vertical dashed)
3. Conditionally render lines based on `visibleMetrics`
4. Make eval_loss use `dot={{ r: 4 }}` (larger) vs train_loss with no dots
5. Add secondary downsampling: train_loss only (keep all eval_loss points)

**Epoch boundary detection (add to `useMemo` for chart data):**
```typescript
const epochBoundaries = useMemo(() => {
  const boundaries: number[] = []
  let lastEpoch = -1
  for (const p of chartData) {
    const e = Math.floor(p.epoch ?? -1)
    if (e > lastEpoch && e >= 0) {
      lastEpoch = e
      if (e > 0) boundaries.push(p.step) // Don't mark epoch 0
    }
  }
  return boundaries
}, [chartData])
```

**Toggle checkboxes (add above chart):**
```tsx
<div style={{ display: 'flex', gap: '12px', marginBottom: '8px', fontSize: '12px' }}>
  {[
    { key: 'trainLoss', label: 'Train Loss', color: '#7C6FCD' },
    { key: 'evalLoss', label: 'Eval Loss', color: '#F0997B' },
    { key: 'learningRate', label: 'Learning Rate', color: '#6b7280' },
    { key: 'gradNorm', label: 'Grad Norm', color: '#f59e0b' },
  ].map(({ key, label, color }) => (
    <label key={key} style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer', color: '#a1a1aa' }}>
      <input
        type="checkbox"
        checked={visibleMetrics[key as keyof typeof visibleMetrics]}
        onChange={e => setVisibleMetrics(prev => ({ ...prev, [key]: e.target.checked }))}
        style={{ accentColor: color }}
      />
      <span style={{ color }}>{label}</span>
    </label>
  ))}
</div>
```

**Updated ComposedChart:**
```tsx
<ComposedChart data={chartData} margin={LOSS_CHART_MARGIN}>
  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
  <XAxis dataKey="step" tick={AXIS_TICK_LG} tickFormatter={fmtStep} />
  <YAxis yAxisId="left" tick={AXIS_TICK_LG} tickFormatter={fmtLossAxis} width={48} />
  {(visibleMetrics.learningRate || visibleMetrics.gradNorm) && (
    <YAxis yAxisId="right" orientation="right" tick={AXIS_TICK_LG} width={60} tickFormatter={(v) => v.toExponential(1)} />
  )}
  <Tooltip contentStyle={...} formatter={(value, name) => [
    typeof value === 'number' ? value.toFixed(4) : value, name
  ]} labelFormatter={fmtLossLabel} />

  {epochBoundaries.map(step => (
    <ReferenceLine key={step} x={step} yAxisId="left" stroke="#3f3f46" strokeDasharray="4 2"
      label={{ value: `E${Math.floor(...)}`, fill: '#71717a', fontSize: 10 }} />
  ))}

  {visibleMetrics.trainLoss && (
    <Line yAxisId="left" type="monotone" dataKey="train_loss" name="Train Loss"
      stroke="#7C6FCD" dot={false} isAnimationActive={false} connectNulls={false} />
  )}
  {visibleMetrics.evalLoss && (
    <Line yAxisId="left" type="monotone" dataKey="eval_loss" name="Eval Loss"
      stroke="#F0997B" dot={{ r: 4, fill: '#F0997B' }} isAnimationActive={false} connectNulls={false} />
  )}
  {visibleMetrics.learningRate && (
    <Line yAxisId="right" type="monotone" dataKey="learning_rate" name="Learning Rate"
      stroke="#6b7280" dot={false} strokeWidth={1} isAnimationActive={false} connectNulls={false} />
  )}
  {visibleMetrics.gradNorm && (
    <Line yAxisId="right" type="monotone" dataKey="grad_norm" name="Grad Norm"
      stroke="#f59e0b" dot={false} strokeWidth={1} isAnimationActive={false} connectNulls={false} />
  )}
</ComposedChart>
```

### Pre-condition: Verify Phase 6 6D is applied first
Before implementing the visual enhancements, the `chartData` useMemo MUST already be fixed (Phase 6D) so that eval_loss points are not discarded by the downsampler. Without that fix, the toggle checkboxes and larger dots would show an eval_loss line that appears nearly empty.

### Verification Checklist
- [ ] Toggle checkboxes appear above chart
- [ ] Learning Rate toggle adds right Y axis
- [ ] Vertical dashed lines appear at epoch boundaries
- [ ] Eval loss shows larger dots (r=4) at every eval step — NOT sparse or gapped
- [ ] Train Loss downsampled to ≤200 points; eval_loss points ALL preserved (count them: should be ~total_steps/100)
- [ ] Tooltip shows all visible metrics on hover

---

## Phase 5: Frontend Training Config Panel

**Goal:** Add gear icon → settings modal/slide-in with stop condition controls, wired to PUT /api/v1/training/config.

### Files to Edit
- `app/frontend/src/views/TrainingMonitor.tsx`

### 5A: Add config panel state

```typescript
const [configPanelOpen, setConfigPanelOpen] = useState(false)
const [trainingConfig, setTrainingConfig] = useState<TrainingConfig | null>(null)
const [configDraft, setConfigDraft] = useState<TrainingConfig | null>(null)
const [configSaving, setConfigSaving] = useState(false)
```

**Fetch config on mount (add to existing useEffect or new one):**
```typescript
useEffect(() => {
  getTrainingConfig().then(setTrainingConfig).catch(console.error)
}, [])
```

### 5B: Gear icon button in monitor header

**Find the monitor header section and add:**
```tsx
<button
  onClick={() => {
    setConfigDraft(trainingConfig ? { ...trainingConfig } : null)
    setConfigPanelOpen(true)
  }}
  title="Training Settings"
  style={{ /* gear icon button styles, dark theme */ }}
>
  ⚙
</button>
```

### 5C: Smart Stop status display with live counters

**To show "Patience 3/5 | Target 0/3 confirmations", the callback must write its state to a file.**

#### 5C-i: SmartStoppingCallback — write state file (add to `scripts/callbacks/smart_stopping.py`)

Add an optional `state_file` parameter. After every counter update in `on_log()` and `on_evaluate()`, write JSON to that file:

```python
def __init__(self, ..., state_file: str | None = None):
    ...
    self._state_file = Path(state_file) if state_file else None

def _write_state(self):
    if self._state_file is None:
        return
    try:
        import json
        state = {
            "patience_counter": self._patience_counter,
            "patience_total": self.patience,
            "target_hit_count": self._target_hit_count,
            "target_confirmations": self.target_confirmations,
            "best_metric": self._best_metric,
            "stop_reason": self._stop_reason,
        }
        self._state_file.write_text(json.dumps(state))
    except Exception:
        pass  # never crash training over a status file
```

Call `self._write_state()` at the end of `on_log()` and `on_evaluate()`.

#### 5C-ii: Pass state_file path in training scripts

When building the `SmartStoppingCallback` in both `train_hime.py` and `train_generic.py`, pass a state file path in the output directory:

```python
state_file = str(Path(output_dir) / "smart_stop_state.json")
callbacks.append(SmartStoppingCallback(
    ...,
    state_file=state_file,
))
```

The `output_dir` is already known at that point (where trainer_state.json is saved).

#### 5C-iii: Backend reads state file in `get_training_status()`

In `training_monitor.py`, after populating `stop_config` from `training_config.json`, also check for `smart_stop_state.json` in the latest checkpoint's run directory:

```python
# Find smart_stop_state.json alongside trainer_state.json
state_path = latest_checkpoint_dir / "smart_stop_state.json"
if state_path.exists():
    with open(state_path) as f:
        ss = json.load(f)
    status.stop_config = StopConfigStatus(
        mode=cfg.get("stop_mode", "none"),
        target_loss=cfg.get("target_loss"),
        patience=cfg.get("patience"),
        patience_remaining=max(0, (cfg.get("patience") or 0) - ss.get("patience_counter", 0)),
        target_reached_count=ss.get("target_hit_count", 0),
    )
```

#### 5C-iv: Frontend status display (reads from `status.stop_config`)

**Replace the static config display with one that reads runtime state from `status.stop_config`:**

```tsx
{status?.stop_config && status.stop_config.mode !== 'none' && (
  <div className="text-xs text-zinc-500 mt-1">
    Smart Stop:{' '}
    {(status.stop_config.mode === 'patience' || status.stop_config.mode === 'both') &&
      status.stop_config.patience !== null && (
        <span>
          Patience {status.stop_config.patience_remaining ?? '?'}/{status.stop_config.patience} remaining
        </span>
      )
    }
    {(status.stop_config.mode === 'threshold' || status.stop_config.mode === 'both') &&
      status.stop_config.target_loss !== null && (
        <span>
          {status.stop_config.patience !== null ? ' | ' : ''}
          Target {status.stop_config.target_reached_count ?? 0}/{status.stop_config.target_confirmations ?? 3} confirmations
        </span>
      )
    }
  </div>
)}
```

This reads live counter data from `status.stop_config` which comes from the SSE `status` event (updated every 30s). When training is not running, falls back to showing nothing (stop_config will not have counter data).

**Fallback for when no training is running:** also show static config values from `trainingConfig` state when `status?.stop_config` is null but a mode is configured:
```tsx
{!status?.stop_config && trainingConfig && trainingConfig.stop_mode !== 'none' && (
  <div className="text-xs text-zinc-500 mt-1">
    Smart Stop configured: {trainingConfig.stop_mode}
    {trainingConfig.patience !== null ? ` | Patience: ${trainingConfig.patience}` : ''}
    {trainingConfig.target_loss !== null ? ` | Target: ${trainingConfig.target_loss}` : ''}
  </div>
)}
```

### 5D: Config panel modal/slide-in

**Add as a fixed overlay (slide-in from right):**
```tsx
{configPanelOpen && configDraft && (
  <div style={{
    position: 'fixed', top: 0, right: 0, bottom: 0, width: '360px',
    background: '#18181b', borderLeft: '1px solid #27272a',
    padding: '24px', overflowY: 'auto', zIndex: 100,
    display: 'flex', flexDirection: 'column', gap: '16px'
  }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <h3 style={{ margin: 0, color: '#e4e4e7' }}>Training Settings</h3>
      <button onClick={() => setConfigPanelOpen(false)} style={{ /* close button */ }}>✕</button>
    </div>

    {/* Stop Mode selector */}
    <label>Stop Mode</label>
    <select value={configDraft.stop_mode} onChange={e => setConfigDraft(d => ({ ...d!, stop_mode: e.target.value as any }))}>
      <option value="none">Fixed Epochs Only</option>
      <option value="threshold">Threshold Only</option>
      <option value="patience">Patience Only</option>
      <option value="both">Both</option>
    </select>

    {/* Threshold section */}
    {(configDraft.stop_mode === 'threshold' || configDraft.stop_mode === 'both') && (<>
      <label>Target Loss</label>
      <input type="number" step="0.01" value={configDraft.target_loss ?? ''} onChange={...} />
      <label>Metric</label>
      <select value={configDraft.target_loss_metric} onChange={...}>
        <option value="loss">Training Loss</option>
        <option value="eval_loss">Eval Loss</option>
      </select>
      <label>Confirmations</label>
      <input type="number" min="1" value={configDraft.target_confirmations} onChange={...} />
    </>)}

    {/* Patience section */}
    {(configDraft.stop_mode === 'patience' || configDraft.stop_mode === 'both') && (<>
      <label>Patience (evals)</label>
      <input type="number" min="1" value={configDraft.patience ?? ''} onChange={...} />
      <label>Min Delta</label>
      <input type="number" step="0.0001" value={configDraft.min_delta} onChange={...} />
    </>)}

    {/* General */}
    <label>Max Epochs</label>
    <input type="number" min="1" value={configDraft.max_epochs} onChange={...} />
    <label>Min Steps (don't stop before)</label>
    <input type="number" min="0" value={configDraft.min_steps} onChange={...} />

    {/* Training active warning */}
    {status?.is_training && (
      <p style={{ color: '#f59e0b', fontSize: '12px' }}>
        ⚠ Training is running — changes apply to the next training run.
      </p>
    )}

    <div style={{ display: 'flex', gap: '8px', marginTop: 'auto' }}>
      <button
        disabled={configSaving}
        onClick={async () => {
          setConfigSaving(true)
          try {
            const saved = await updateTrainingConfig(configDraft!)
            setTrainingConfig(saved)
            setConfigPanelOpen(false)
          } finally {
            setConfigSaving(false)
          }
        }}
      >
        {configSaving ? 'Saving...' : 'Save'}
      </button>
      <button onClick={() => setConfigDraft({ ...DEFAULT_TRAINING_CONFIG })}>Reset to Defaults</button>
    </div>
  </div>
)}
```

### Verification Checklist
- [ ] Gear icon button visible in monitor header
- [ ] Panel slides in from right, all fields editable
- [ ] Save calls PUT /api/v1/training/config, panel closes
- [ ] Smart stop status text appears in monitor when mode != 'none'
- [ ] Training-active warning shows when training is running

---

## Phase 6: Memory Leak — Real Root Cause Analysis & Fix

**Goal:** Fix the confirmed WebView2 memory growth. This is NOT an audit of caps (those are correct). The actual leak is in the React render cycle causing continuous recharts SVG DOM churn.

### 6A: Confirmed Root Cause — Recharts Re-renders Every Second

**Traced code path (do not assume — read the code):**

1. **Line 466:** `useInterval(() => setSecondsAgo(...), 1000, isWindowVisible)` — fires every second
2. **Line 472:** `useInterval(() => setHwSecondsAgo(...), 1000, isWindowVisible)` — fires every second
3. Two `setState` calls/second → `TrainingMonitor` re-renders up to 2× per second
4. On each re-render, the JSX inside `<ComposedChart>` is re-evaluated and produces **new child element objects** (inline `<CartesianGrid>`, `<XAxis>`, `<YAxis>`, `<Tooltip>`, `<Line>`, `<Line>`)
5. `ComposedChart` is recharts' `PureComponent`. Its `shouldComponentUpdate` compares `this.props.children !== nextProps.children` — they're **always unequal** because JSX creates new objects every render
6. Recharts re-renders its entire SVG tree ~2×/second, creating and removing SVG nodes
7. WebView2's GC is slower than desktop Chrome — detached SVG nodes accumulate
8. **Result: 120+ recharts re-renders/minute → continuous SVG DOM leak**

**What is NOT the cause (verified by reading the actual code):**
- Array caps: `lossHistory` uses `.slice(-500)` on both initial load (line 373) and SSE batch (line 403) ✓
- `hwHistory`: `[...prev.slice(-59), s]` = max 60 entries (line 488) ✓
- `logLines`: only loaded on demand (20 lines), never stream-accumulated ✓
- `backendLogLines`: only loaded on manual refresh, sliced to 50 ✓
- SSE cleanup: uses `aborted` closure pattern correctly, closes on every dependency change ✓
- SSE reconnect: closes old ES before creating new one (line 344-345), async race handled by `aborted` flag ✓
- `loss_history_batch` listener: not explicitly removed, but EventSource is `.close()`d → no more events fire → listener is GC'd with the EventSource ✓
- `isAnimationActive={false}`: set on all Line components in both charts ✓
- Route-based mounting: `/monitor` route only, TrainingMonitor unmounts on navigation ✓

### 6B: Fix — Extract Charts to `memo()`'d Components

**Why this works:** `React.memo` does shallow comparison of props. When `chartData` is the same reference (unchanged by `useMemo`), `LossChart` will NOT re-render even when the parent re-renders due to `setSecondsAgo`. Recharts only re-renders when actual chart data changes (SSE batch events), not every second.

**Create `LossChart` memoized component (above `TrainingMonitor` function, below `HwCard`):**
```tsx
interface LossChartProps { chartData: Array<{ step: number; train_loss: number | null; eval_loss: number | null }> }

const LossChart = memo(function LossChart({ chartData }: LossChartProps) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={chartData} margin={LOSS_CHART_MARGIN}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="step" tick={AXIS_TICK_LG} tickFormatter={fmtStep} />
        <YAxis tick={AXIS_TICK_LG} tickFormatter={fmtLossAxis} width={48} />
        <Tooltip
          contentStyle={TOOLTIP_CONTENT_STYLE}
          labelStyle={TOOLTIP_LABEL_STYLE}
          itemStyle={TOOLTIP_ITEM_STYLE}
          formatter={fmtLoss}
          labelFormatter={fmtLossLabel}
        />
        <Line
          type="monotone" dataKey="train_loss" name="Train loss"
          stroke="#7C6FCD" dot={false} activeDot={false}
          isAnimationActive={false} connectNulls={false}
        />
        <Line
          type="monotone" dataKey="eval_loss" name="Eval loss"
          stroke="#F0997B" dot={{ r: 4, fill: '#F0997B' }} activeDot={false}
          isAnimationActive={false} connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
})
```

**Create `HwChart` memoized component (similarly above `TrainingMonitor`):**
```tsx
interface HwChartProps { hwChartData: HardwareStats[]; hwHistoryLength: number }

const HwChart = memo(function HwChart({ hwChartData, hwHistoryLength }: HwChartProps) {
  return (
    <div className="mt-4">
      <div className="text-xs text-zinc-600 mb-1">Last {hwHistoryLength} samples</div>
      <ResponsiveContainer width="100%" height={120}>
        <ComposedChart data={hwChartData} margin={HW_CHART_MARGIN}>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis dataKey="timestamp" hide />
          <YAxis domain={[0, 100]} width={28} tick={AXIS_TICK_SM} />
          <Tooltip
            contentStyle={TOOLTIP_CONTENT_STYLE}
            labelStyle={TOOLTIP_LABEL_STYLE}
            itemStyle={TOOLTIP_ITEM_STYLE}
            formatter={fmtPct}
            labelFormatter={fmtEmpty}
          />
          <Line dataKey="gpu_vram_pct" stroke="#8b5cf6" dot={false} activeDot={false} name="VRAM%" isAnimationActive={false} />
          <Line dataKey="gpu_utilization_pct" stroke="#22c55e" dot={false} activeDot={false} name="GPU%" isAnimationActive={false} />
          <Line dataKey="ram_pct" stroke="#f59e0b" dot={false} activeDot={false} name="RAM%" isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-1 text-xs text-zinc-600">
        <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-violet-500 inline-block" />VRAM%</span>
        <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-green-500 inline-block" />GPU%</span>
        <span className="flex items-center gap-1"><span className="w-2 h-0.5 bg-yellow-500 inline-block" />RAM%</span>
      </div>
    </div>
  )
})
```

**In `TrainingMonitor` JSX, replace the inline chart sections:**

Replace lines 1036-1077 (Loss Chart) with:
```tsx
<LossChart chartData={chartData} />
```

Replace lines 816-841 (HW History Chart) with:
```tsx
{hwChartData.length > 1 && (
  <HwChart hwChartData={hwChartData} hwHistoryLength={hwHistory.length} />
)}
```

### 6C: Fix — Merge Two 1-Second Timers Into One

**Current (2 separate setState calls = 2 re-renders/second):**
```typescript
// lines 466-480
useInterval(() => setSecondsAgo(...), 1000, isWindowVisible)
useInterval(() => { if (hwLastUpdatedRef.current !== null) setHwSecondsAgo(...) }, 1000, isWindowVisible)
```

**Replace with single interval:**
```typescript
useInterval(() => {
  setSecondsAgo(Math.floor((Date.now() - lastUpdatedRef.current) / 1000))
  if (hwLastUpdatedRef.current !== null) {
    setHwSecondsAgo(Math.floor((Date.now() - hwLastUpdatedRef.current) / 1000))
  }
}, 1000, isWindowVisible)
```

This halves the re-render rate from 2/s to 1/s. Combined with the memo'd charts, this means charts no longer re-render at all on timestamp ticks.

### 6D: Fix — eval_loss Downsampling Bug

**Current bug (lines 531-543):**
```typescript
const chartData = useMemo(() => {
  const evalSteps = new Set(lossHistory.filter(p => p.eval_loss !== null).map(p => p.step))
  const trainPoints = lossHistory.filter(p => p.train_loss !== null).slice(-500)
  const trainSteps = new Set(trainPoints.map(p => p.step))
  const merged = lossHistory
    .filter(p => trainSteps.has(p.step) || evalSteps.has(p.step))
    .map(p => ({...}))
  return downsample(merged, 200)  // ← BUG: drops ~66% of eval_loss points
}, [lossHistory])
```

**Why it's a bug:** 500 combined entries → `downsample(500, 200)` keeps every 3rd entry by index. Eval entries at indices 10, 20, 40, 50... are dropped. Only eval entries whose array index happens to be divisible by 3 survive. With LOGGING_STEPS=10 and EVAL_STEPS=100, roughly 2/3 of eval_loss points are removed. Since `connectNulls={false}` and `dot={false}`, gaps make the eval line nearly invisible.

**Fixed `chartData` memo:**
```typescript
const chartData = useMemo(() => {
  // Downsample train loss only (there are many train points)
  const trainPoints = lossHistory.filter(p => p.train_loss !== null)
  const trainDownsampled = downsample(trainPoints, 200)
  const trainStepsKept = new Set(trainDownsampled.map(p => p.step))

  // Keep ALL eval loss points (there are few — every 100 steps)
  const evalStepsAll = new Set(
    lossHistory.filter(p => p.eval_loss !== null).map(p => p.step)
  )

  return lossHistory
    .filter(p => trainStepsKept.has(p.step) || evalStepsAll.has(p.step))
    .map(p => ({
      step: p.step,
      train_loss: trainStepsKept.has(p.step) ? p.train_loss : null,
      eval_loss: evalStepsAll.has(p.step) ? p.eval_loss : null,
    }))
}, [lossHistory])
```

### 6E: Dev Debug Overlay

**Add `import.meta.env.DEV` check and overlay at the bottom of the TrainingMonitor return JSX:**
```tsx
{import.meta.env.DEV && (
  <div style={{
    position: 'fixed', bottom: '8px', right: '8px',
    background: 'rgba(0,0,0,0.85)', color: '#22c55e',
    fontSize: '11px', fontFamily: 'monospace', padding: '6px 10px',
    borderRadius: '4px', zIndex: 9999, pointerEvents: 'none',
  }}>
    lossHistory: {lossHistory.length} | hwHistory: {hwHistory.length} |
    logLines: {logLines.length} | SSE: {esRef.current ? '1' : '0'}
  </div>
)}
```

This compiles away in production (`import.meta.env.DEV` is a build-time constant).

### Verification Checklist
- [ ] Open DevTools → Performance → Record 2 minutes on /monitor → confirm recharts re-renders ONLY when new data arrives (SSE batch), NOT every second
- [ ] Dev overlay visible in dev mode, shows stable array lengths
- [ ] After 10 minutes: WebView2 Task Manager memory grows < 20MB total (vs. previously growing continuously)
- [ ] Navigate to /translate and back to /monitor 5 times: memory returns to baseline
- [ ] eval_loss line is clearly visible (all eval points rendered as dots), not sparse/invisible
- [ ] Two `useInterval` calls for secondsAgo merged into one (verify by grepping for `setSecondsAgo`)

---

## Phase 7: Version Bump & Final Verification

**Goal:** Bump version, run full test checklist.

### Command
```bash
python scripts/bump_version.py minor
```
Current version is ~1.0.2 → will become 1.1.0

### Full Testing Checklist (from prompt)
1. `python scripts/train_hime.py --help` shows `--target-loss`, `--patience`, `--min-delta`, `--min-steps`, `--max-epochs`
2. `python scripts/train_generic.py --help` shows same
3. Training config panel opens → set patience=5 → Save → verify `scripts/training_config.json` updated
4. Loss chart: verify eval_loss shows as larger dots, separate from train_loss line
5. Metric toggles: check/uncheck Learning Rate → secondary axis appears/disappears
6. Epoch markers appear as vertical dashed lines
7. Smart stop status text shows in monitor
8. After 10 minutes on Monitor tab: WebView2 memory < 400MB
9. Navigate away/back 5 times: memory stable (dev overlay shows consistent values)
10. Debug overlay shows correctly capped array sizes

---

## Execution Order

Execute phases in order within separate sessions (each is self-contained).

> **IMPORTANT:** Phase 6 sections 6B/6C/6D must be applied to `TrainingMonitor.tsx` BEFORE Phase 4 chart enhancements. Reason: Phase 6D fixes the `chartData` memo so eval_loss points are not discarded, which is a precondition for Phase 4 to produce a visible eval_loss line.

1. **Phase 1** → Create `scripts/callbacks/smart_stopping.py` — pure Python, no dependencies on UI
2. **Phase 2** → Update `train_hime.py` + `train_generic.py` — Python only
3. **Phase 3** → Update `training_monitor.py` + `training.py` + `training_runner.py` — Backend Python/FastAPI
4. **Phase 6** (6B, 6C, 6D first) → Fix recharts re-render loop + eval_loss downsampling bug in `TrainingMonitor.tsx`
5. **Phase 4** → Chart enhancements (toggles, LR axis, epoch markers) — now safe since eval_loss is visible
6. **Phase 5** → Training Config Panel in `TrainingMonitor.tsx`
7. **Phase 6** (6E) → Add dev debug overlay, verify memory
8. **Phase 7** → Version bump + full checklist

Each phase references exact line numbers from the discovery. Re-read the relevant file section before editing.
