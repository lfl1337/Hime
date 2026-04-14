# Qwen3.5-9B Config Search — Stable & Fast Training

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Autonomously find the fastest stable training configuration for Qwen3.5-9B on RTX 5090 (32 GB VRAM), then launch full training.

**Architecture:** Try 3 candidate configs (B→C→D) each for 100 optimizer steps with full instrumentation. Evaluate on: mean step time, VRAM peak, speed stability (CV), loss curve. Write findings to a living report after each run. Stop as soon as a config meets the stability+speed criteria.

**Tech Stack:** Unsloth 4-bit NF4 QLoRA, HuggingFace SFTTrainer, nvidia-smi monitoring, conda run -n hime, bash monitoring loops

---

## Context

**Model:** Qwen/Qwen3.5-9B — hybrid GatedDeltaNet architecture (NOT pure attention, NOT pure Mamba).  
Has both standard attention layers AND SSM/linear-attention (GatedDeltaNet) layers.  
Physical VRAM: 32607 MiB. Shared memory begins at >32607 MiB.  
Gradient checkpointing: already active (`use_gradient_checkpointing="unsloth"` in apply_lora).  
Optimizer: adamw_8bit (already minimizes optimizer state VRAM).

**Baseline — Anlauf 3 (Config A — DONE, do not re-run):**  
`max_seq=2048, batch=1, grad_accum=8, lora_dropout=0.0`  
- Step speed: 22–33 s/step (mean ~28 s), oscillating — NOT monotonically degrading  
- VRAM: 81–96% peaks (26–31.3 GB), regular spikes every 60–90 s  
- Loss: Step 10=18.48, Step 20=16.95, Step 30=13.60 ✓ (healthy descent)  
- Projected: ~11–13 days for 3 epochs → **not viable**

**Root cause of slow speed:** At batch=1, max_seq=2048, the GPU processes one packed sequence at a time.  
Attention layers scale O(n²) in sequence length → 4× more attention compute vs seq=1024.  
SSM layers scale O(n) → 2× more vs seq=1024.  
Result: underutilized tensor cores, bandwidth-bound ops.

**Configs to test:**

| Config | max_seq | batch | grad_accum | eff_batch | tokens/optimizer_step | Predicted speed |
|--------|---------|-------|------------|-----------|----------------------|-----------------|
| A (baseline) | 2048 | 1 | 8 | 8 | 16384 | ~28 s ❌ |
| B | 1024 | 2 | 4 | 8 | 8192 | ~14–18 s |
| C | 1024 | 4 | 2 | 8 | 8192 | ~10–14 s |
| D | 512  | 8 | 1 | 8 | 4096 | ~6–10 s |

Note: all configs maintain effective_batch=8 (same gradient quality).  
Total optimizer steps = 35394 (3 epochs, 94379 training examples) for all configs.

**Stability criteria (pass/fail per config):**
- ✅ PASS: mean step time < 15 s AND VRAM peak < 32000 MiB AND no speed degradation trend
- ⚠️ MARGINAL: 15–20 s/step OR VRAM peaks 30000–32000 MiB (occasional)
- ❌ FAIL: speed > 20 s/step sustained OR OOM OR VRAM stays > 32000 MiB

**Stop early if Config B already passes** — no need to test C and D.

---

## Files

- **Modify:** `scripts/training/configs/qwen35_9b.py` — change params per config
- **Modify:** `scripts/training/trainers/unsloth_trainer.py` — add `--output-dir` support (line 53)
- **Create:** `reports/qwen35_config_search/report.md` — living report (updated after each run)
- **Create:** `reports/qwen35_config_search/config_B.log` — training log for Config B
- **Create:** `reports/qwen35_config_search/config_C.log` — training log for Config C  
- **Create:** `reports/qwen35_config_search/config_D.log` — training log for Config D

---

## Task 1: Setup — Patch trainer + create report template

**Files:**
- Modify: `scripts/training/trainers/unsloth_trainer.py:53-54`
- Create: `reports/qwen35_config_search/report.md`

- [ ] **Step 1: Add --output-dir support to unsloth_trainer.py**

