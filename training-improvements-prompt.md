# Hime — Training Stopping, Monitor Erweiterung & Memory Leak Fix

Use `/plan` mode. Read all relevant files before making changes.

---

## PROBLEM 1: Loss-basiertes Training-Stoppen statt fester Epochen

Currently training runs for a fixed `num_train_epochs=3` regardless of whether the model has converged. This wastes compute — the 32B training showed eval_loss barely improved from epoch 1 (0.9506) to epoch 2 (0.9500). We need configurable stop conditions.

### 1A: Custom Callback — `SmartStoppingCallback`

Create `scripts/callbacks/smart_stopping.py` (or inline in train_hime.py and train_generic.py):

```python
from transformers import TrainerCallback, TrainerControl, TrainerState, TrainingArguments

class SmartStoppingCallback(TrainerCallback):
    """
    Two modes, configurable:
    
    Mode 1 — Hard Threshold:
      Stop when training_loss <= target_loss for N consecutive evals.
      Example: stop when loss <= 0.4
      
    Mode 2 — Patience (Early Stopping):
      Stop when eval_loss has not improved by at least `min_delta` 
      for `patience` consecutive evaluations.
      Example: stop if eval_loss doesn't improve by 0.001 for 5 evals.
    
    Both modes can be active simultaneously — whichever triggers first wins.
    """
    
    def __init__(
        self,
        # Hard threshold mode
        target_loss: float | None = None,          # e.g. 0.4
        target_loss_metric: str = "loss",          # "loss" (training) or "eval_loss"
        target_confirmations: int = 3,             # must hit target N times in a row
        
        # Patience mode  
        patience: int | None = None,               # e.g. 5 evals without improvement
        patience_metric: str = "eval_loss",        # metric to watch
        min_delta: float = 0.001,                  # minimum improvement to count
        
        # Shared
        min_steps: int = 0,                        # don't stop before this step
    ):
        ...
    
    def on_evaluate(self, args, state, control, metrics, **kwargs):
        # Check patience mode: compare current eval_loss to best
        # If no improvement for `patience` evals → control.should_training_stop = True
        ...
    
    def on_log(self, args, state, control, logs, **kwargs):
        # Check hard threshold mode: if logs["loss"] <= target_loss
        # Increment confirmation counter, stop if >= target_confirmations
        ...
    
    def on_train_end(self, args, state, control, **kwargs):
        # Log why training stopped: "Reached target loss", "Patience exhausted", 
        # or "Completed all epochs"
        ...
```

### 1B: Integrate into training scripts

Update both `scripts/train_hime.py` and `scripts/train_generic.py`:

- Import SmartStoppingCallback
- Read stop config from command line args OR from a JSON config file
- Add these CLI args:
  ```
  --target-loss       Target training loss threshold (e.g. 0.4). None = disabled.
  --patience          Number of evals without improvement before stopping. None = disabled.
  --min-delta         Minimum improvement for patience mode (default: 0.001)
  --min-steps         Don't stop before this step (default: 0)
  ```
- Pass callback to Trainer:
  ```python
  callbacks = []
  if args.target_loss is not None or args.patience is not None:
      callbacks.append(SmartStoppingCallback(
          target_loss=args.target_loss,
          patience=args.patience,
          min_delta=args.min_delta,
          min_steps=args.min_steps,
      ))
  trainer = SFTTrainer(..., callbacks=callbacks)
  ```
- Keep `num_train_epochs` as a maximum cap (default 10 when smart stopping is active, 3 when not)
- Log the stop reason clearly: `[SMART STOP] Training stopped: eval_loss did not improve for 5 evaluations. Best: 0.9500 at step 12400`

### 1C: Config file support

Also support reading stop config from `C:\Projekte\Hime\scripts\training_config.json`:
```json
{
  "stop_mode": "both",
  "target_loss": 0.4,
  "target_loss_metric": "loss",
  "target_confirmations": 3,
  "patience": 5,
  "patience_metric": "eval_loss", 
  "min_delta": 0.001,
  "min_steps": 1000,
  "max_epochs": 10
}
```
CLI args override config file values. Config file is optional — if missing, use defaults (3 epochs, no smart stopping).

### 1D: Backend integration

Update `app/backend/app/services/training_runner.py`:
- When starting training from the app, pass stop config as CLI args
- Read stop config from the training config endpoint

Update `app/backend/app/routers/training.py`:
- Add `GET /api/v1/training/config` — returns current training_config.json
- Add `PUT /api/v1/training/config` — updates training_config.json
- Validate values (target_loss > 0, patience > 0, etc.)

---

## PROBLEM 2: Training Monitor zeigt zu wenig Infos

Currently the Monitor only shows training loss in the chart. The backend already has eval_loss, learning_rate, grad_norm, and epoch data in trainer_state.json — it's just not displayed.

### 2A: Backend — extend loss history response

Update `training_monitor.py` → `get_loss_history()`:

Currently returns `LossPoint(step, loss)`. Change to:
```python
class LossPoint(BaseModel):
    step: int
    train_loss: float | None = None
    eval_loss: float | None = None
    learning_rate: float | None = None
    grad_norm: float | None = None
    epoch: float | None = None
```

Parse ALL fields from trainer_state.json log_history entries:
- Entries with `"loss"` key → train_loss, grad_norm, learning_rate, epoch
- Entries with `"eval_loss"` key → eval_loss (these are at eval steps only)

The SSE stream should also send these extended fields for live updates.

### 2B: Backend — add stop config status to /status endpoint

