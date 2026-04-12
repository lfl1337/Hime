# Training Checkpoint Crisis — Diagnosis & Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore normal training speed and checkpoint saving after disk exhaustion caused 25x slowdown — training takes ~32 min/step instead of ~1.3 min/step, never reaching checkpoint intervals.

**Architecture:** Checkpoint config is correct (save_steps=100, save_strategy="steps"). Training resumes from checkpoint-14400 but each step takes ~32 minutes instead of ~1.3 minutes. After 8.5 hours only 19 steps complete, never reaching the next save point at step 14500. Root cause: 98% full disk (22GB free on 931GB) causing swap thrashing and I/O failure.

**Tech Stack:** Python, Unsloth, Transformers/TRL, PyTorch, CUDA, Windows 11, RTX 5090

---

## Diagnosis Summary

| Finding | Detail |
|---------|--------|
| save_steps | 100 (correct) |
| save_strategy | "steps" implicit default (correct but should be explicit) |
| save_total_limit | None/unlimited in train_hime.py, 3 in train_generic.py |
| SmartStoppingCallback | Only sets should_training_stop, never should_save (safe) |
| SaveCheckpointCallback | Only logs, no interference (safe) |
| Disk usage | 98% (22GB free on 931GB) |
| modelle/ directory | 110GB (includes ~45GB 72B GGUF not needed for training) |
| Normal step speed | ~1.3 min/step (Mar 31, checkpoint-14300→14400) |
| Current step speed | ~32 min/step (25x slower) |
| Steps since resume | 19 (14401→14419) in 8.5 hours |
| Next checkpoint at | Step 14500 (81 steps away ≈ 43 hours at current speed) |
| max_epochs | 10 in training_config.json (affects NEXT run; current run uses 3) |

## Slowdown Pattern (from training log)

```
Step 14401:   31s  (cached/fast)
Step 14402:   13s  (still fast)
Step 14403:    5m  (degradation begins)
Step 14404:   29m  (broken)
Step 14405+:  ~32m each (stable at 25x slower)
```

Classic memory pressure / swap thrashing: first steps use cached data, then performance collapses.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/training_config.json` | Modify | Fix max_epochs from 10→3 |
| `scripts/train_hime.py:305-330` | Modify | Add explicit save_strategy, reduce max_memory |
| `scripts/train_generic.py:301-326` | Modify | Add explicit save_strategy, reduce max_memory |
| `scripts/train_hime.py:273-291` | Modify | Add VRAM monitoring to SaveCheckpointCallback |
| `scripts/train_generic.py:266-285` | Modify | Add VRAM monitoring to SaveCheckpointCallback |

---

### Task 1: Free Disk Space (Critical — Root Cause Fix)

**Target:** Get from 22GB free to 60-70GB+ free.

**⚠️ This task requires user interaction — all deletions need confirmation.**

- [ ] **Step 1: Kill the currently running training**

The slow training must be stopped first. User should Ctrl+C the training terminal, or:
```powershell
tasklist | findstr python
# Then: taskkill /F /PID <pid>
```

- [ ] **Step 2: Check current disk space**

```powershell
wmic logicaldisk get caption,freespace,size
```

Expected: ~22GB free on C:.

- [ ] **Step 3: Check size of 72B GGUF model (~45GB)**

This model is for inference only and can be re-downloaded. Check size:
```powershell
dir /s "C:\Projekte\Hime\modelle\lmstudio-community\Qwen2.5-72B-Instruct-GGUF"
```

**IMPORTANT:** Ask user for explicit confirmation before deleting.

If confirmed:
```powershell
rmdir /s /q "C:\Projekte\Hime\modelle\lmstudio-community\Qwen2.5-72B-Instruct-GGUF"
```

- [ ] **Step 4: Delete the `interrupted` checkpoint (obsolete, from Feb 28)**

This predates all current checkpoints and has no value:
```powershell
rmdir /s /q "C:\Projekte\Hime\modelle\lora\Qwen2.5-32B-Instruct\checkpoint\interrupted"
```

- [ ] **Step 5: Do NOT delete checkpoint-12400**

checkpoint-12400 was the "Best" checkpoint with eval_loss 0.9500. Keep as reference (~791MB).

- [ ] **Step 6: Clean Python/Conda caches**

```powershell
pip cache purge
conda clean --all -y
```

- [ ] **Step 7: Verify disk space improved**

```powershell
wmic logicaldisk get caption,freespace,size
```

Expected: 60GB+ free (was 22GB).

---

### Task 2: Windows Defender Exclusions

Windows Defender real-time scanning adds latency to every checkpoint file write and data load.

- [ ] **Step 1: Add exclusions (requires elevated PowerShell)**

Run PowerShell as Administrator:
```powershell
Add-MpPreference -ExclusionPath "C:\Projekte\Hime\modelle\"
Add-MpPreference -ExclusionPath "C:\Projekte\Hime\data\"
Add-MpPreference -ExclusionPath "C:\Projekte\Hime\Conda\"
```

- [ ] **Step 2: Verify exclusions are set**

```powershell
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
```

Expected: All three paths listed.

---

### Task 3: Fix training_config.json (max_epochs 10→3)

The max_epochs=10 in training_config.json was set during experimentation and causes the Monitor UI to display wrong total_steps (59,030 instead of 17,709). It only affects the NEXT training run.

**Files:**
- Modify: `scripts/training_config.json`

- [ ] **Step 1: Edit training_config.json**

Change max_epochs from 10 to 3 in `scripts/training_config.json`:

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

- [ ] **Step 2: Commit**

```bash
git add scripts/training_config.json
git commit -m "fix(training): set max_epochs back to 3 in config (was 10 from experimentation)"
```

---

### Task 4: Add Explicit save_strategy to Prevent Future Ambiguity

Both scripts rely on the implicit default that `save_strategy="steps"` when `save_steps` is set. Making it explicit prevents future breakage if Transformers changes defaults.

**Files:**
- Modify: `scripts/train_hime.py:305-330` (TrainingArguments block)
- Modify: `scripts/train_generic.py:301-326` (TrainingArguments block)

- [ ] **Step 1: Add save_strategy="steps" to train_hime.py**

In `scripts/train_hime.py`, in the TrainingArguments block (around line 319), after the `save_steps` line, add `save_strategy`:

Before:
```python
    save_steps                    = SAVE_STEPS,
    eval_steps                    = EVAL_STEPS,