Read `scripts/training/trainers/unsloth_trainer.py` lines 48-75.  
Replace:
```python
        output_dir = models_dir / "lora" / config.lora_dir
        output_dir.mkdir(parents=True, exist_ok=True)
```
With:
```python
        _cli_output_dir = getattr(args, 'output_dir', None)
        output_dir = Path(_cli_output_dir) if _cli_output_dir else (models_dir / "lora" / config.lora_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 2: Verify no stale training process is running**

Run:
```bash
wmic process where "name='python.exe'" get ProcessId,CommandLine 2>/dev/null | head -10
```
Expected: empty output (no Python processes). If any exist, investigate before proceeding.

- [ ] **Step 3: Create living report with Config A pre-filled**

Create `reports/qwen35_config_search/report.md` using the template in Task 1 Step 3 block below.  
(Full content provided — do not abbreviate.)

```markdown
# Qwen3.5-9B Training Config Search — Living Report

**Hardware:** RTX 5090 (32607 MiB VRAM) | **Model:** Qwen/Qwen3.5-9B (hybrid GatedDeltaNet, 4-bit NF4 QLoRA)  
**Fixed params:** LORA_RANK=16, LORA_ALPHA=32, LR=5e-5, WARMUP=50, EPOCHS=3, GRAD_NORM_CLIP=0.5  
**Dataset:** 94379 training + 10487 eval examples | **Total optimizer steps:** 35394  
**Last updated:** 2026-04-14

---

## Results Table

| Config | max_seq | batch | grad_accum | Speed (s/step) | Speed CV | VRAM peak (MiB) | VRAM stable | Loss@10 | Loss@30 | Loss@100 | Verdict |
|--------|---------|-------|------------|----------------|----------|-----------------|-------------|---------|---------|----------|---------|
| A | 2048 | 1 | 8 | ~28 (22–33) | ~17% | 31380 | 81–88% | 18.48 | 13.60 | n/a | ❌ Too slow |
| B | 1024 | 2 | 4 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| C | 1024 | 4 | 2 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| D | 512  | 8 | 1 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

---

## Config A — Baseline (Anlauf 3, 2026-04-13)

**Parameters:** `max_seq=2048, batch_size=1, grad_accum=8, lora_dropout=0.0`  
**Effective batch:** 8 | **Tokens/optimizer step:** 16384

### Training Curve
| Step | Loss | grad_norm | LR |
|------|------|-----------|-----|
| 10 | 18.48 | 1.556 | 9e-06 |
| 20 | 16.95 | 1.130 | 1.9e-05 |
| 30 | 13.60 | 1.177 | 2.9e-05 |

### VRAM Profile
- Baseline (idle training): 26340–28801 MiB (81–88%)
- Peak spikes: 31027–31380 MiB (95–96%)
- Pattern: regular spikes every 60–90 s with low GPU% (memory operations)
- Temperature: not measured

### Speed Profile
- Compilation steps 1–8: 22–34 s/step (CUDA kernel compile)
- Stabilized steps 10–37: 22–33 s/step, mean ≈ 28 s
- Coefficient of variation: ~17% — high oscillation
- No clear monotonic degradation (initial interpretation incorrect)

### Projected Duration
35394 steps × 28 s = 990832 s ≈ **11.5 days** ❌

### Analysis
Loss descent: healthy (-8% per 10 steps at warmup, accelerating). Gradient norm: stable (1.1–1.6).  
Primary bottleneck: batch=1 + seq=2048 → serial processing, attention O(n²) at max context.  
VRAM spikes at optimizer steps (low GPU% signature) suggest optimizer state update buffers.

### Verdict
**❌ NOT VIABLE** — 11.5 days per 3-epoch run unacceptable. Config B+ required.

---

## Config B — Short Seq, 2× Batch (TBD)

**Parameters:** `max_seq=1024, batch_size=2, grad_accum=4, lora_dropout=0.0`  
**Effective batch:** 8 | **Tokens/optimizer step:** 8192  
**Theoretical speedup:** Attention O(n²): 4× faster. SSM O(n): 2× faster. Estimate: 1.6–2× → 14–18 s/step.

