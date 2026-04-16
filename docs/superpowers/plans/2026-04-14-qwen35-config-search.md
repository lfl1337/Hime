# Qwen3.5-9B Config Search — Stable & Fast Autonomous Training

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Configure Hime-Vault folder structure. (2) Autonomously find the fastest stable training configuration for Qwen3.5-9B via adaptive config search. (3) Run full training indefinitely with the winner — monitoring everything, auto-recovering from degradation, writing scientific documentation throughout. User can sleep; system is fully autonomous.

**Architecture:**
- **Phase 1 — Config Search:** Test configs B→C→D→E→... (200 steps each) until a PASS config is found. Each new config derived from previous run's measured bottleneck.
- **Phase 2 — Autonomous Training:** Run winner config indefinitely. Monitor all system metrics every 30 s. On degradation: pause (save checkpoint), run new config search from current winner's params, resume with new winner.
- **Monitoring:** GPU VRAM, GPU%, Power, Temperature + CPU%, RAM, Swap — all logged every 30 s. Scientific paper updated after each config and periodically during full training.
- **User contract:** Start it → sleep → wake up to either active training or ongoing config test. Stop with explicit command only.

**Tech Stack:** Unsloth 4-bit NF4 QLoRA, HuggingFace SFTTrainer, nvidia-smi, PowerShell (RAM/Swap on Windows), conda run -n hime

---

## Context — What We Know

**Model:** Qwen/Qwen3.5-9B — hybrid GatedDeltaNet (SSM + attention layers), 4-bit NF4, LoRA.
**Hardware:** RTX 5090, 32607 MiB physical VRAM. Shared memory begins at >32607 MiB. Windows 11.
**Already active:** `use_gradient_checkpointing="unsloth"`, `optim="adamw_8bit"`, `--output-dir` support in trainer.

**Baseline Config A (Anlauf 3, 2026-04-13) — do NOT re-run:**
- `max_seq=2048, batch=1, grad_accum=8, lora_dropout=0.0`
- Speed: mean ~28 s/step (range 22–33 s)
- VRAM: baseline 26–28 GB, spikes 31.0–31.4 GB (95–96%) every 60–90 s
- GPU: 42–84%, Power 161–218 W (28–38% of 575 W TDP) → severely underutilised
- CPU/RAM/Swap: not measured (add to monitoring)
- Loss: Step 10=18.48 → 20=16.95 → 30=13.60 ✓ (healthy)
- Projected: ~11.5 days for 3 epochs — not viable