```

After:
```python
    save_steps                    = SAVE_STEPS,
    save_strategy                 = "steps",
    eval_steps                    = EVAL_STEPS,
```

- [ ] **Step 2: Add save_strategy="steps" to train_generic.py**

In `scripts/train_generic.py`, in the TrainingArguments block (around line 315), after the `save_steps` line, add `save_strategy`:

Before:
```python
    save_steps=SAVE_STEPS,
    eval_steps=EVAL_STEPS,
```

After:
```python
    save_steps=SAVE_STEPS,
    save_strategy="steps",
    eval_steps=EVAL_STEPS,
```

- [ ] **Step 3: Commit**

```bash
git add scripts/train_hime.py scripts/train_generic.py
git commit -m "fix(training): add explicit save_strategy='steps' to both training scripts"
```

---

### Task 5: Reduce Memory Limits and Add VRAM Monitoring

Reduce max_memory to give CUDA headroom on a disk-pressured system, and add VRAM logging to SaveCheckpointCallback for visibility.

**Files:**
- Modify: `scripts/train_hime.py:148` (max_memory)
- Modify: `scripts/train_generic.py:159` (max_memory)
- Modify: `scripts/train_hime.py:273-291` (SaveCheckpointCallback)
- Modify: `scripts/train_generic.py:266-285` (SaveCheckpointCallback)

- [ ] **Step 1: Reduce max_memory in train_hime.py**

In `scripts/train_hime.py` around line 148, change:

Before:
```python
max_memory      = {0: "30GB", "cpu": "20GB"},  # Cap CPU RAM to prevent pagefile exhaustion
```

After:
```python
max_memory      = {0: "28GB", "cpu": "16GB"},  # 28GB GPU = 4GB CUDA headroom, 16GB CPU = less pagefile pressure
```

- [ ] **Step 2: Reduce max_memory in train_generic.py**

In `scripts/train_generic.py` around line 159, change:

Before:
```python
max_memory={0: "30GB", "cpu": "20GB"},
```

After:
```python
max_memory={0: "28GB", "cpu": "16GB"},
```

- [ ] **Step 3: Add VRAM monitoring to SaveCheckpointCallback in train_hime.py**

In `scripts/train_hime.py`, replace the SaveCheckpointCallback class (lines 273-291):

Before:
```python
class SaveCheckpointCallback(TrainerCallback):
    """Structured log lines for checkpoint saves, epoch ends, and training lifecycle."""

    def on_save(self, args, state, control, **kwargs):
        checkpoint = state.best_model_checkpoint or f"step-{state.global_step}"
        print(f"[CHECKPOINT] Gespeichert: {checkpoint}")
        return control

    def on_train_begin(self, args, state, control, **kwargs):
        print(f"[INFO] Starte Training: {state.max_steps} Steps")
        return control

    def on_train_end(self, args, state, control, **kwargs):
        print(f"[FERTIG] Training abgeschlossen bei Step {state.global_step}")
        return control

    def on_epoch_end(self, args, state, control, **kwargs):
        print(f"[EPOCH] Epoch {state.epoch:.2f} abgeschlossen")
        return control