### Hypothesis
Halving sequence length reduces attention compute 4×. Doubling batch allows 2 sequences to be processed in parallel, improving tensor core utilization. VRAM footprint for activations ≈ proportional to batch×seq → same total (2×1024 = 1×2048) but shorter context means smaller KV-related buffers.

### Training Curve
*(to be filled)*

### VRAM Profile
*(to be filled)*

### Speed Profile
*(to be filled)*

### Projected Duration
*(to be filled)*

### Verdict
*(to be filled)*

---

## Config C — Higher Batch, Short Seq (TBD)

**Parameters:** `max_seq=1024, batch_size=4, grad_accum=2, lora_dropout=0.0`  
**Effective batch:** 8 | **Tokens/optimizer step:** 8192  
**Theoretical speedup:** Same attention budget as B, but 4 parallel sequences → better warp utilization.

*(full template same as Config B — filled after run)*

---

## Config D — Very Short, Max Batch (TBD)

**Parameters:** `max_seq=512, batch_size=8, grad_accum=1, lora_dropout=0.0`  
**Effective batch:** 8 | **Tokens/optimizer step:** 4096  
**Risk:** seq=512 may truncate long training examples, hurting translation quality.

*(full template same as Config B — filled after run)*

---

## Winner Config

*(to be filled after search completes)*