**Config B quick observation (4 steps):**
- Speed at step 4: 14 s/step (already faster than A's stable 22 s)
- VRAM baseline: 19.8 GB (61%) — 6–8 GB less than A
- GPU power: 292–302 W — much better utilisation

**Stability criteria (config search):**
- ✅ PASS: mean step time < 15 s AND VRAM peak < 32000 MiB AND no degradation over 150 steps
- ⚠️ MARGINAL: 15–20 s/step OR occasional VRAM peaks 30–32 GB
- ❌ FAIL: > 20 s/step sustained OR OOM OR monotonic speed degradation

**Degradation criteria (full training — triggers auto config search):**
- Step time rolling average (last 50 steps) exceeds 1.5× the winner config's measured mean
- VRAM peak > 31800 MiB sustained for 10+ consecutive readings (near-OOM zone)
- OOM error in log

**Test duration:** 200 steps per config. Steps 1–50: warmup (excluded from metrics). Steps 51–200: measurement window.

**Config chain:** B→C→D→E→... open-ended. Each derived from previous run's bottleneck. Paper updated at: ~step 30, ~step 100, after completion.

---

## Files

- **Create (Task 0):** Hime-vault folder structure (7 new folders + `.gitkeep`)
- **Modify (Task 0):** `Hime-vault/_index.md`
- **Modify (Task 0):** Hime vault MCP `vault_write` handler — add folder routing
- **Create (Task 0):** `scripts/monitor_system.sh` — combined system monitor (GPU+CPU+RAM+Swap)
- **Modify (Task 1+):** `scripts/training/configs/qwen35_9b.py`
- **Modify (Task 1+):** `reports/qwen35_config_search/report.md` — living scientific paper
- **Create (Task 1+):** `reports/qwen35_config_search/config_B.log`, `config_C.log`, ...
- **Create (Task 4):** `scripts/training_watchdog.sh` — auto-restart loop for full training

---

## Task 0: Setup — Vault Structure + System Monitor Script

### 0a: Hime-Vault Folder Structure

- [ ] **Step 1: Create folders with .gitkeep**

```bash
for dir in "10-Training" "20-Architecture" "30-Bugs-Solved" "40-Snippets" "50-Sessions" "60-Light-Novel" "70-Manga"; do
  mkdir -p "N:/Projekte/NiN/Hime/Hime-vault/$dir"
  touch "N:/Projekte/NiN/Hime/Hime-vault/$dir/.gitkeep"
done
```

- [ ] **Step 2: Update `Hime-vault/_index.md`**

```markdown
---
tags: [hime, index]
---

# Hime Knowledge Vault

> [!tip] Open this folder as Obsidian vault. Graph View shows all knowledge connections.

## Folder Structure

| Folder | Purpose |
|--------|---------|
| `00-Inbox/` | Unsorted / default writes |
| `10-Training/` | ML experiments: config search, loss curves, VRAM profiles, benchmarks |
| `20-Architecture/` | Architecture decisions, ADRs, design documents |
| `30-Bugs-Solved/` | Bugs with root cause + fix |
| `40-Snippets/` | Reusable code snippets |
| `50-Sessions/` | Session continuity logs |
| `60-Light-Novel/` | Translation memory, glossaries, character notes — light novels |
| `70-Manga/` | Translation memory, glossaries, character notes — manga |
| `series_1/` | RAG chunks — Watashi no Yuri wa Oshigoto desu! |
| `series_2/` | RAG chunks — Adachi to Shimamura |

## Series Index
- [[series_1/_series_index|Series 1 — Watashi no Yuri wa Oshigoto desu!]]
- [[series_2/_series_index|Series 2 — Adachi to Shimamura]]
```

- [ ] **Step 3: Locate Hime vault_write MCP handler and add folder routing**

Find the server:
```bash
find "N:/Projekte/NiN" -name "*.py" | xargs grep -l "vault_write" 2>/dev/null | grep -v "__pycache__\|hime_rag_mcp"
```

Read the file. Add folder routing function before the write handler:

```python
_TYPE_TO_FOLDER = {
    "session":  "50-Sessions",
    "decision": "20-Architecture",
    "bug":      "30-Bugs-Solved",
    "snippet":  "40-Snippets",
    "note":     "00-Inbox",
}

def _resolve_vault_folder(note_type: str, tags: list) -> str:
    tag_set = {t.lower() for t in (tags or [])}
    if tag_set & {"light-novel", "ln", "lightnovel"}:
        return "60-Light-Novel"
    if "manga" in tag_set:
        return "70-Manga"
    if tag_set & {"training", "experiment", "ml", "config-search"}:
        return "10-Training"
    if tag_set & {"architecture", "adr", "design"}:
        return "20-Architecture"
    return _TYPE_TO_FOLDER.get(note_type, "00-Inbox")
```

Use `_resolve_vault_folder(type, tags)` when constructing the output `.md` file path instead of always writing to `00-Inbox/`.

- [ ] **Step 4: Commit vault structure + MCP routing**

```bash
git add -f "Hime-vault/_index.md" "Hime-vault/10-Training/.gitkeep" \
  "Hime-vault/20-Architecture/.gitkeep" "Hime-vault/30-Bugs-Solved/.gitkeep" \
  "Hime-vault/40-Snippets/.gitkeep" "Hime-vault/50-Sessions/.gitkeep" \
  "Hime-vault/60-Light-Novel/.gitkeep" "Hime-vault/70-Manga/.gitkeep"
# add MCP server file if modified
git commit -m "feat(vault): Hime-vault taxonomy + MCP folder routing

Folders: 00-Inbox, 10-Training, 20-Architecture, 30-Bugs-Solved,
40-Snippets, 50-Sessions, 60-Light-Novel, 70-Manga
vault_write routes by type+tag instead of always 00-Inbox

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

### 0b: System Monitor Script

- [ ] **Step 5: Create `scripts/monitor_system.sh`**

Create `scripts/monitor_system.sh`:

```bash
#!/usr/bin/env bash
# Full system monitor — GPU (VRAM/Util/Power/Temp) + CPU% + RAM + Swap
# Usage: bash scripts/monitor_system.sh [interval_seconds]
# Output: one line per interval, tab-separated, parseable

INTERVAL=${1:-30}

while true; do
  TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

  # GPU metrics via nvidia-smi
  GPU_LINE=$(nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,power.draw,temperature.gpu \
    --format=csv,noheader,nounits 2>/dev/null | head -1)
  VRAM_USED=$(echo "$GPU_LINE" | awk -F',' '{print $1+0}')
  VRAM_TOTAL=$(echo "$GPU_LINE" | awk -F',' '{print $2+0}')
  GPU_UTIL=$(echo "$GPU_LINE" | awk -F',' '{print $3+0}')
  GPU_PWR=$(echo "$GPU_LINE" | awk -F',' '{print $4+0}')
  GPU_TEMP=$(echo "$GPU_LINE" | awk -F',' '{print $5+0}')
  VRAM_PCT=$(awk "BEGIN {printf \"%.0f\", $VRAM_USED/$VRAM_TOTAL*100}")

  # CPU + RAM + Swap via PowerShell (Windows)
  SYS_LINE=$(powershell -NoProfile -Command "
    \$cpu = (Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    \$os  = Get-WmiObject Win32_OperatingSystem
    \$ram_used = [math]::Round((\$os.TotalVisibleMemorySize - \$os.FreePhysicalMemory)/1MB, 1)
    \$ram_total = [math]::Round(\$os.TotalVisibleMemorySize/1MB, 1)
    \$pf  = Get-WmiObject Win32_PageFileUsage
    \$swap_used  = [math]::Round(\$pf.CurrentUsage/1024, 1)
    \$swap_alloc = [math]::Round(\$pf.AllocatedBaseSize/1024, 1)
    Write-Host \"\${cpu}|\${ram_used}|\${ram_total}|\${swap_used}|\${swap_alloc}\"
  " 2>/dev/null)

  CPU_PCT=$(echo "$SYS_LINE" | cut -d'|' -f1)
  RAM_USED=$(echo "$SYS_LINE" | cut -d'|' -f2)
  RAM_TOT=$(echo "$SYS_LINE" | cut -d'|' -f3)
  SWAP_USED=$(echo "$SYS_LINE" | cut -d'|' -f4)
  SWAP_ALLOC=$(echo "$SYS_LINE" | cut -d'|' -f5)

  # Flags
  FLAG=""
  [ "$VRAM_USED" -gt 31000 ] 2>/dev/null && FLAG="${FLAG} ❌VRAM-NEAROOM"
  [ "$VRAM_USED" -gt 29000 ] 2>/dev/null && [ -z "$FLAG" ] && FLAG="${FLAG} ⚠VRAM-HIGH"
  # Swap > 2 GB used is notable on a training machine
  SWAP_WARN=$(awk "BEGIN {print ($SWAP_USED > 2.0) ? \"1\" : \"0\"}" 2>/dev/null)
  [ "$SWAP_WARN" = "1" ] && FLAG="${FLAG} ⚠SWAP-ACTIVE"

  echo "[$TIMESTAMP] VRAM:${VRAM_USED}/${VRAM_TOTAL}MiB(${VRAM_PCT}%) GPU:${GPU_UTIL}% PWR:${GPU_PWR}W TEMP:${GPU_TEMP}°C | CPU:${CPU_PCT}% RAM:${RAM_USED}/${RAM_TOT}GB SWAP:${SWAP_USED}/${SWAP_ALLOC}GB${FLAG}"

  sleep "$INTERVAL"
done
```

- [ ] **Step 6: Commit monitor script**

```bash
git add scripts/monitor_system.sh
git commit -m "feat(monitoring): full system monitor — GPU+CPU+RAM+Swap in one line

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 1: Config B — 200-Step Test

**Rationale from Config A data:** Bottleneck = serial attention O(n²) at seq=2048 + batch=1. Fix: halve seq (4× cheaper attention) + double batch (2 parallel seqs). Effective batch unchanged at 8.

**Parameters:** `max_seq=1024, batch_size=2, grad_accum=4, lora_dropout=0.0`

**Files:**
- Modify: `scripts/training/configs/qwen35_9b.py`
- Create: `reports/qwen35_config_search/config_B.log`, `reports/qwen35_config_search/monitor_B.log`
- Modify: `reports/qwen35_config_search/report.md`

- [ ] **Step 1: Write Config B to qwen35_9b.py**

```python
"""Qwen3.5-9B — v2 Stage 1C translator."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=1024,       # [CFG-B] 4× less attention compute vs A's 2048 (O(n²) scaling)
    batch_size=2,       # [CFG-B] 2 parallel packed seqs → better tensor core utilisation
    grad_accum=4,       # [CFG-B] effective_batch = 2×4 = 8 (same as A)
    lora_dropout=0.0,   # Unsloth fast CUDA kernels
    trainer="unsloth",
    enable_thinking=False,
)
register(CONFIG)
```

- [ ] **Step 2: Start full system monitor (background, persistent)**

```bash
bash scripts/monitor_system.sh 30 | tee reports/qwen35_config_search/monitor_B.log
```
Note Monitor task ID.

- [ ] **Step 3: Launch Config B — 200 steps**

```bash
conda run -n hime python scripts/train_generic.py \
  --model qwen35-9b \
  --fresh \
  --max-steps 200 \
  --output-dir /tmp/qwen35_cfg_search/B \
  --log-file reports/qwen35_config_search/config_B.log
```
Note background task ID. Also start loss monitor:
```bash
tail -f reports/qwen35_config_search/config_B.log | \
  grep --line-buffered -E "'loss'|it/s\]|Error|OOM|Traceback|FERTIG"
```

- [ ] **Step 4a: Scientific paper update at ~step 30**

After steps 10/20/30 loss values arrive, update `reports/qwen35_config_search/report.md` Config B section with:
- Loss trend: faster/slower than Config A?
- Speed trend: stabilising at what value?
- VRAM baseline and first peak
- System metrics: CPU%, RAM, Swap (any surprises?)
- Early hypothesis: on track for PASS/MARGINAL/FAIL?

- [ ] **Step 4b: Scientific paper update at ~step 100**

After step 100 (50 stable measurement steps):
- Provisional mean/std/CV from steps 51–100
- Provisional VRAM max
- Provisional projected duration
- CPU/RAM/Swap observations (any bottleneck outside GPU?)
- Early verdict + Config C hypothesis if needed

- [ ] **Step 4c: Collect final metrics after step 200**

```bash
# Stats from stable phase (steps 51–200)
conda run -n hime python -c "
import re, statistics
log = open('reports/qwen35_config_search/config_B.log').read()
speeds = [float(m) for m in re.findall(r'(\d+\.\d+)s/it', log)][50:]
if speeds:
    mean = statistics.mean(speeds)
    print(f'n={len(speeds)} mean={mean:.2f}s std={statistics.stdev(speeds):.2f}s')
    print(f'CV={statistics.stdev(speeds)/mean*100:.1f}%')
    print(f'min={min(speeds):.2f}s max={max(speeds):.2f}s')
    print(f'Projected full training = {mean*35394/86400:.1f} days')
"

# All loss values
grep \"'loss'\" reports/qwen35_config_search/config_B.log

# VRAM peak from monitor
grep -E "VRAM" reports/qwen35_config_search/monitor_B.log | \
  awk -F'VRAM:' '{split($2,a,"/"); if(a[1]+0>peak) peak=a[1]+0} END {print "Peak VRAM:", peak, "MiB"}'

# RAM/Swap peak
grep "RAM:" reports/qwen35_config_search/monitor_B.log | tail -5
```

- [ ] **Step 5: Determine Config B verdict + design Config C if needed**

Apply criteria:
- **PASS** → go directly to Task 4 (full training)
- **MARGINAL/FAIL** → analyse which metric failed:
  - Speed > 15 s but VRAM OK → next config: increase batch or reduce seq further
  - VRAM spikes near-OOM → next config: reduce seq or batch
  - CPU bottleneck (>90% sustained) → investigate dataloader (DATALOADER_NUM_WORKERS)
  - Swap active → RAM pressure, consider reducing batch
  - Speed degrades monotonically → VRAM fragmentation, try very short seq + more batch

Document Config C parameters and rationale here.

- [ ] **Step 6: Final scientific paper update for Config B**

Complete Config B section in `reports/qwen35_config_search/report.md` with all fields (see report template below). Write at scientific level: hypothesis → method → results → analysis → conclusion.

- [ ] **Step 7: Write to both vaults**

**Hime-Vault** (tags: training, experiment, qwen35-9b, config-search → routes to 10-Training/):
```
Title: "Config B Results — max_seq=1024 batch=2 grad_accum=4"
Content: [full Config B paper section from report.md]
```

**Kioku-Vault** (folder: 10-Projects/Hime):
```
Title: "Qwen3.5-9B Config B — [VERDICT]"
Content: [1-paragraph summary: params, key metrics, verdict, next config hypothesis]
```

- [ ] **Step 8: Commit**

```bash
git add -f reports/qwen35_config_search/report.md reports/qwen35_config_search/config_B.log \
  scripts/training/configs/qwen35_9b.py
git commit -m "experiment(qwen35): Config B — max_seq=1024 batch=2 grad_accum=4 [VERDICT]"
```

---

## Task 2+: Config C, D, E, ... — Open-Ended Adaptive Search

*(Repeat for each config letter until PASS. Each config designed from previous run's measured bottleneck.)*

- [ ] **Step 1: Write config to qwen35_9b.py**

Use parameters from previous run's bottleneck analysis. Comment must include WHY each value was chosen:
```python
CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=<N>,       # [CFG-X] from Config Y data: bottleneck was Z, so ...
    batch_size=<B>,    # [CFG-X] reason: ...
    grad_accum=<G>,    # [CFG-X] effective_batch = B×G = 8
    lora_dropout=0.0,
    trainer="unsloth",
    enable_thinking=False,
)
```

- [ ] **Step 2: Start system monitor**

```bash
bash scripts/monitor_system.sh 30 | tee reports/qwen35_config_search/monitor_<X>.log
```

- [ ] **Step 3: Launch 200-step test**

```bash
conda run -n hime python scripts/train_generic.py \
  --model qwen35-9b --fresh --max-steps 200 \
  --output-dir /tmp/qwen35_cfg_search/<X> \
  --log-file reports/qwen35_config_search/config_<X>.log
```

- [ ] **Step 4: Three paper updates (step 30, step 100, final)**

Same as Task 1 Steps 4a/4b/4c.

- [ ] **Step 5: Verdict + design next config if needed**

- [ ] **Step 6: Vault writes (Hime + Kioku)**

- [ ] **Step 7: Commit**

**If 4+ configs MARGINAL/FAIL without improvement:** Stop search. Write escalation note to both vaults (why RTX 5090 / Qwen3.5-9B / current setup may be hitting a hard limit). Escalate to user.

---

## Task 4: Full Autonomous Training with Winner Config

- [ ] **Step 1: Set winner config in qwen35_9b.py with annotation**

```python
CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=<W>,       # [WINNER-CFG-X] selected YYYY-MM-DD: Xs/step, Y days projected
    batch_size=<W>,
    grad_accum=<W>,
    lora_dropout=0.0,
    trainer="unsloth",
    enable_thinking=False,
)
```

- [ ] **Step 2: Create `scripts/training_watchdog.sh`**

This script: launches training → monitors for degradation → auto re-searches config if degraded → resumes. Runs until user kills it.

```bash
#!/usr/bin/env bash
# Training watchdog — autonomous training with auto config search on degradation.
# Usage: bash scripts/training_watchdog.sh
# Stop: Ctrl+C or kill the process.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

WINNER_SPEED=<FILL_IN>        # measured mean s/step of winner config
DEGRADATION_FACTOR=1.5        # trigger re-search if rolling average > WINNER_SPEED × factor
MONITOR_LOG="$PROJECT_DIR/logs/training/watchdog_monitor.log"
TRAINING_LOG=""

mkdir -p "$PROJECT_DIR/logs/training"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$MONITOR_LOG"; }

start_training() {
  TRAINING_LOG="$PROJECT_DIR/logs/training/qwen35_9b_$(date +%Y%m%d_%H%M).log"
  log "Starting training → $TRAINING_LOG"
  conda run -n hime python "$SCRIPT_DIR/train_generic.py" \
    --model qwen35-9b \
    --log-file "$TRAINING_LOG" &
  TRAINING_PID=$!
  log "Training PID: $TRAINING_PID"
}

check_degradation() {
  # Get rolling average of last 50 s/it values from training log
  if [ -z "$TRAINING_LOG" ] || [ ! -f "$TRAINING_LOG" ]; then return 1; fi
  AVG=$(grep -oE '[0-9]+\.[0-9]+s/it' "$TRAINING_LOG" | tail -50 | \
    awk -F's' '{sum+=$1; n++} END {if(n>10) print sum/n; else print 0}')
  THRESHOLD=$(awk "BEGIN {print $WINNER_SPEED * $DEGRADATION_FACTOR}")
  DEGRADED=$(awk "BEGIN {print ($AVG > $THRESHOLD && $AVG > 0) ? 1 : 0}")
  if [ "$DEGRADED" = "1" ]; then
    log "⚠ DEGRADATION DETECTED: rolling avg=${AVG}s/step > threshold=${THRESHOLD}s/step"
    return 0  # degraded
  fi
  return 1  # ok
}

main_loop() {
  log "=== Training Watchdog Started ==="
  log "Winner config speed: ${WINNER_SPEED}s/step | Degradation threshold: ×${DEGRADATION_FACTOR}"
  start_training

  while true; do
    sleep 60  # check every minute

    # Check if training process died
    if ! kill -0 "$TRAINING_PID" 2>/dev/null; then
      log "Training process ended (PID $TRAINING_PID). Checking log for completion..."
      if grep -q "FERTIG\|Training abgeschlossen" "$TRAINING_LOG" 2>/dev/null; then
        log "✅ Training completed normally."
        exit 0
      else
        log "❌ Training died unexpectedly. Restarting..."
        start_training
        continue
      fi
    fi

    # Check for degradation
    if check_degradation; then
      log "Stopping training to search for better config..."
      kill "$TRAINING_PID" 2>/dev/null || true
      wait "$TRAINING_PID" 2>/dev/null || true
      log "Training stopped. Triggering config search... (manual step — update config then restart watchdog)"
      # Note: Config search is triggered by Claude; watchdog signals the need.
      # Write a flag file that Claude monitors:
      echo "DEGRADATION_DETECTED $(date)" > "$PROJECT_DIR/logs/training/watchdog_degradation.flag"
      exit 2  # exit code 2 = degradation detected
    fi
  done
}

main_loop
```

- [ ] **Step 3: Start system monitor + training watchdog**

```bash
# System monitor (persistent):
bash scripts/monitor_system.sh 30 | tee logs/training/monitor_full.log

# Watchdog (will run training internally):
bash scripts/training_watchdog.sh
```

Also start Claude-side monitors:
- Loss monitor: `tail -f [current training log] | grep --line-buffered -E "'loss'|Error|OOM|FERTIG"`
- Watchdog flag monitor: `tail -f logs/training/watchdog_degradation.flag` (alerts Claude if degradation)

- [ ] **Step 4: Verify first 50 steps healthy**

Check: loss falling, VRAM < 32000 MiB, no CPU/RAM/Swap anomalies.

- [ ] **Step 5: Periodic vault updates during full training**

Every 500 steps (or ~2 hours at winner speed), update both vaults with:
- Current step, current loss
- VRAM/CPU/RAM/Swap status
- Estimated completion time
- Any notable observations

- [ ] **Step 6: On degradation detection (watchdog exits with code 2)**

1. Read `logs/training/watchdog_degradation.flag`
2. Note: what step degradation started, what the speed was
3. Update scientific paper with degradation event
4. Run Task 2+ (new config search) starting from current winner params ± small adjustments
5. Once new winner found: update `scripts/training_watchdog.sh` WINNER_SPEED and restart

- [ ] **Step 7: Final commit when user stops training**

```bash
git add -f reports/qwen35_config_search/report.md scripts/training/configs/qwen35_9b.py \
  scripts/training_watchdog.sh scripts/monitor_system.sh
git commit -m "perf(qwen35): [final summary — winner config, total steps, days trained]"
```

---

## Scientific Paper Format (for `reports/qwen35_config_search/report.md`)

Each config section must follow this structure:

```markdown
## Config X — [short name] (YYYY-MM-DD)

**Parameters:** `max_seq=N, batch_size=B, grad_accum=G, lora_dropout=0.0`
**Effective batch:** 8 | **Tokens/optimizer step:** N×B = Z

### 1. Hypothesis
[Why these values? What bottleneck from the previous config are we addressing?
Reference specific measured values: "Config Y showed mean=Xs/step with GPU at Y%W,
indicating Z bottleneck because..."]

### 2. Expected Outcomes
- Speed prediction: [formula/reasoning, e.g. "attention O(n²): 4× faster at seq=1024 vs 2048;
  SSM O(n): 2× faster; combined ≈ 2.5× → ~11 s/step"]
- VRAM prediction: [reasoning]
- GPU utilisation prediction: [reasoning]

### 3. Results

#### Training Curve
| Step | Loss | grad_norm | LR |
|------|------|-----------|-----|
[fill from log]

#### Speed Profile (steps 51–200)
| Metric | Value |
|--------|-------|
| Mean | Xs/step |
| Std | Ys/step |
| CV | Z% |
| Min | As/step |
| Max | Bs/step |
| Trend | stable / degrading / improving |

#### System Metrics (observed range)
| Metric | Min | Max | Mean | Notes |
|--------|-----|-----|------|-------|
| VRAM (MiB) | | | | |
| GPU % | | | | |
| GPU Power (W) | | | | |
| GPU Temp (°C) | | | | |
| CPU % | | | | |
| RAM (GB) | | | | |
| Swap (GB) | | | | |

### 4. Analysis
[Compare expected vs actual. Explain deviations. What did this run reveal about the
model/hardware interaction? E.g. "GPU power increased to 302W (52% TDP) confirming
better compute utilisation. VRAM baseline dropped 7 GB vs Config A, consistent with
shorter activation tensors at seq=1024. However, spikes still reached 96%..."]

### 5. Projected Full Training
35394 × Xs = N days (vs Config A's 11.5 days: Z× speedup)

### 6. Verdict: ✅ PASS / ⚠️ MARGINAL / ❌ FAIL

**Bottleneck for next config (if not PASS):**
[Specific observation that drives the next design decision]
```
