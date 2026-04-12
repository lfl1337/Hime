# Training Checkpoint Crisis — Diagnosis & Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore normal training speed and checkpoint saving after identifying that the real issue is catastrophic training slowdown (25x slower than normal), NOT misconfigured checkpoint settings.

**Architecture:** The checkpoint config is correct (save_steps=100, save_strategy="steps"). Training resumes from checkpoint-14400 but each step takes ~32 minutes instead of ~1.3 minutes. After 8.5 hours only 19 steps complete, never reaching the next save point at step 14500. Root cause is memory/disk pressure on a 98% full drive causing swap thrashing.

**Tech Stack:** Python, Unsloth, Transformers/TRL, PyTorch, CUDA, Windows 11

---

## Diagnosis Summary

| Finding | Detail |
|---------|--------|
| save_steps | 100 (correct) |
| save_strategy | "steps" default (correct) |
| save_total_limit | None/unlimited (correct) |
| SmartStoppingCallback | Only sets should_training_stop, never should_save (safe) |
| SaveCheckpointCallback | Only logs, no interference (safe) |
| Disk usage | 98% (22GB free on 931GB) |
| modelle/ directory | 110GB |
| data/ directory | 13GB |
| Normal step speed | ~1.3 min/step (Mar 31 checkpoint-14300→14400) |
| Current step speed | ~32 min/step (25x slower) |
| Steps since resume | 19 (14401→14419) in 8.5 hours |
| Next checkpoint at | Step 14500 (81 steps away = ~43 hours at current speed) |
| max_epochs | 10 (from training_config.json) → 59,030 total steps |
| Active script | train_generic.py (NOT train_hime.py) |

## Slowdown Pattern (from log)

```
Step 14401:   31s  (cached/fast)
Step 14402:   13s  (still fast)
Step 14403:    5m  (degradation begins)
Step 14404:   29m  (broken)
Step 14405+:  ~32m each (stable at 25x slower than normal)
```

This is a classic memory pressure / swap thrashing pattern: first steps after resume use cached data, then performance collapses as the system runs out of fast memory.

---

### Task 1: Free Disk Space (Critical)

**Files:**
- Check: `C:\Projekte\Hime\modelle\lora\` (old checkpoints, interrupted saves)
- Check: Windows temp files, pip cache, conda cache
- Check: `C:\Projekte\Hime\unsloth_compiled_cache\` (3MB, minor)

- [ ] **Step 1: Audit disk usage in modelle/**

Run:
```bash
du -sh /c/Projekte/Hime/modelle/lora/*/checkpoint/*/ 2>/dev/null
du -sh /c/Projekte/Hime/modelle/lora/*/adapter/ 2>/dev/null
du -sh /c/Projekte/Hime/modelle/base*/ 2>/dev/null
```

Expected: Identify which checkpoints/models consume the most space.

- [ ] **Step 2: Delete the `interrupted` checkpoint (if not needed)**

The `interrupted` directory in `modelle/lora/Qwen2.5-32B-Instruct/checkpoint/` is from Feb 28 and predates the current training. Since checkpoint-14400 is more recent:

```bash
du -sh /c/Projekte/Hime/modelle/lora/Qwen2.5-32B-Instruct/checkpoint/interrupted/
# If user confirms deletion:
rm -rf /c/Projekte/Hime/modelle/lora/Qwen2.5-32B-Instruct/checkpoint/interrupted/
```

- [ ] **Step 3: Delete oldest checkpoint if space is critical**

checkpoint-12400 (Mar 28) is older than checkpoint-14400. If the adapter was already exported from a later state, it can be removed:

```bash
du -sh /c/Projekte/Hime/modelle/lora/Qwen2.5-32B-Instruct/checkpoint/checkpoint-12400/
# If user confirms:
rm -rf /c/Projekte/Hime/modelle/lora/Qwen2.5-32B-Instruct/checkpoint/checkpoint-12400/
```

- [ ] **Step 4: Check Windows pagefile and temp usage**

```bash
# Check available disk space after cleanup
df -h /c/
# Check Windows temp
du -sh /c/Users/lfLaw/AppData/Local/Temp/ 2>/dev/null | head -5
# Check pip cache
du -sh /c/Users/lfLaw/AppData/Local/pip/cache/ 2>/dev/null
```

Target: Get disk usage below 90% (~93GB free).

- [ ] **Step 5: Verify disk space improved**

```bash
df -h /c/
```

Expected: At least 50GB+ free before restarting training.

---

### Task 2: Reduce max_epochs to Prevent Runaway Training

**Files:**
- Modify: `C:\Projekte\Hime\scripts\training_config.json`

The config has `max_epochs: 10` which creates 59,030 total steps. The model already trained 14,400 steps (~2.44 epochs). Continuing to 10 epochs is likely unnecessary and creates massive overhead.

- [ ] **Step 1: Review current training_config.json**

```bash
cat /c/Projekte/Hime/scripts/training_config.json
```

Current:
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

- [ ] **Step 2: Reduce max_epochs from 10 to 3 (or 5 max)**

Edit `C:\Projekte\Hime\scripts\training_config.json`:
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
  "max_epochs": 3
}
```

**Why:** 3 epochs = ~17,709 total steps. Resuming from 14,400 means only ~3,309 steps remain (vs 44,630 with 10 epochs). With early stopping configured (target_loss=0.4, patience=5), training will stop when it converges.

- [ ] **Step 3: Commit the config change**

```bash
git add scripts/training_config.json
git commit -m "fix(training): reduce max_epochs from 10 to 3 to prevent runaway training"
```

---

### Task 3: Add Explicit save_strategy to Prevent Future Ambiguity

**Files:**
- Modify: `C:\Projekte\Hime\scripts\train_hime.py:305-330`
- Modify: `C:\Projekte\Hime\scripts\train_generic.py:301-330`