Extend the `/api/v1/training/status` response:
```json
{
  "status": "training",
  "step": 12400,
  "total_steps": 17709,
  "best_checkpoint": "checkpoint-12400",
  "best_eval_loss": 0.9500,
  "stop_config": {
    "mode": "both",
    "target_loss": 0.4,
    "patience": 5,
    "patience_remaining": 3,
    "target_reached_count": 0
  }
}
```

### 2C: Frontend — extended Loss Chart

Update `TrainingMonitor.tsx` loss chart:

- **Primary Y axis (left):** train_loss (purple line) + eval_loss (coral/orange dots connected by line)
- **Secondary Y axis (right):** learning_rate (thin gray line, much smaller scale)
- Add toggle checkboxes above the chart to show/hide each metric:
  `[✓] Train Loss  [✓] Eval Loss  [ ] Learning Rate  [ ] Grad Norm`
- Default: train_loss and eval_loss visible, others hidden
- Eval loss points should be larger dots (they're less frequent) connected by a line
- Add epoch boundary markers as vertical dashed lines (parse from epoch field)
- Tooltip on hover: show all metrics at that step
- Keep the existing downsampling for train_loss (max 200 points for the chart)
- Do NOT downsample eval_loss — there are far fewer eval points

### 2D: Frontend — Training Config Panel (Overlay/Modal)

Add a "Training Settings" button (gear icon) in the Monitor header, next to the model selector.

Opens a settings panel (slide-in from right, or modal) with:

```
═══ Stop Conditions ═══

Stop Mode:    [▼ Both / Threshold Only / Patience Only / None (fixed epochs)]

── Threshold ──
Target Loss:        [ 0.4    ]  ← number input
Metric:             [▼ Training Loss / Eval Loss]
Confirmations:      [ 3      ]  ← how many times in a row

── Early Stopping ──  
Patience:           [ 5      ]  ← evals without improvement
Metric:             [▼ Eval Loss]
Min Delta:          [ 0.001  ]  ← minimum improvement

── General ──
Max Epochs:         [ 10     ]  ← hard cap, even with smart stopping
Min Steps:          [ 1000   ]  ← don't stop before this

[Save]  [Reset to Defaults]
```

- On Save: `PUT /api/v1/training/config` 
- Settings are saved to `training_config.json` and applied on next training start
- If training is currently running, show a note: "Changes apply to next training run"
- Show current stop config status in the main monitor view:
  `"Smart Stop: Patience 3/5 remaining | Target 0/3 confirmations"`

---

## PROBLEM 3: Memory Leak (STILL not fixed)

WebView2 memory still grows over time. Previous fixes (downsampling, SSE cleanup, polling caps) helped but didn't solve it.

### 3A: Full audit of all state arrays and intervals

Go through EVERY component and find:
1. Every `useState` that holds an array — verify it has a hard cap
2. Every `setInterval` — verify `clearInterval` in cleanup
3. Every `EventSource` — verify `.removeEventListener()` AND `.close()` in cleanup
4. Every `fetch` — verify AbortController usage and `.abort()` in cleanup

Files to audit:
- `src/views/TrainingMonitor.tsx`
- `src/App.tsx`
- `src/components/Sidebar.tsx`
- Any other component that polls or streams data

### 3B: Specific fixes

1. **hwHistory array**: Hard cap at 120 entries (10 minutes at 5s intervals). 
   Every `setHwHistory` call MUST enforce: `prev.slice(-120)`

2. **lossHistory array**: Hard cap at 500. Already supposedly fixed but verify.

3. **logLines array**: Hard cap at 100 lines. Verify.

4. **backendLogLines**: Hard cap at 50. Verify.

5. **SSE reconnection**: If SSE disconnects and reconnects, it must NOT create 
   a second parallel EventSource. Use a ref to track the current one:
   ```typescript
   const eventSourceRef = useRef<EventSource | null>(null)
   // In useEffect:
   if (eventSourceRef.current) {
     eventSourceRef.current.close()
   }
   eventSourceRef.current = new EventSource(...)
   // In cleanup:
   eventSourceRef.current?.close()
   eventSourceRef.current = null
   ```

6. **Route-based unmounting**: Verify that TrainingMonitor is ONLY mounted 
   when the user is on the /monitor route. If it's in a persistent layout, 
   it must be conditionally rendered. SSE and polling MUST stop on other routes.

7. **recharts SVG cleanup**: When lossHistory or hwHistory update, recharts 
   creates new SVG elements. If old ones aren't cleaned up, DOM grows.
   Consider using `isAnimationActive={false}` on all recharts components 
   to prevent animation-related DOM leaks.

8. **Dev mode HMR**: In dev mode, HMR can cause duplicate mounts without 
   cleanup. Add `React.StrictMode` handling — useEffect cleanup must work 
   correctly when React double-invokes effects.

### 3C: Verification

After fixes, add a temporary debug overlay (only in dev mode) showing:
```
[DEV] hwHistory: 45 | lossHistory: 200 | logLines: 88 | SSE: 1 active | Intervals: 2
```
This helps verify caps are working. Remove before release build.

---

## VERSION BUMP

After all changes:
```
python scripts/bump_version.py minor
```

This is a significant feature release:
- Smart training stopping (threshold + patience)
- Extended training monitor with all metrics
- Training config UI
- Memory leak fixes (round N+1)

---

## TESTING CHECKLIST

After implementation, verify:
1. `python scripts/train_hime.py --help` shows new args (--target-loss, --patience, etc.)
2. Training config panel opens and saves correctly
3. Loss chart shows eval_loss as separate line with larger dots
4. Metric toggles work (show/hide individual lines)
5. Smart stop status shows in monitor when training runs
6. After 10 minutes on Monitor tab: WebView2 memory < 400MB
7. Navigate away from Monitor and back 5 times: memory stable
8. Debug overlay shows capped array sizes