**Winner:** TBD  
**Full training projected duration:** TBD  
**Launch command:**
```bash
conda run -n hime python scripts/train_generic.py --model qwen35-9b --log-file logs/training/qwen35_9b_full_YYYYMMDD.log
```
```

- [ ] **Step 4: Commit setup**

```bash
git add scripts/training/trainers/unsloth_trainer.py reports/qwen35_config_search/report.md
git commit -m "feat(training): add --output-dir support to unsloth trainer, add config search report"
```

---

## Task 2: Config B — max_seq=1024, batch=2, grad_accum=4

**Files:**
- Modify: `scripts/training/configs/qwen35_9b.py`
- Create: `reports/qwen35_config_search/config_B.log`

- [ ] **Step 1: Update qwen35_9b.py with Config B**

Write `scripts/training/configs/qwen35_9b.py`:
```python
"""Qwen3.5-9B — v2 Stage 1C translator (hybrid; Base-Training pending compat-check)."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=1024,       # [CFG-B] 2048→1024 — 4× less attention compute (O(n²))
    batch_size=2,       # [CFG-B] 1→2 — process 2 packed seqs in parallel
    grad_accum=4,       # [CFG-B] 8→4 — effective_batch = 2×4 = 8 (unchanged)
    lora_dropout=0.0,   # enables Unsloth fast CUDA kernels
    trainer="unsloth",
    enable_thinking=False,
)
register(CONFIG)
```

- [ ] **Step 2: Start VRAM+Temp monitor**

Start a persistent background monitor:
```bash
while true; do
  nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,power.draw,temperature.gpu \
    --format=csv,noheader,nounits | \
  awk -F',' '{
    used=$1+0; total=$2+0; util=$3+0; pwr=$4+0; temp=$5+0;
    pct=used/total*100;
    flag="";
    if(used>31000) flag=" ❌ NEAR-OOM";
    else if(used>29000) flag=" ⚠ HIGH";
    printf "VRAM:%d/%d(%.0f%%) GPU:%d%% PWR:%.0fW TEMP:%d°C%s\n",used,total,pct,util,pwr,temp,flag
  }';
  sleep 30;
done
```
Note the task ID.

- [ ] **Step 3: Launch Config B training (100 steps)**

```bash
conda run -n hime python scripts/train_generic.py \
  --model qwen35-9b \
  --fresh \
  --max-steps 100 \
  --output-dir /tmp/qwen35_cfg_search/B \
  --log-file reports/qwen35_config_search/config_B.log
```
Run in background, note task ID.

- [ ] **Step 4: Wait for step 10 loss (first logging event), verify training started**

Expected first loss event: ~3–5 minutes after start.  
Monitor `reports/qwen35_config_search/config_B.log` with:
```bash
tail -f reports/qwen35_config_search/config_B.log | grep --line-buffered -E "'loss'|Error|OOM|Traceback"
```

- [ ] **Step 5: Collect metrics after 100 steps complete**

After training finishes, run:
```bash
# Extract all loss values
grep "'loss'" reports/qwen35_config_search/config_B.log

# Extract step speeds (last 20 steps = stabilized)
grep -E "\| [0-9]+/35394" reports/qwen35_config_search/config_B.log | tail -20

# Calculate mean and variance manually from the s/it values
```

Compute:
- `mean_speed` = mean of s/it values from steps 20–100
- `max_speed` = max s/it (worst case)
- `min_speed` = min s/it
- `cv` = std/mean × 100% (coefficient of variation)
- `vram_peak` = max VRAM reading from monitor
- `vram_stable` = typical VRAM range (not spike)
- `max_temp` = max temperature reading

- [ ] **Step 6: Update report.md with Config B results**

Fill in the Config B section of `reports/qwen35_config_search/report.md`:
- Results table row
- Training curve (all loss values)
- VRAM profile
- Speed profile  
- Projected duration: `mean_speed × 35394 / 3600 / 24` days
- Verdict: PASS / MARGINAL / FAIL based on criteria in Context section

- [ ] **Step 7: Decision — proceed to Config C?**

If Config B verdict is **PASS** (< 15 s/step AND VRAM < 32000 MiB stable): skip Tasks 3 and 4, go to Task 5.  
If **MARGINAL or FAIL**: proceed to Task 3 (Config C).

- [ ] **Step 8: Commit Config B results**

```bash
git add reports/qwen35_config_search/report.md reports/qwen35_config_search/config_B.log scripts/training/configs/qwen35_9b.py
git commit -m "experiment(qwen35): Config B results — max_seq=1024 batch=2 grad_accum=4"
```

---

## Task 3: Config C — max_seq=1024, batch=4, grad_accum=2

*(Only if Config B is MARGINAL or FAIL)*

**Files:**
- Modify: `scripts/training/configs/qwen35_9b.py`
- Create: `reports/qwen35_config_search/config_C.log`

- [ ] **Step 1: Update qwen35_9b.py with Config C**

```python
"""Qwen3.5-9B — v2 Stage 1C translator (hybrid; Base-Training pending compat-check)."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=1024,       # [CFG-C] short sequences for speed
    batch_size=4,       # [CFG-C] 4× parallel seqs → better warp utilization
    grad_accum=2,       # [CFG-C] effective_batch = 4×2 = 8 (unchanged)
    lora_dropout=0.0,
    trainer="unsloth",
    enable_thinking=False,
)
register(CONFIG)
```

- [ ] **Step 2: Restart VRAM monitor if stopped**

Same command as Task 2 Step 2.

- [ ] **Step 3: Launch Config C training (100 steps)**

```bash
conda run -n hime python scripts/train_generic.py \
  --model qwen35-9b \
  --fresh \
  --max-steps 100 \
  --output-dir /tmp/qwen35_cfg_search/C \
  --log-file reports/qwen35_config_search/config_C.log
