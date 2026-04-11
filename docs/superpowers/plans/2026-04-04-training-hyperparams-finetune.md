# Training Hyperparameter Fine-Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adjust 4 hyperparameters in both training scripts to overcome overfitting plateau at eval_loss 0.950, then verify with a dry-run (no training execution).

**Architecture:** Pure config changes — lower learning rate (2e-4→5e-5), add LoRA dropout (0→0.05), halve gradient accumulation (16→8), switch warmup to fixed 50 steps. The model warm-starts from checkpoint-12400 (best eval_loss) with fresh optimizer.

**Tech Stack:** Python, Unsloth, HuggingFace Transformers/TRL, conda env `hime`

---

### File Structure

No new files. Two files modified:

| File | Changes |
|------|---------|
| `scripts/train_hime.py` | 4 constant values + 1 TrainingArguments param name |
| `scripts/train_generic.py` | 4 constant/config values + 1 TrainingArguments param name |

---

### Task 1: Update hyperparameters in train_hime.py

**Files:**
- Modify: `scripts/train_hime.py:44` (LORA_DROPOUT)
- Modify: `scripts/train_hime.py:47` (LEARNING_RATE)
- Modify: `scripts/train_hime.py:50` (GRAD_ACCUM)
- Modify: `scripts/train_hime.py:52` (WARMUP_RATIO → WARMUP_STEPS)
- Modify: `scripts/train_hime.py:374` (warmup_ratio → warmup_steps in TrainingArguments)

- [ ] **Step 1: Change the 4 constants at the top of the file**

Replace the constants block at lines 44–52:

```python
# Old:
LORA_DROPOUT    = 0.0   # 0 = Unsloth Fast Path aktiv!

# Training Parameter
LEARNING_RATE   = 2e-4
EPOCHS          = 3
BATCH_SIZE      = 1     # Reduziert von 2 → weniger VRAM
GRAD_ACCUM      = 16    # Erhöht → gleiche effektive Batch Size = 16
MAX_SEQ_LEN     = 1024  # Reduziert von 2048 → weniger VRAM
WARMUP_RATIO    = 0.05
```

```python
# New:
LORA_DROPOUT    = 0.05  # Regularisierung gegen Overfitting (deaktiviert Unsloth Fast Path)

# Training Parameter
LEARNING_RATE   = 5e-5  # Gesenkt von 2e-4 — Feinschliff nach Loss-Plateau
EPOCHS          = 3
BATCH_SIZE      = 1     # Reduziert von 2 → weniger VRAM
GRAD_ACCUM      = 8     # Halbiert von 16 → schnellere Steps, rauschigere Gradienten
MAX_SEQ_LEN     = 1024  # Reduziert von 2048 → weniger VRAM
WARMUP_STEPS    = 50    # Fixe 50 Steps statt 5% Ratio — reicht für frischen Optimizer
```

- [ ] **Step 2: Update TrainingArguments to use warmup_steps**

At line 374, change `warmup_ratio` to `warmup_steps`:

```python
# Old:
        warmup_ratio                  = WARMUP_RATIO,

# New:
        warmup_steps                  = WARMUP_STEPS,
```

- [ ] **Step 3: Update the info print**

At line 362, the batch size print uses `GRAD_ACCUM` — no change needed (still references the constant). But search for any other references to `WARMUP_RATIO` that need updating:

Run: `grep -n "WARMUP_RATIO" scripts/train_hime.py`

Expected: Zero matches (the only reference was in TrainingArguments, already changed).

---

### Task 2: Update hyperparameters in train_generic.py

**Files:**
- Modify: `scripts/train_generic.py:48` (qwen32b grad_accum in MODEL_CONFIGS)
- Modify: `scripts/train_generic.py:79` (LORA_DROPOUT)
- Modify: `scripts/train_generic.py:82` (LEARNING_RATE)
- Modify: `scripts/train_generic.py:87` (WARMUP_RATIO → WARMUP_STEPS)
- Modify: `scripts/train_generic.py:341` (warmup_ratio → warmup_steps in TrainingArguments)

- [ ] **Step 1: Change qwen32b grad_accum in MODEL_CONFIGS**

At line 48, inside the `'qwen32b'` dict only:

```python
# Old:
    'qwen32b': {
        'model':    'unsloth/Qwen2.5-32B-Instruct-bnb-4bit',
        'lora_dir': 'Qwen2.5-32B-Instruct',
        'max_seq':  1024,
        'grad_accum': 16,
    },

# New:
    'qwen32b': {
        'model':    'unsloth/Qwen2.5-32B-Instruct-bnb-4bit',
        'lora_dir': 'Qwen2.5-32B-Instruct',
        'max_seq':  1024,
        'grad_accum': 8,
    },
```