Both scripts rely on the implicit default that save_strategy="steps" when save_steps is set. Making it explicit prevents future breakage if transformers changes defaults.

- [ ] **Step 1: Add save_strategy="steps" to train_hime.py**

In `C:\Projekte\Hime\scripts\train_hime.py`, line ~319, after `save_steps = SAVE_STEPS,` add:

```python
        save_strategy                 = "steps",
```

- [ ] **Step 2: Add save_strategy="steps" to train_generic.py**

Same change in `C:\Projekte\Hime\scripts\train_generic.py` in the TrainingArguments block.

- [ ] **Step 3: Run dry-run verification**

Create a minimal dry-run test that validates TrainingArguments without loading the model:

```bash
python -c "
from transformers import TrainingArguments
args = TrainingArguments(
    output_dir='/tmp/test',
    save_steps=100,
    save_strategy='steps',
    eval_strategy='steps',
    eval_steps=100,
    save_total_limit=None,
    num_train_epochs=3,
)
print(f'save_steps:       {args.save_steps}')
print(f'save_strategy:    {args.save_strategy}')
print(f'eval_strategy:    {args.evaluation_strategy}')
print(f'save_total_limit: {args.save_total_limit}')
print(f'num_train_epochs: {args.num_train_epochs}')
print('ALL OK')
"
```

Expected:
```
save_steps:       100
save_strategy:    steps
eval_strategy:    steps
save_total_limit: None
num_train_epochs: 3
ALL OK
```

- [ ] **Step 4: Commit the explicit save_strategy**

```bash
git add scripts/train_hime.py scripts/train_generic.py
git commit -m "fix(training): add explicit save_strategy='steps' to both training scripts"
```

---

### Task 4: Diagnose the VRAM/Memory Thrashing

**Files:**
- Check: NVIDIA driver logs, Windows Event Viewer
- Check: PyTorch CUDA memory stats

This task identifies WHY training is 25x slower. The pattern (fast first steps, then collapse) suggests VRAM overflow causing CPU/disk swapping.

- [ ] **Step 1: Check CUDA memory allocation settings**

The script sets `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` and limits GPU to 30GB, CPU to 20GB:
```python
max_memory = {0: "30GB", "cpu": "20GB"}
```

On a 32GB RTX 5090, 30GB leaves only 2GB for CUDA overhead. Combined with 98% disk usage (pagefile thrashing), this could explain the slowdown.

- [ ] **Step 2: Kill the currently running training (if still active)**

Before any fix, the slow training should be stopped:

```bash
# Check if training is running
tasklist | grep -i python
# If running, the user should Ctrl+C it or kill it
```

- [ ] **Step 3: Reduce max_memory GPU limit to give CUDA more headroom**

In both `train_hime.py` (line 148) and `train_generic.py`, change:
```python
max_memory = {0: "30GB", "cpu": "20GB"}
```
to:
```python
max_memory = {0: "28GB", "cpu": "16GB"}
```

**Why:** 28GB GPU gives 4GB headroom for CUDA kernels, intermediate tensors, and checkpoint saving. 16GB CPU prevents the pagefile from being exhausted on a disk-pressured system.

- [ ] **Step 4: Add VRAM monitoring to SaveCheckpointCallback**

In `C:\Projekte\Hime\scripts\train_hime.py`, enhance SaveCheckpointCallback.on_save to log VRAM usage:

```python
def on_save(self, args, state, control, **kwargs):
    checkpoint = state.best_model_checkpoint or f"step-{state.global_step}"
    if torch.cuda.is_available():
        alloc = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        print(f"[CHECKPOINT] Gespeichert: {checkpoint} (VRAM: {alloc:.1f}GB alloc / {reserved:.1f}GB reserved)")
    else:
        print(f"[CHECKPOINT] Gespeichert: {checkpoint}")
    return control
```

- [ ] **Step 5: Commit VRAM monitoring and memory limit changes**

```bash
git add scripts/train_hime.py scripts/train_generic.py
git commit -m "fix(training): reduce max_memory limits, add VRAM monitoring to checkpoint callback"
```

---

### Task 5: Test Resume with Fixed Config

**Files:**
- Run: `train_hime.py` or `train_generic.py` for ~200 steps only

- [ ] **Step 1: Verify disk space is adequate**

```bash
df -h /c/
```

Expected: >50GB free.

- [ ] **Step 2: Start training and monitor first 10 steps**

```bash
cd /c/Projekte/Hime
python scripts/train_hime.py --log-file logs/test-resume.log 2>&1 | head -100
```

Watch the step speed:
- Steps should complete in ~1-2 minutes each (not 30 minutes)
- First checkpoint save should appear at step 14500
- VRAM usage should be logged at each save

- [ ] **Step 3: Verify checkpoint was created at step 14500**

```bash
ls -la /c/Projekte/Hime/modelle/lora/Qwen2.5-32B-Instruct/checkpoint/
```

Expected: `checkpoint-14500` directory exists.

- [ ] **Step 4: If still slow, investigate further**

If steps are still ~30 min each with free disk space:
1. Check `nvidia-smi` during training for VRAM usage
2. Check if Windows Defender is scanning checkpoint files (add exclusion)
3. Consider reducing MAX_SEQ_LEN from 1024 to 512 temporarily
4. Check if packing=True with 94k samples causes memory issues

---

## Priority Order

1. **Task 1** (free disk space) — most likely root cause of swap thrashing
2. **Task 2** (reduce max_epochs) — prevents 44k unnecessary steps
3. **Task 4** (kill running training, fix memory limits)
4. **Task 3** (explicit save_strategy) — defensive fix
5. **Task 5** (test resume) — verify everything works
