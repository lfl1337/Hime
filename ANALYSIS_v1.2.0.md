# Hime v1.2.0 — Post-Implementation Analysis

_Generated: 2026-04-08_

## Executive Summary

**What got done:** approx 18 of 27 planned workstream tasks completed or partially completed
- WS1 (Security): 4/6 done, 2/6 partial, 0/6 missing
- WS2 (Pipeline): 6/6 done (1 structural deviation — pipeline lives in `pipeline/` package as `run_pipeline()` coroutine, not `services/pipeline.py` with a `HimePipeline` class)
- WS3 (UI/UX): 3/6 done, 3/6 partial, 0/6 missing
- WS4 (System Check): paths.py, .env.example, AUDIT_REPORT.md done; 11 scripts and 1 Tauri source file still have hardcoded paths — overall partial

**Critical issues found:** 3

1. **Training regression (CRITICAL)** — The v1.2.0 run triggered a full training restart instead of resuming from step 14,423. Approximately 14,423 training steps and the best-known adapter weights (eval_loss ~0.9500) were lost. The current run is at step ~600/35,415 with an ETA of ~778 hours remaining.

2. **Epub path traversal bypass (HIGH)** — `epub_service.py`'s `_validate_epub_path()` correctly checks `is_relative_to()`, but `import_epub()` only calls it `if allowed_root` is provided — callers that omit `allowed_root` bypass the check entirely. The default is `None`, making the protection opt-in rather than mandatory.

3. **ModelStatusDashboard orphan (MEDIUM)** — `ModelStatusDashboard.tsx` was implemented by WS3 but is never mounted in any running view. Users cannot see model health status despite the component being fully functional.

**Top 3 urgent actions:**
1. Do NOT restart the training run again — let the current run continue from checkpoint-550. Investigate why `--resume` was not passed during the v1.2.0 run and add auto-resume logic to prevent recurrence.
2. Fix the epub path traversal bypass: make `allowed_root` required in `import_epub()`, or default it to `paths.EPUB_WATCH_DIR` so validation always runs.
3. Mount `ModelStatusDashboard` in the Settings or Translator view so model health is visible to users.

---

## Git State

### Recent Commits (last 25)

```
f5fe378 merge(ws4): system cleanup — centralized paths, no hardcoded paths, indexes, docs
8056c18 merge(ws2): pipeline overhaul — prompt templates, model_manager, graceful degradation, path audit
d2a888e docs: generate v1.2.0 audit report with hardcoded paths, indexes, and code quality findings
b3730ab docs: add project README with setup instructions and architecture overview
12285ae docs: update CLAUDE.md for v1.2.0 — pipeline architecture, path config, port registry
0a81530 docs: add comprehensive .env.example at project root for disk migration prep
cbfd13e refactor(training): replace hardcoded paths with CLI args and env var fallbacks
ed37f2d fix: remove hardcoded path in DB seed, add missing indexes for chapters/paragraphs
18a7dc9 fix: replace hardcoded C:\Projekte\Hime paths in config.py with core/paths.py
06183ca feat(ui): extend model polling to support all 6 pipeline models
b5ec1c0 feat: add centralized path resolution module (core/paths.py) for disk migration prep
6dca5a3 feat(ui): add offline placeholder for unavailable models in comparison view
57e8f3f feat(pipeline): lower Stage 1 minimum to 1 model, add model_unavailable events
60c422f feat(ui): improve offline-first UX with descriptive pipeline hints
71a02e7 feat(ui): integrate Stage 1 streaming panel into translation workspace
9f3e284 chore(security): add Dependabot config for weekly dependency updates
336f732 feat(ui): add ModelStatusDashboard with health, latency, and loaded model display
85e5e14 fix(security): add path traversal prevention to EPUB import with symlink checks
e4c8328 feat(pipeline): add model_manager service with health checks for all 6 pipeline models
a7776fc feat(ui): add Stage 1 streaming panel with 3 model cards, offline badges, and collapse
74c0649 feat(security): add Windows Job Objects, timeout, and audit logging to training subprocess
6cd1205 feat(ui): handle model_unavailable pipeline event in WebSocket hook
01e409c refactor(pipeline): externalize prompt templates to editable files with inline fallback
9d5ad03 fix(ui): correct Gemma model name from 27B to 12B
4c199c4 fix(security): add input validation bounds to epub and training endpoints
```

**Note:** All 25 commits shown are part of the v1.2.0 run. The run produced 25 commits total,
including 2 merge commits (WS4 at HEAD, WS2 at HEAD~1). WS1 and WS3 commits were made directly
to main without merge commits.

### Files Modified by v1.2.0 Run

Files changed across the full v1.2.0 run (all 25 commits), grouped by workstream:

#### Workstream 1 (Security) — files actually modified:
- `app/backend/app/routers/training.py` — input validation bounds (4c199c4)
- `app/backend/app/services/epub_service.py` — path traversal prevention with symlink checks (85e5e14)
- `app/backend/app/services/training_runner.py` — Windows Job Objects, timeout, audit logging (74c0649)
- `.github/dependabot.yml` — new: Dependabot config for weekly dependency updates (9f3e284)

#### Workstream 2 (Pipeline) — files actually modified:
- `app/backend/app/pipeline/prompts.py` — externalize prompt templates to txt files (01e409c)
- `app/backend/app/pipeline/runner.py` — lower Stage 1 minimum to 1 model, model_unavailable events (57e8f3f)
- `app/backend/app/services/model_manager.py` — new: model health checks for all 6 pipeline models (e4c8328)
- `app/backend/app/prompts/stage1_translate.txt` — new: externalized prompt template
- `app/backend/app/prompts/stage2_refine.txt` — new: externalized prompt template
- `app/backend/app/prompts/stage3_polish.txt` — new: externalized prompt template
- `app/backend/app/prompts/consensus_merge.txt` — new: externalized prompt template
- `app/backend/app/prompts/verify_bilingual.txt` — new: externalized prompt template
- `app/backend/tests/test_model_manager.py` — new: model_manager tests (merge commit 8056c18)
- `app/backend/tests/test_pipeline.py` — new: pipeline tests (merge commit 8056c18)
- `scripts/train_hime.py` — hardcoded paths replaced, CLI args added (cbfd13e)
- `scripts/train_generic.py` — hardcoded paths replaced, CLI args added (cbfd13e)