**Important:** Do NOT change grad_accum for the other model configs (qwen14b, qwen72b, gemma27b, deepseek). Those are separate models with their own tuning.

- [ ] **Step 2: Change the 3 global constants**

At lines 79, 82, 87:

```python
# Old:
LORA_DROPOUT = 0.0
LEARNING_RATE = 2e-4
WARMUP_RATIO  = 0.05

# New:
LORA_DROPOUT  = 0.05   # Regularisierung gegen Overfitting
LEARNING_RATE = 5e-5   # Gesenkt von 2e-4 — Feinschliff nach Loss-Plateau
WARMUP_STEPS  = 50     # Fixe 50 Steps statt 5% Ratio
```

- [ ] **Step 3: Update TrainingArguments to use warmup_steps**

At line 341:

```python
# Old:
        warmup_ratio=WARMUP_RATIO,

# New:
        warmup_steps=WARMUP_STEPS,
```

- [ ] **Step 4: Verify no remaining WARMUP_RATIO references**

Run: `grep -n "WARMUP_RATIO" scripts/train_generic.py`

Expected: Zero matches.

---

### Task 3: Dry-run verification

**Files:** None (read-only verification)

- [ ] **Step 1: Syntax check both files**

Run:
```powershell
conda run -n hime python -c "import py_compile; py_compile.compile(r'C:\Projekte\Hime\scripts\train_hime.py', doraise=True); py_compile.compile(r'C:\Projekte\Hime\scripts\train_generic.py', doraise=True); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 2: Dry-run TrainingArguments to confirm no errors**

Run:
```powershell
conda run -n hime python -c "
from transformers import TrainingArguments
args = TrainingArguments(
    output_dir='test',
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=5e-5,
    warmup_steps=50,
    save_steps=100,
    save_strategy='steps',
    eval_steps=100,
    eval_strategy='steps',
    num_train_epochs=3,
    save_total_limit=None,
    report_to='none',
)
print(f'learning_rate:    {args.learning_rate}')
print(f'grad_accum:       {args.gradient_accumulation_steps}')
print(f'warmup:           {args.warmup_steps}')
print(f'save_steps:       {args.save_steps}')
print(f'save_strategy:    {args.save_strategy}')
print('ALL OK')
"
```

Expected output:
```
learning_rate:    5e-05
grad_accum:       8
warmup:           50
save_steps:       100
save_strategy:    IntervalStrategy.STEPS
ALL OK
```

- [ ] **Step 3: Print hyperparameter comparison summary**

Print this to the console to confirm all changes:

```
=== Hyperparameter Vergleich ===

                        Alt (overfitted)    Neu (Feinschliff)
Learning Rate:          2e-4                5e-5
LoRA Dropout:           0                   0.05
Gradient Accumulation:  16                  8
Effective Batch Size:   16                  8
Warmup:                 5% ratio            50 steps (fixed)
Approx. Total Steps:    ~17,709             ~35,418
Approx. Step Speed:     ~15s/step           ~8s/step
Approx. Total Time:     ~74h                ~79h (ähnlich)

Smart Stopping:         patience=5, target_loss=0.4
Best Checkpoint:        12400 (eval_loss=0.950)
Start Mode:             --from-best (warm-start)
```

---

### Task 4: Commit

- [ ] **Step 1: Stage and commit**

```bash
git add scripts/train_hime.py scripts/train_generic.py
git commit -m "tune: LR 5e-5, dropout 0.05, grad_accum 8 for fine-tuning phase

Adjusts hyperparameters to overcome eval_loss plateau at 0.950:
- Learning rate: 2e-4 → 5e-5 (smaller steps for fine-tuning)
- LoRA dropout: 0 → 0.05 (regularization against overfitting)
- Gradient accumulation: 16 → 8 (faster steps, noisier gradients)
- Warmup: 5% ratio → 50 fixed steps (sufficient for fresh optimizer)

No version bump — hyperparameter tuning only, not an app change.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Notes

- **Unsloth Fast Path disabled:** Setting `lora_dropout=0.05` disables Unsloth's optimized LoRA fast path (which requires `dropout=0`). This may slightly increase step time. The regularization benefit outweighs the speed cost given the overfitting problem.

- **lora_alpha stays at 32:** The spec mentions `lora_alpha=16` in the "don't change" section, but the actual code has `LORA_ALPHA=32` in both scripts. Per spec instructions ("NICHT ändern"), the value remains at 32.

- **Only qwen32b affected in train_generic.py:** The `grad_accum` change in MODEL_CONFIGS applies only to the qwen32b entry. Other model configs retain their original values.

- **Training NOT started by this plan.** After commit, training can be launched manually with:
  ```bash
  conda activate hime
  python scripts/train_hime.py --from-best
  ```