```

After:
```python
class SaveCheckpointCallback(TrainerCallback):
    """Structured log lines for checkpoint saves, epoch ends, and training lifecycle."""

    def on_save(self, args, state, control, **kwargs):
        checkpoint = state.best_model_checkpoint or f"step-{state.global_step}"
        if torch.cuda.is_available():
            alloc = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"[CHECKPOINT] Gespeichert: {checkpoint} (VRAM: {alloc:.1f}GB alloc / {reserved:.1f}GB reserved)")
        else:
            print(f"[CHECKPOINT] Gespeichert: {checkpoint}")
        return control

    def on_train_begin(self, args, state, control, **kwargs):
        print(f"[INFO] Starte Training: {state.max_steps} Steps")
        return control

    def on_train_end(self, args, state, control, **kwargs):
        print(f"[FERTIG] Training abgeschlossen bei Step {state.global_step}")
        return control

    def on_epoch_end(self, args, state, control, **kwargs):
        print(f"[EPOCH] Epoch {state.epoch:.2f} abgeschlossen")
        return control
```

**Note:** `torch` is already imported in train_hime.py — no new import needed.

- [ ] **Step 4: Add VRAM monitoring to SaveCheckpointCallback in train_generic.py**

In `scripts/train_generic.py`, replace the on_save method in SaveCheckpointCallback (lines 269-272):

Before:
```python
    def on_save(self, args, state, control, **kwargs):
        checkpoint = state.best_model_checkpoint or f"step-{state.global_step}"
        print(f"[CHECKPOINT] Saved: {checkpoint}")
        return control
```

After:
```python
    def on_save(self, args, state, control, **kwargs):
        checkpoint = state.best_model_checkpoint or f"step-{state.global_step}"
        if torch.cuda.is_available():
            alloc = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"[CHECKPOINT] Saved: {checkpoint} (VRAM: {alloc:.1f}GB alloc / {reserved:.1f}GB reserved)")
        else:
            print(f"[CHECKPOINT] Saved: {checkpoint}")
        return control
```

**Note:** Verify `torch` is imported in train_generic.py. If not, add `import torch` near the top imports.

- [ ] **Step 5: Commit**

```bash
git add scripts/train_hime.py scripts/train_generic.py
git commit -m "fix(training): reduce max_memory limits, add VRAM monitoring to checkpoint callback"
```

---

### Task 6: Test Resume with Fixed Config

**ONLY after Tasks 1-5 are complete and disk has 60GB+ free.**

- [ ] **Step 1: Verify disk space**

```powershell
wmic logicaldisk get caption,freespace,size
```

Expected: 60GB+ free.

- [ ] **Step 2: Resume training from checkpoint-14400**

```powershell
cd C:\Projekte\Hime
conda activate hime
python scripts/train_hime.py --log-file logs\test-resume.log
```

The script auto-detects the latest checkpoint (checkpoint-14400) via the logic at lines 160-177.

- [ ] **Step 3: Monitor first 10 steps**

Watch the training output for step timing:
- **Expected:** Steps complete in ~1-2 minutes each
- **Failure indicator:** Steps taking >5 minutes each → disk is still pressured

Also watch for VRAM logging on checkpoint save (new from Task 5):
```
[CHECKPOINT] Gespeichert: step-14500 (VRAM: 24.3GB alloc / 26.8GB reserved)
```

- [ ] **Step 4: Verify checkpoint saved at step 14500**

After training passes step 14500:
```powershell
dir "C:\Projekte\Hime\modelle\lora\Qwen2.5-32B-Instruct\checkpoint\" /od
```

Expected: `checkpoint-14500` directory exists.

- [ ] **Step 5: If still slow despite 60GB+ free disk**

Escalation diagnostics:
1. Run `nvidia-smi -l 5` during training to watch VRAM usage
2. Check Windows Event Viewer for disk/memory warnings (`eventvwr.msc` → Windows Logs → System)
3. Consider reducing MAX_SEQ_LEN from 1024 to 512 temporarily (line 51 in train_hime.py)
4. Check if `packing=True` with 104k training samples causes memory issues

---

## Priority Order

1. **Task 1** (free disk space) — root cause fix, 72B GGUF deletion gives ~45GB back
2. **Task 2** (Windows Defender exclusions) — prevents scan latency on checkpoint writes
3. **Task 5** (reduce memory limits + VRAM monitoring) — gives CUDA headroom, adds visibility
4. **Task 3** (fix config) — prevents wrong total_steps display in Monitor UI
5. **Task 4** (explicit save_strategy) — defensive hardening
6. **Task 6** (test resume) — verify everything works