```

- [ ] **Step 4: Collect metrics after 100 steps**

Same procedure as Task 2 Step 5, but reading from `config_C.log`.

- [ ] **Step 5: Update report.md with Config C results**

Same procedure as Task 2 Step 6, filling Config C section.

- [ ] **Step 6: Decision — proceed to Config D?**

If Config C verdict is **PASS**: skip Task 4, go to Task 5.  
If **MARGINAL or FAIL**: proceed to Task 4 (Config D).

- [ ] **Step 7: Commit Config C results**

```bash
git add reports/qwen35_config_search/report.md reports/qwen35_config_search/config_C.log scripts/training/configs/qwen35_9b.py
git commit -m "experiment(qwen35): Config C results — max_seq=1024 batch=4 grad_accum=2"
```

---

## Task 4: Config D — max_seq=512, batch=8, grad_accum=1

*(Only if both B and C are MARGINAL or FAIL)*

**Files:**
- Modify: `scripts/training/configs/qwen35_9b.py`
- Create: `reports/qwen35_config_search/config_D.log`

- [ ] **Step 1: Update qwen35_9b.py with Config D**

```python
"""Qwen3.5-9B — v2 Stage 1C translator (hybrid; Base-Training pending compat-check)."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=512,        # [CFG-D] minimal seq — 16× less attention vs 2048
    batch_size=8,       # [CFG-D] maximum batch for GPU utilization
    grad_accum=1,       # [CFG-D] no accumulation — effective_batch = 8×1 = 8
    lora_dropout=0.0,
    trainer="unsloth",
    enable_thinking=False,
)
register(CONFIG)
```

- [ ] **Step 2: Launch Config D training (100 steps)**

```bash
conda run -n hime python scripts/train_generic.py \
  --model qwen35-9b \
  --fresh \
  --max-steps 100 \
  --output-dir /tmp/qwen35_cfg_search/D \
  --log-file reports/qwen35_config_search/config_D.log
```

- [ ] **Step 3: Collect metrics and update report**

Same procedure as Task 2 Steps 5–6.

- [ ] **Step 4: Commit Config D results**

```bash
git add reports/qwen35_config_search/report.md reports/qwen35_config_search/config_D.log scripts/training/configs/qwen35_9b.py
git commit -m "experiment(qwen35): Config D results — max_seq=512 batch=8 grad_accum=1"
```

---

## Task 5: Launch Full Training with Winner Config

**Files:**
- Modify: `scripts/training/configs/qwen35_9b.py` — set to winner params
- Create: `logs/training/qwen35_9b_run4_YYYYMMDD_HHMM.log`

- [ ] **Step 1: Set winner config in qwen35_9b.py**

Pick the fastest config that PASSed the stability criteria.  
If multiple configs pass, pick the fastest (lowest mean step time).  
Update `qwen35_9b.py` with winner params and add comment:
```python
# [WINNER-CONFIG] Selected YYYY-MM-DD after config search:
# Config X: max_seq=N, batch=B, grad_accum=G → M s/step, V MiB peak
```

- [ ] **Step 2: Clear stale test checkpoints**

```bash
rm -rf /tmp/qwen35_cfg_search/
```

The real checkpoint at `modelle/lora/Qwen3.5-9B/checkpoint/` has step-20 from Anlauf 3.  
Decision: use `--fresh` (ignore Anlauf 3 checkpoint) since it was trained at different config.

- [ ] **Step 3: Start full training with monitoring**

```bash
LOG="logs/training/qwen35_9b_run4_$(date +%Y%m%d_%H%M).log"
conda run -n hime python scripts/train_generic.py \
  --model qwen35-9b \
  --fresh \
  --log-file "$LOG"
```
Run in background, note task ID.

Start VRAM monitor (Task 2 Step 2 command) and loss monitor:
```bash
tail -f "$LOG" | grep --line-buffered -E "'loss'|Error|OOM|Traceback|FERTIG"
```

- [ ] **Step 4: Verify first 30 steps — loss falling, VRAM stable**

Expected at step 30: loss < 15, VRAM peaks < 32000 MiB.  
If OK → training is running, report to user.

- [ ] **Step 5: Finalize report.md with winner section**

Update report.md winner section:
- Winner config parameters
- Projected full training duration
- Launch timestamp
- Link to live log file

- [ ] **Step 6: Vault + commit**

```bash
git add scripts/training/configs/qwen35_9b.py reports/qwen35_config_search/report.md
git commit -m "perf(qwen35): launch full training with winner config [CONFIG-X]"
```

Write vault entry via `mcp__vault-rag__vault_write`:
```
# Qwen3.5-9B Config Search — Winner
Datum: 2026-04-14 | Projekt: Hime | Tags: training, qwen35, config-search
Winner config: [FILL IN], mean step time: [FILL IN] s/step, projected: [FILL IN] days
Config A (baseline) was ~28 s/step = 11.5 days — unusable.
Context: RTX 5090 32 GB, batch_size/max_seq tradeoff, GatedDeltaNet hybrid architecture.
```