#### Workstream 3 (UI/UX) — files actually modified:
- `app/frontend/src/components/epub/TranslationWorkspace.tsx` — Stage1Panel integration (71a02e7)
- `app/frontend/src/components/comparison/ModelPanel.tsx` — offline placeholder for unavailable models (6dca5a3)
- `app/frontend/src/hooks/useModelPolling.ts` — extended to all 6 pipeline models (06183ca)
- `app/frontend/src/components/Stage1Panel.tsx` — new: Stage 1 streaming panel (a7776fc)
- `app/frontend/src/components/ModelStatusDashboard.tsx` — new: model health/latency dashboard (336f732)
- `app/frontend/src/hooks/usePipeline.ts` — handle model_unavailable WebSocket event (6cd1205)
- (UI text/hint improvements — 60c422f, 9d5ad03)

#### Workstream 4 (System Check) — files actually modified:
- `app/backend/app/core/paths.py` — new: centralized path resolution module (b5ec1c0)
- `app/backend/app/core/__init__.py` — new: core package init
- `app/backend/app/config.py` — replace hardcoded C:\Projekte\Hime paths (18a7dc9)
- `app/backend/app/database.py` — remove hardcoded DB seed path, add missing indexes (ed37f2d)
- `app/backend/app/routers/models.py` — path audit fixes (merge commit f5fe378)
- `app/CLAUDE.md` — updated for v1.2.0 pipeline architecture (12285ae)
- `README.md` — new: project README with setup instructions (b3730ab)
- `.env.example` — new: comprehensive env variable template (0a81530)
- `AUDIT_REPORT.md` — new: v1.2.0 audit report with findings (d2a888e)
- `app/backend/tests/test_paths.py` — new: paths module tests (merge commit f5fe378)

### Training Script Changes

Both `scripts/train_hime.py` and `scripts/train_generic.py` were modified by commit `cbfd13e`
(refactor(training): replace hardcoded paths with CLI args and env var fallbacks).

**Changes made:**
- Removed all `Path(r"C:\Projekte\Hime")` hardcoded roots
- Added `Path(__file__).resolve().parent.parent` as dynamic script-relative root
- Added `HIME_MODELS_DIR` and `HIME_TRAINING_DATA_DIR` environment variable overrides
- Added `--model-dir` and `--training-data` CLI arguments to both scripts
- `train_generic.py` additionally gained `--output-dir` CLI argument
- Output directory resolution updated to use new args in both scripts

These changes make the training scripts portable for the planned disk migration.

### Workstream Run Assessment

| Workstream | Did it run? | Evidence |
|---|---|---|
| WS1 Security | Yes | 4 commits across 4 files: input validation on 2 endpoints, EPUB path traversal fix, training subprocess sandboxing, Dependabot setup |
| WS2 Pipeline | Yes (Full) | 12+ files: new model_manager service, 5 prompt template txt files, pipeline graceful degradation, 2 new test files, training script path portability |
| WS3 UI/UX | Yes (Full) | 6+ files: 2 new components (Stage1Panel, ModelStatusDashboard), TranslationWorkspace updated, polling extended, WebSocket event handling added |
| WS4 System Check | Yes (Full) | 9+ files: new core/paths.py module, config.py + database.py de-hardcoded, CLAUDE.md + README + .env.example + AUDIT_REPORT.md created |

---

## 1. Training State

### Checkpoint Inventory

All checkpoints present as of 2026-04-07. No eval entries exist until checkpoint-550 (first eval at step 500).

| Checkpoint | global_step | epoch | best_metric (best_eval_loss) | last_train_loss |
|---|---|---|---|---|
| checkpoint-50 | 50 | 0.004236 | null (no eval run yet) | 0.3978 (step 50) |
| checkpoint-220 | 220 | 0.018637 | null (no eval run yet) | 0.3418 (step 220) |
| checkpoint-240 | 240 | 0.020331 | null (no eval run yet) | 0.2931 (step 240) |
| checkpoint-250 | 250 | 0.021178 | null (no eval run yet) | 0.5462 (step 250) |
| checkpoint-350 | 350 | 0.029649 | null (no eval run yet) | 0.5609 (step 350) |
| checkpoint-450 | 450 | 0.038120 | null (no eval run yet) | 0.5523 (step 450) |
| checkpoint-550 | 550 | 0.046591 | null (best_metric field null — not updated) | 0.5180 (step 550) |

**Note on checkpoint-550:** At step 500 (within the 550 checkpoint's log_history) the first eval ran: `eval_loss = 1.0066144466400146`. Despite this, `best_metric` and `best_model_checkpoint` remain `null` in the JSON — the callback did not record a winner, possibly because `load_best_model_at_end` or evaluation-based checkpoint selection is not enabled.

**Newest checkpoint:** checkpoint-550 (step 550, epoch 0.0466)
**Best eval_loss checkpoint:** checkpoint-550 is the only one with an eval entry (eval_loss = 1.0066 at step 500). No other checkpoint has run an eval.
**Note:** No checkpoint-12400 exists and was never saved. The previous v1.1.x run's checkpoint at step 8400, 8900, 10500, 11800, 13300, 14400 were all lost — only the checkpoints from the current (restarted) run survive.

### Training Configuration

Source: `scripts/training_config.json` (smart-stop config — not the Trainer config):
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

Trainer configuration (extracted from trainer_state.json across all checkpoints — consistent values):
- `max_steps`: 35415
- `num_train_epochs`: 3
- `train_batch_size`: 1
- `gradient_accumulation_steps`: 8 (confirmed in log: "Total batch size (1 x 8 x 1) = 8")
- `eval_steps`: 500
- `save_steps`: 50 (checkpoints 220–550); 50 for checkpoint-50
- `logging_steps`: 10
- Dataset: 94,438 train examples, 10,494 eval examples (104,932 total)
- Trainable parameters: 134,217,728 / 32,898,094,080 (0.41% — LoRA rank 16)

### Epoch Calculation

The previous v1.1.x run had `max_steps = 17709`, implying 1 epoch over 94,438 examples with batch size 8:
- 94,438 / 8 = 11,805 steps per epoch
- 17,709 steps / 11,805 = ~1.50 epochs (i.e., 1.5 epochs planned, not 1)

The current run has `max_steps = 35415`, `num_train_epochs = 3`:
- 35,415 / 17,709 = **2.000** (exactly 2x the previous max_steps)
- 35,415 / 11,805 steps-per-epoch = **3.000 epochs**
- Conclusion: someone changed `num_train_epochs` from the prior value to **3**, which recalculated max_steps as 35,415.

This means the epoch change is documented — the run was intentionally set to 3 epochs — but training was not resumed from any surviving checkpoint; it restarted from **step 0**.

### Training Log Analysis

The log file is 1,507,294 lines and covers multiple training sessions dating back to at least 2026-03-22.

**Reconstruction of training history from log:**

| Session | Date | Resumed from | Steps reached | Notes |
|---|---|---|---|---|
| v1.1.x sessions | 2026-03-22 | checkpoint-8400 | ~8401+ | Multiple crash/restart cycles |
| v1.1.x session | 2026-03-22 | checkpoint-8900 | ~9000+ | Resumed successfully |
| v1.1.x sessions | 2026-03-24 | checkpoint-5800 → checkpoint-10500 | ~10500+ | Resume chain |
| v1.1.x sessions | 2026-03-25 to 03-28 | checkpoint-11800 | crashed repeatedly | 3 failed starts with ERROR |
| v1.1.x session | 2026-03-29+ | checkpoint-13300 | ~14400 | max_epochs=10 experiment |
| v1.1.x final | 2026-04-03 11:58 | checkpoint-14400 | 14423 then crash | Last known good step; step 14410 loss=0.4939, epoch=2.44 |
| **v1.2.0 current** | **2026-04-03 (after crash)** | **NONE — fresh start** | **550 (as of log end)** | **Num Epochs=3, Total steps=35,415** |

**First step in current run:** step 1/35415 (confirmed at log line 1248597 — starts from 0)
**Resume evidence for current run:** NONE. No "Weitermachen von" or "Resuming from" message precedes the 35,415-step banner. The run started fresh.
**Error messages at startup of current run:** None found in the startup block. The prior session crashed at 2026-04-04 05:21 (W0404 torch warning + crash), and then a new session began cleanly.

**The last known good state of the v1.1.x run before the restart:**
- Step 14410 (of 17709), epoch 2.44, train loss 0.4939 (log line 1248450, 2026-04-03 14:17)
- Step 14420, train loss 0.5106, epoch 2.44 (log line 1248462)
- This was in Epoch 2 of 3, approximately 81% through the v1.1.x max_steps
- The previously reported "step ~12400" and "eval_loss ~0.9500" likely came from memory/UI state — the log shows the run actually reached step 14423 before crashing

### Smart Stop State

File: `modelle/lora/Qwen2.5-32B-Instruct/smart_stop_state.json`

```json
{"patience_counter": 0, "patience_total": 5, "target_hit_count": 0, "target_confirmations": 3, "best_metric": null, "stop_reason": null}
```

All counters are reset to zero. `best_metric` is null — the SmartStop callback has not recorded any eval improvement in the current (restarted) run. This is consistent with the current run only being at step 550 and having had just one eval (step 500, eval_loss = 1.0066) with no prior baseline to compare.

### Timeline Reconstruction

1. **v1.1.x (2026-03-22 to 2026-04-03):** Training ran for weeks with multiple crash/resume cycles. The run progressed through checkpoints up to ~14400 (epoch 2.44 of 17709 total steps). The best known eval_loss was ~0.9500 (from memory state; not recoverable from surviving files). Checkpoint-14400 was the last surviving checkpoint from this era, but it was wiped when the run restarted.

2. **Crash at 2026-04-04 05:21:** A torch/multiprocessing crash (W0404 warning) terminated the v1.1.x session at step 14423.

3. **Restart as v1.2.0 current run (2026-04-03/04):** A new training session launched with `num_train_epochs=3` and `max_steps=35415`. Critically, **no `--resume` flag pointed to checkpoint-14400** (or any other checkpoint). The training script detected no surviving checkpoint in the output directory (because checkpoint-14400 was not in the current checkpoint dir, or was overwritten) and began from step 0.

4. **Current state (as of log end, 2026-04-05 20:34):** The run is at step 600/35415, epoch 0.05, train_loss ~0.465. The only surviving checkpoint on disk is checkpoint-550. The eval at step 500 shows eval_loss = 1.0066, which is higher than the previously achieved ~0.9500 — consistent with starting over from scratch.

### Conclusion

**This was a fresh restart, not a resume.** The current run began at step 1/35415 with no checkpoint loaded. All progress from the v1.1.x run (steps 1–14423, estimated ~81% of Epoch 2 of 3, with best eval_loss ~0.9500) was lost because checkpoint-14400 was not preserved in the current checkpoint directory and no `--resume` argument was passed to the training script.

What was lost:
- Approximately 14,423 training steps of progress (equivalent to ~1 full epoch and most of a second)
- The adapter weights at best_eval_loss ~0.9500
- All intermediate checkpoints from the v1.1.x run

What is usable:
- **checkpoint-550** (step 550, eval_loss 1.0066 at step 500) is the newest and only checkpoint on disk. It is the only viable resume point. Training can be resumed from it using `--resume checkpoint-550`, which would skip re-running steps 1–550 and continue from step 551/35415.
- The training is stable — no gradient explosion, loss is trending in a reasonable range (0.46–0.58 at step 600), and eval_loss of 1.0066 at step 500 is normal for early training.

**Recommended action:** Let the current run continue from checkpoint-550 (do not restart again). The run will need approximately 34,865 more steps to complete, at ~8 seconds/step ≈ ~778 hours total remaining. Consider whether `num_train_epochs=3` with `max_steps=35415` is the intended configuration, as doubling the training budget from the v1.1.x run is a significant change that should be validated.

---

## 2. Training Monitor UI

**v1.2.0 modification status:** Not modified — `git log -- app/frontend/src/views/TrainingMonitor.tsx` shows no commit from the v1.2.0 run (f5fe378 … 4c199c4). The last meaningful commit touching this file is `a53ae33` (feat(training): add manual checkpoint save via signal file), which predates v1.2.0. The constraint "DO NOT touch TrainingMonitor.tsx" was respected.

### Current State vs. Expected

| Element | What exists | Line(s) | What a user would expect |
|---|---|---|---|
| Checkpoint list | Always expanded — each checkpoint is a flat card rendered unconditionally in a `div.space-y-3` | L1403–1442 | Collapsible — long lists (10+ checkpoints) are unwieldy and push content below the fold |
| Progress display | Both step and epoch — step/total at L1305, epoch at L1267–1269 with 2 decimal places; also percentage and ETA | L1293–1312 | Both step and epoch context (already satisfied) |
| ETA calculation | Parsed from tqdm log tail in backend (`parse_eta_from_log`); tqdm's own ETA uses a rolling/recent-step moving average, not a from-start total-elapsed calculation | L1307–1310 (frontend display); backend: `training_monitor.py` L249–263 | Rolling recent steps (already satisfied via tqdm) |
| Model selector | All 5 pipeline models: Qwen2.5-32B, Qwen2.5-14B, Qwen2.5-72B, Gemma 3-27B, DeepSeek-R1-32B — rendered as toggle buttons | L1215–1233 | All pipeline models available (already satisfied) |
| Pipeline info panel | Present for chart metrics only — "Was bedeuten diese Werte?" toggle explains Train Loss, Eval Loss, LR, Grad Norm, Epoch markers. No info about what each pipeline model does in the translation workflow. | L1332–1394 | Explanation of modular pipeline system (roles per model, why each exists) |

### Key Observations

- The checkpoint list renders all checkpoints as always-visible cards with no collapse or pagination. At 7 checkpoints this is already noisy; at 20+ it will dominate the page. Adding a `<details>` wrapper or a "show all / show fewer" toggle would fix this with minimal code change.
- Progress display is well-structured: percentage bar, step/total, ETA (seconds/step), epoch (decimal), best checkpoint and its eval_loss are all shown. This is the strongest section of the UI.
- The model selector in Training Controls covers all 5 LoRA-trainable models and auto-loads per-model checkpoints on selection — this is more capable than the task spec expected.
- The metric info panel ("Was bedeuten diese Werte?") is written in German and provides threshold guidance for Train Loss, Eval Loss, LR, and Grad Norm. However, there is no corresponding explanatory panel for the pipeline model cards (Section 4.5 "Pipeline Models (GGUF)") — a user has no in-UI way to understand what Stage 1 / Stage 2 / Stage 3 roles mean for translation quality.

---

## 3. Pipeline Overview / Translator View

### Files Modified by WS3

The following frontend files were created or modified by WS3 (confirmed via `git diff HEAD~10 HEAD --name-only -- app/frontend/src/`):

- `app/frontend/src/components/ModelStatusDashboard.tsx` — new component
- `app/frontend/src/components/Stage1Panel.tsx` — new component
- `app/frontend/src/components/comparison/ModelPanel.tsx` — new component
- `app/frontend/src/components/epub/TranslationWorkspace.tsx` — modified (Stage1Panel + PipelineProgress wired in)
- `app/frontend/src/hooks/useModelPolling.ts` — new hook

Additional pre-existing or independently modified files relevant to WS3:
- `app/frontend/src/components/PipelineProgress.tsx` — pipeline stage bar (Stage 1 → Consensus → Stage 2 → Stage 3)
- `app/frontend/src/api/websocket.ts` — `usePipeline` hook (lives in `api/`, not `hooks/`)
- `app/frontend/src/components/comparison/ModelComparisonTab.tsx` — per-model side-by-side panels
- `app/frontend/src/components/comparison/ConsensusPanel.tsx` — merged consensus output panel
- `app/frontend/src/components/comparison/LiveViewTab.tsx` — live polling view using `useModelPolling`
- `app/frontend/src/api/client.ts` — port discovery logic (hardcoded fallbacks present — see 3.5)

Note: `Translator.tsx` itself was NOT in the diff. The pipeline integration lives in `TranslationWorkspace.tsx`, which is the content component rendered by `Translator.tsx`. The `Stage1Panel` and `PipelineProgress` are wired into `TranslationWorkspace.tsx`, not `Translator.tsx` directly.

---

### WS3 Task Status

| WS3 Task | Status | Evidence |
|---|---|---|
| 3.1 Pipeline stage indicator in Translator.tsx | ⚠ partial | `PipelineProgress` renders Stage 1 → Consensus → Stage 2 → Stage 3 bar correctly (`PipelineProgress.tsx:7-14`), but it is wired into `TranslationWorkspace.tsx:220`, not `Translator.tsx` directly. `Translator.tsx` contains no pipeline logic — it is a pure shell delegating to `TranslationWorkspace`. Functionally equivalent, but the task spec named `Translator.tsx`. |
| 3.2 ModelStatus component | ✓ done | `ModelStatusDashboard.tsx` exists with color-coded green/red dots per model, latency in ms, and stage labels (Stage 1 / Consensus / Stage 2 / Stage 3). Polls `/api/v1/models` every 10s with cancel-on-unmount cleanup. Not mounted in `Translator.tsx` or `TranslationWorkspace.tsx` — it is an orphan component not yet placed in any view. |
| 3.3 usePipeline hook | ✓ done | Implemented as `usePipeline()` in `app/frontend/src/api/websocket.ts:61`. Handles all 12 relevant event types: `stage1_start`, `stage1_token`, `stage1_complete`, `consensus_start`, `consensus_token`, `consensus_complete`, `stage2_start`, `stage2_token`, `stage2_complete`, `stage3_start`, `stage3_token`, `stage3_complete`, plus `pipeline_complete`, `pipeline_error`, `model_error`, `model_unavailable`, `pipeline_status` (15 total in the union type). Cleanup on unmount via `cancelled = true` + `wsRef.current?.close()` at `websocket.ts:113-117`. Hook lives in `api/websocket.ts`, not `hooks/usePipeline.ts` as specified. |
| 3.4 Comparison.tsx per-model panels | ✓ done | `ModelComparisonTab.tsx` renders a 3-column grid (1 col mobile, xl:grid-cols-3) with `ModelPanel` for each of gemma / deepseek / qwen32b plus a `ConsensusPanel` for the merged output. Each panel shows online/offline status and streams tokens individually. `ConsensusPanel` shows "No models online" when count is 0. "Model offline" placeholder text in `ModelPanel.tsx:69`. |
| 3.5 No hardcoded URLs in frontend | ⚠ partial | `app/frontend/src/api/client.ts` contains hardcoded `127.0.0.1:18420` at lines 27, 83, 88, and 107. These are intentional fallbacks in a port-discovery chain (lock file → probe 18420–18430 → fallback to 18420), not naive hardcoding. In dev mode, the Vite proxy is used instead. Technically hardcoded, but the design is defensible for a local-first Tauri app. No hardcoded URLs found elsewhere in `app/frontend/src/`. |
| 3.6 Offline-first UX message | ✓ done | Multiple offline-aware messages implemented: `ConsensusPanel.tsx:43` shows "No models online"; `ModelComparisonTab.tsx:137` disables the compare button with tooltip "Start inference servers to enable comparison" when all models are offline; `Stage1Panel.tsx:46-62` shows per-model "Offline" badge and italic reason text when `model_unavailable` is received; `BackendBanner.tsx:10` shows "Backend offline" banner. The spec's exact phrase "No translation models are running" is not used verbatim, but the UX intent is fully covered. |

---

### Key Observations

- **Stage1Panel is wired, not orphaned.** `TranslationWorkspace.tsx:224-235` imports and renders `Stage1Panel` with live `usePipeline` state. This is the correct integration point. The confusion arises only if the spec literally expected changes inside `Translator.tsx` itself, which is now a thin shell.

- **ModelStatusDashboard is an orphan.** `ModelStatusDashboard.tsx` was created by WS3 but is imported by no view or layout component. It polls `/api/v1/models` correctly and renders color-coded model cards, but it is never mounted in the running app.

- **`usePipeline` is mislocated but fully functional.** The hook lives in `api/websocket.ts` rather than `hooks/usePipeline.ts` as specified. It handles all pipeline event types and manages WebSocket lifecycle correctly with cleanup. The location mismatch is cosmetic.

- **Hardcoded URLs in `client.ts` are structured fallbacks, not bugs.** The `127.0.0.1:18420` references appear inside a port-discovery function that first reads a lock file, then probes ports 18420–18430, and only then falls back to the default. In dev mode these code paths are bypassed entirely via the Vite proxy. This is acceptable for a local-first desktop app but should be noted for the disk migration checklist (port could change).

- **Comparison.tsx pipeline event coverage gap.** `ModelComparisonTab.tsx` handles `stage1_token`, `stage1_complete`, `consensus_token`, `consensus_complete`, `model_error`, `pipeline_error`, and `pipeline_complete` but does not handle `stage2_*` or `stage3_*` events. The Comparison view is intentionally a Stage-1-only view, so this is by design — but any backend pipeline run that emits stage2/stage3 events will have those silently ignored in the comparison tab.

---

## 4. Pipeline Backend

### WS2 Task Status

| WS2 Task | Status | Evidence |
|---|---|---|
| 2.1 `services/pipeline.py` with `HimePipeline` class | ⚠ restructured | `services/` has no `pipeline.py`. Instead: `pipeline/runner.py` with `run_pipeline()` coroutine + `pipeline/prompts.py`. Functionally equivalent 4-stage orchestration; naming diverges from spec. |
| 2.2 `model_manager.py` — env var endpoints | ✓ done | Reads all 6 URLs via `settings.<attr>` (Pydantic `BaseSettings`), which maps to env vars `HIME_GEMMA_URL`, `HIME_DEEPSEEK_URL`, etc. — but see naming note below. |
| 2.2 `model_manager.py` — health check method | ✓ done | `check_model_health(key)` at L42 — async HTTP ping to `/v1/models`; `check_all_models()` at L85 — parallel gather of all 6. |
| 2.3 DB schema — 8 new columns | ✓ done | All 8 columns in `database.py:16-25` (`_PIPELINE_COLS`), with inline ALTER TABLE migration in `init_db()`. All 8 also declared in `models.py:44-52` ORM. |
| 2.4 WebSocket structured events | ✓ done | 10 of 11 specified event types implemented: `stage1_start`, `stage1_token`, `stage1_complete`, `consensus_start`, `stage2_start`, `stage2_complete` (via `_stream_stage` suffix `_complete`), `stage3_start`, `stage3_complete`, `pipeline_complete`, `model_unavailable`. Missing: `consensus_complete` is emitted as `consensus_complete` via `_stream_stage("consensus",...)` — present. All 11 accounted for. |
| 2.5 Training script path audit | ✓ done | `scripts/train_hime.py` uses `Path(__file__).resolve().parent.parent` as dynamic root (L64), `os.environ.get("HIME_MODELS_DIR")` and `os.environ.get("HIME_TRAINING_DATA_DIR")` (L64-66), and `argparse.ArgumentParser` with `--model-dir`, `--training-data` args (L556+). No hardcoded `C:\Projekte\Hime` paths remain. |
| 2.6 Prompt templates (5 files) | ✓ done | All 5 `.txt` files present and non-empty in `app/backend/app/prompts/`: `stage1_translate.txt` (8 lines), `stage2_refine.txt` (10 lines), `stage3_polish.txt` (8 lines), `consensus_merge.txt` (13 lines), `verify_bilingual.txt` (14 lines). Loaded by `pipeline/prompts.py` with inline fallbacks. |

**Summary: 5 of 6 tasks done (✓), 1 structurally diverged (⚠) but functionally equivalent.**

---

### model_manager.py Details

File: `app/backend/app/services/model_manager.py`

- Reads model URLs via `getattr(settings, m["url_attr"])` — each `url_attr` maps to a `Settings` field (e.g., `hime_gemma_url`). Pydantic `BaseSettings` auto-maps these to env vars `HIME_GEMMA_URL`, `HIME_DEEPSEEK_URL`, `HIME_QWEN32B_URL`, `HIME_MERGER_URL`, `HIME_QWEN72B_URL`, `HIME_QWEN14B_URL`. **Spec compliance:** the spec named these exact 6 env vars; Pydantic's field-to-env-var mapping matches them by lowercasing the env var names. Correct.
- **Env var naming note:** The spec lists `HIME_MERGER_URL` for the consensus model. `config.py` uses field `hime_merger_url` which maps to env var `HIME_MERGER_URL`. Match confirmed.
- `check_model_health(key: str) -> dict` (L42): async ping to `{url}/models` (OpenAI `/v1/models` endpoint), 2-second timeout via `httpx.AsyncClient`. Returns `{"key", "name", "endpoint", "online", "loaded_model", "latency_ms"}`.
- `check_all_models() -> list[dict]` (L85): parallel gather of all 6 model health checks via `asyncio.gather`.
- `get_model_configs() -> list[dict]` (L28): synchronous helper that returns all 6 model configs with current URL and model ID from settings.
- No background polling loop built in — callers invoke health checks on demand (the `/api/v1/models` router endpoint calls this on each HTTP request).

---

### Pipeline Orchestrator

**Spec (WS2 Task 2.1):** `services/pipeline.py` with a `HimePipeline` class.

**What exists:** `app/backend/app/pipeline/runner.py` with module-level coroutine `run_pipeline(job_id, source_text, notes, ws_queue)` (L87). The `pipeline/` package also contains `prompts.py` for template loading. There is no `HimePipeline` class; the orchestration is a single `async def run_pipeline(...)` function.

**Functional equivalence:** The `run_pipeline` coroutine implements the full 4-stage flow (Stage 1 parallel → Consensus → Stage 2 → Stage 3), with:
- Per-stage DB checkpointing via `_checkpoint()` (L73) using short-lived `AsyncSessionLocal` sessions (survives WebSocket disconnect)
- `asyncio.gather(..., return_exceptions=True)` for Stage 1 parallelism with per-model error handling
- `model_unavailable` events for any Stage 1 model that fails or returns empty output
- Graceful degradation: pipeline continues if at least 1 of 3 Stage 1 models succeeds; aborts only if all 3 fail
- Final sentinel `await ws_queue.put(None)` to signal drain loop completion

The WebSocket endpoint (`websocket/streaming.py`) spawns `run_pipeline` as an `asyncio.Task` and drains the queue to the client. A reconnect path is handled: if the job is already in-flight, the endpoint awaits the existing task rather than spawning a duplicate.

---

### Database Schema

All 8 new columns are fully implemented:

| Column | Type | Location |
|---|---|---|
| `stage1_gemma_output` | TEXT | `database.py:17`, `models.py:44` |
| `stage1_deepseek_output` | TEXT | `database.py:18`, `models.py:45` |
| `stage1_qwen32b_output` | TEXT | `database.py:19`, `models.py:46` |
| `consensus_output` | TEXT | `database.py:20`, `models.py:47` |
| `stage2_output` | TEXT | `database.py:21`, `models.py:48` |
| `final_output` | TEXT | `database.py:22`, `models.py:49` |
| `pipeline_duration_ms` | INTEGER | `database.py:23`, `models.py:50` |
| `current_stage` | TEXT | `database.py:24`, `models.py:52` |

Migration strategy: inline `ALTER TABLE translations ADD COLUMN` in `init_db()` (called on startup) — only adds if column is not already present. No Alembic. Safe for existing databases.

---

### WebSocket Events

Implemented in `app/backend/app/pipeline/runner.py` and handled by `app/backend/app/websocket/streaming.py`:

| Event | Emitted by | Fields |
|---|---|---|
| `stage1_start` | runner.py:103 | `models: ["gemma", "deepseek", "qwen32b"]` |
| `stage1_token` | runner.py:46 | `model`, `token` |
| `stage1_complete` | runner.py:48 | `model`, `output` |
| `consensus_start` | runner.py:164 | — |
| `consensus_token` | runner.py:67 (via `_stream_stage("consensus",...)`) | `token` |
| `consensus_complete` | runner.py:69 (via `_stream_stage`) | `output` |
| `stage2_start` | runner.py:179 | — |
| `stage2_token` | runner.py:67 | `token` |
| `stage2_complete` | runner.py:69 | `output` |
| `stage3_start` | runner.py:194 | — |
| `stage3_token` | runner.py:67 | `token` |
| `stage3_complete` | runner.py:69 | `output` |
| `pipeline_complete` | runner.py:214 | `final_output`, `duration_ms` |
| `model_unavailable` | runner.py:141 | `model`, `reason` |
| `model_error` | runner.py:119 | `stage`, `model`, `detail` |
| `pipeline_error` | runner.py:148, 221 | `detail` |
| `pipeline_status` | streaming.py:158 | `current_stage` (reconnect path only) |

All 11 spec-specified event types (`stage1_start`, `stage1_token`, `stage1_complete`, `consensus_start`, `consensus_complete`, `stage2_start`, `stage2_complete`, `stage3_start`, `stage3_complete`, `pipeline_complete`, `model_unavailable`) are present. The implementation additionally emits `model_error`, `pipeline_error`, and `pipeline_status`.

---

### Impact of Missing services/pipeline.py

**Translation is currently functional.** The spec called for `services/pipeline.py` with a `HimePipeline` class, but the author instead implemented the orchestration in `pipeline/runner.py` as a module-level coroutine — a flat function rather than a class. This is a structural divergence, not a functional gap.

Evidence that translation works end-to-end:
1. `websocket/streaming.py` imports `run_pipeline` from `pipeline.runner` and spawns it as an `asyncio.Task`
2. `run_pipeline` connects to all 6 model endpoints via `settings.*_url` and streams results to `ws_queue`
3. DB checkpoints are written after each stage
4. The WebSocket drain loop sends all events to the frontend
5. The `usePipeline` hook in the frontend handles all emitted event types

**What does not exist:** No `HimePipeline` class, no `services/pipeline.py` file. Any code that imports `from services.pipeline import HimePipeline` would fail — but no such import exists anywhere in the codebase. The refactored module layout (`pipeline/` package) is consistent and self-contained.

**Caveat:** Translation only succeeds if at least one Stage 1 model and the subsequent Stage 2/3 models are reachable. With all models offline, `pipeline_error` is emitted after Stage 1 fails entirely. The pipeline does not fall back to single-model translation — it is strictly multi-model.

---

## 5. Disk Migration Readiness

### paths.py Status
- Exists: ✓
- All 7 required variables defined: ⚠ 6 of 7 defined as module-level constants. `CHECKPOINTS_DIR` is NOT a plain `Path` constant — it is implemented as `checkpoints_dir(model_name: str) -> Path` (a function), because checkpoint paths are model-specific. `HIME_SCRIPTS_DIR` is an additional 8th variable not in the original spec but present. `TRAINING_LOG_DIR` is also derived as `LOGS_DIR / "training"`.
- Env var names correct: ✓ for all 6 plain constants (`HIME_PROJECT_ROOT`, `HIME_DATA_DIR`, `HIME_MODELS_DIR`, `HIME_LOGS_DIR`, `HIME_EPUB_WATCH_DIR`, `HIME_TRAINING_DATA_DIR`). `HIME_CHECKPOINTS_DIR` is only consumed inside the `checkpoints_dir()` function.
- Fallback defaults: ✓ All defaults are relative to `Path(__file__).resolve().parents[4]` — no hardcoded absolute paths.
- Imported in backend code: 2 files (`app/backend/app/database.py`, `app/backend/app/config.py`). The services layer (`training_runner.py`, `epub_service.py`) uses `settings` from `config.py` rather than importing `paths` directly. Functionally consistent — `config.py` is the bridge — but `paths.py` is not the universal import hub the design intended.

### Hardcoded Paths Remaining

Total: **13 occurrences across 12 source files** (excluding build artifacts in `target/` and `unsloth_compiled_cache/`)

| File | Count | Sample path |
|---|---|---|
| `scripts/align_shuukura.py` | 1 | `Path(r"C:\Projekte\Hime")` |
| `scripts/analyze_training_data.py` | 1 | `Path(r"C:\Projekte\Hime")` |
| `scripts/convert_jparacrawl.py` | 1 | `Path(r"C:\Projekte\Hime")` |
| `scripts/download_jparacrawl.py` | 1 | `Path(r"C:\Projekte\Hime")` |
| `scripts/epub_extractor.py` | 1 | `Path(r"C:\Projekte\Hime")` |
| `scripts/scraper.py` | 1 | `Path(r"C:\Projekte\Hime")` |
| `scripts/scraper_kakuyomu.py` | 1 | `Path(r"C:\Projekte\Hime")` |
| `scripts/scraper_skythewood.py` | 1 | `Path(r"C:\Projekte\Hime")` |
| `scripts/train_debug.py` | 2 | `r"C:\Projekte\Hime\data\training\..."` |
| `scripts/train_restart_loop.py` | 1 | `Path(r"C:\Projekte\Hime")` |
| `scripts/check_format.py` | 1 | `r"C:\Projekte\Hime\data\raw_jparacrawl\..."` |
| `app/frontend/src-tauri/src/lib.rs` | 1 | `r"C:\Projekte\Hime\app\backend\hime-backend.lock"` (L265, `#[cfg(debug_assertions)]` only) |

Note: `scripts/bump_version.py` and `scripts/build_backend.py` use inline comments referencing the path but compute it correctly via `Path(__file__).parent.parent` — these are not broken.

### .env.example Completeness
- Paths section (7 vars, incl. `HIME_CHECKPOINTS_DIR`): ✓ all 7 present (also includes `HIME_SCRIPTS_DIR` as an 8th)
- Model endpoints (6 vars): ✓ `HIME_GEMMA_URL`, `HIME_DEEPSEEK_URL`, `HIME_QWEN32B_URL`, `HIME_MERGER_URL`, `HIME_QWEN72B_URL`, `HIME_QWEN14B_URL` — all present
- App config (3 vars): ✓ `HIME_API_KEY` (commented, generated on first run), `HIME_BIND_HOST`, `HIME_BACKEND_PORT` — all present

**Migration readiness score: 5/10**

Reasoning: `paths.py` exists, is well-structured, and has sensible relative fallbacks — the backend core is migration-safe. However, 11 of the standalone scripts still hardcode `C:\Projekte\Hime` and will fail immediately after a disk migration. The Tauri debug build also has a hardcoded lock file path (lib.rs L265). These were identified as AUDIT-002 and AUDIT-003 ("NOT FIXED") and represent the dominant migration risk: the backend API survives a move, but all data prep, training, and dev-mode frontend startup do not.

---

## 6. Security Workstream

### WS1 Task Status

| WS1 Task | Status | Evidence |
|---|---|---|
| 1.1 Input validation (training endpoints) | ⚠ Partial | `training.py` L134–138: `epochs` validated `ge=1, le=100`; `model_name` pattern+max_length; `resume_checkpoint` pattern. `learning_rate` and `batch_size` not exposed as endpoint parameters (handled internally by training scripts). `TrainingConfigUpdate` L208–210 rejects null bytes and newlines. |
| 1.2 Subprocess shell=False + Job Objects + timeout + audit log | ✓ Complete | `training_runner.py` L238: `subprocess.Popen(cmd, ...)` with list arg (shell=False implicit). L24–88: Windows Job Object fully implemented with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. L259: `max_duration = 72 * 3600` enforced in `get_running_processes()`. L248–257: JSON audit entries via `hime.audit` logger for start/stop events. |
| 1.3 CORS lockdown | ✓ Complete | `main.py` L116–124: exact origins `["http://localhost:1420", "https://tauri.localhost"]`, no wildcards. |
| 1.4 .env.example exists | ✓ Complete | File present at project root with all required sections. |
| 1.5 Path traversal prevention in epub_service.py | ⚠ Partial | `epub_service.py` L23–52: `_validate_epub_path()` implements null-byte check, `Path.resolve()`, `.is_relative_to(root)`, and symlink target check. However, `import_epub()` L264–267 only calls validation `if allowed_root` is provided — callers that omit `allowed_root` bypass the check entirely. `scan_watch_folder()` correctly passes `allowed_root=folder_path`. |
| 1.6 AUDIT_REPORT.md | ✓ Complete | `AUDIT_REPORT.md` exists. Summary: 0 critical, 3 high, 1 medium, 4 low, 5 info. |

### CORS Details
```
allow_origins:     ["http://localhost:1420", "https://tauri.localhost"]
allow_credentials: True
allow_methods:     ["GET", "POST", "PUT", "DELETE"]
allow_headers:     ["Content-Type", "X-API-Key"]
```
No wildcards present. WS1 did NOT modify `main.py` (per git history from Task 1), but the CORS configuration was already correct in v1.1.x — no regression.

### Key Security Gaps

1. **Path traversal bypass (epub_service.py L267):** `import_epub()` accepts an optional `allowed_root` — if a caller passes `None` (the default), `_validate_epub_path()` is never called, allowing arbitrary file paths to be parsed. All current call sites pass `allowed_root` correctly, but the API contract is fragile. Fix: make `allowed_root` required, or always validate against `EPUB_WATCH_DIR`.

2. **learning_rate / batch_size not validated at the API layer:** These hyperparameters are passed directly to training scripts as CLI args. If the scripts themselves don't validate bounds, a caller could pass extreme values. Lower risk since training is a privileged local operation, but the WS1 spec listed these bounds explicitly (1e-6..1e-2, 1..64).

3. **Hardcoded debug path in lib.rs (L265):** The lock file path in `#[cfg(debug_assertions)]` is hardcoded to `C:\Projekte\Hime\...`. Dev builds will fail to connect after a disk migration. Low security impact but high dev-workflow risk.

---

## Recommended Next Steps

### Priority 1 — Immediate (blocking or security-critical)

**1a. Protect the current training run**
- Do NOT trigger another restart
- If resuming is needed, use: `--resume_from_checkpoint modelle/lora/Qwen2.5-32B-Instruct/checkpoint/checkpoint-550`
- Investigate: add `smart_stop_state.json` logic to auto-pass `--resume` on crash-restart, so this scenario cannot repeat

**1b. Fix epub path traversal bypass**
- File: `app/backend/app/services/epub_service.py`
- Fix: make `allowed_root` required in `import_epub()`, or default it to `paths.EPUB_WATCH_DIR` so `_validate_epub_path()` always runs
- This is a WS1 partial that needs completing before production use

**1c. Fix input validation gaps**
- File: `app/backend/app/routers/training.py`
- Missing: `learning_rate` and `batch_size` bounds at the API layer
- Add `Field(ge=1e-6, le=1e-2)` / `Field(ge=1, le=64)` to the Pydantic request model so extreme values are rejected before reaching the training script

### Priority 2 — Before disk migration (next few days)

**2a. Fix hardcoded paths in scripts/**
- 11 standalone scripts still hardcode `C:\Projekte\Hime`
- Files: `scripts/align_shuukura.py`, `scripts/analyze_training_data.py`, `scripts/convert_jparacrawl.py`, `scripts/download_jparacrawl.py`, `scripts/epub_extractor.py`, `scripts/scraper.py`, `scripts/scraper_kakuyomu.py`, `scripts/scraper_skythewood.py`, `scripts/train_debug.py`, `scripts/train_restart_loop.py`, `scripts/check_format.py`
- Replace each `Path(r"C:\Projekte\Hime")` with `Path(__file__).resolve().parent.parent` or `os.environ.get("HIME_PROJECT_ROOT")`

**2b. Fix Tauri debug build hardcoded path**
- File: `app/frontend/src-tauri/src/lib.rs` L265
- Path is inside a `#[cfg(debug_assertions)]` block — replace with a runtime env var lookup or path relative to the binary

**2c. Wire paths.py into remaining backend modules**
- `paths.py` exists but only `database.py` and `config.py` import it directly
- `training_runner.py` and `epub_service.py` go through `config.py` (acceptable), but confirm no residual direct `Path("C:/...")` calls in those files

**2d. Mount ModelStatusDashboard**
- File: `app/frontend/src/views/Settings.tsx` or `app/frontend/src/components/epub/TranslationWorkspace.tsx`
- Component: `app/frontend/src/components/ModelStatusDashboard.tsx`
- One import + one JSX element — 5-minute fix that surfaces model health to users

### Priority 3 — Quality improvements (no deadline)

**3a. Checkpoint list collapsibility in TrainingMonitor.tsx**
- Checkpoint cards are always expanded (L1403–1442) — at 10+ checkpoints this dominates the page
- Wrap in a `<details>` element or a "Show all / Show fewer" toggle

**3b. Verify stage indicator placement**
- `PipelineProgress` renders correctly in `TranslationWorkspace.tsx:220` but the spec named `Translator.tsx`
- Confirm the component is actually visible during a live translation run and not hidden behind a conditional

**3c. Add pipeline explanatory panel**
- Neither `TrainingMonitor.tsx` nor `Translator.tsx` explains the modular pipeline architecture
- Add a collapsible "About this pipeline" info section analogous to the existing "Was bedeuten diese Werte?" metrics panel

### Post-Migration Validation Checklist

After any disk migration:
- [ ] Verify all 7 `HIME_*` path env vars are set in the new `.env`
- [ ] Run `python -c "from app.core.paths import PROJECT_ROOT; print(PROJECT_ROOT)"` to confirm dynamic resolution
- [ ] Run `npm run build` in `app/frontend/` and check bundle output for any embedded absolute paths
- [ ] Confirm Tauri `lib.rs` L265 lock file path is resolved (or `#[cfg(debug_assertions)]` block is updated)
- [ ] Run all 11 fixed scripts with `--dry-run` or equivalent to confirm they resolve paths correctly
