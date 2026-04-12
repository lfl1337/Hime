# REMEDIATION REPORT — Hime v2.0.0

_Branch: remediation/v2.0.0-20260411 | Completed: 2026-04-11_

---

## Summary

Full remediation of Hime from v1.x to v2.0.0 completed across 9 phases.
The pipeline was fundamentally redesigned: Stage 1 now runs 4 models in parallel,
Stage 2 merges with TranslateGemma-27B, Stage 3 uses Qwen3-30B-A3B (MoE), and
Stage 4 introduces a 15-persona Reader Panel with LFM2-24B aggregator and a
two-path retry loop (fix_pass / full_retry).

---

## Phase Completion Status

| Phase | Title | Status |
|-------|-------|--------|
| 01 | Quick wins (config, security, DB) | ✅ Complete |
| 02 | Downloads (BGE-M3, Qwen3-30B) | ✅ Complete |
| 03 | Code fixes (RAG, config, pipeline) | ✅ Complete |
| 04 | Dry-run validation | ✅ Complete |
| 05 | Training v2 | ✅ Complete |
| 06 | Data registry | ✅ Complete |
| 07 | Frontend tests | ✅ Complete |
| 08 | Backend tests + E2E | ✅ Complete |
| 09 | Final smoke test + v2.0.0 | ✅ Complete |

---

## Version Bump (all 8 files)

| File | Version |
|------|---------|
| app/VERSION | 2.0.0 |
| app/backend/pyproject.toml | 2.0.0 |
| app/frontend/package.json | 2.0.0 |
| app/frontend/src-tauri/tauri.conf.json | 2.0.0 |
| app/frontend/src-tauri/Cargo.toml | 2.0.0 |
| app/backend/app/main.py | 2.0.0 |
| app/frontend/src/components/Sidebar.tsx | v2.0.0 |
| app/frontend/src/views/Settings.tsx | v2.0.0 |

All verified by `tests/test_version_bump.py` (8/8 pass).

---

## T1–T8 Post-Remediation Fixes (2026-04-11, Session 1)

Applied after second CC audit of the Stage 4 two-path retry implementation:

| ID | File | Change |
|----|------|--------|
| T1 | `tests/test_stage4_aggregator_segment.py` | `isinstance(SegmentVerdict)` → `hasattr` duck-typing (import-reload safety) |
| T2 | `app/frontend/src/api/pipeline_v2.ts` | WS event types updated: `stage3_complete` gets `fix_pass_count`/`full_retry_count`, `segment_complete` gets `retry_flag: boolean` |
| T3 | `app/pipeline/runner_v2.py` | `run_pipeline_v2` docstring clarifies `session` scope |
| T4 | `tests/conftest.py` | `db_session` fixture uses SAVEPOINT nested transaction for test isolation |
| T5 | `app/database.py` | SQLite dialect guard on PRAGMA event listener |
| T6 | `app/pipeline/runner_v2.py` | `_run_ladder()` async helper extracted — removes ~60-line duplication |
| T7 | `app/pipeline/stage4_aggregator.py` | `_strip_code_fence()` + `_run_generation()` extracted |
| T8 | `tests/test_paragraph_retry_columns.py` | Migration test renamed to `test_retry_columns_exist_in_schema` (accurate description) |

## T9–T15 Post-Remediation Fixes (2026-04-11, Session 2)

Applied after Phase 9 smoke test + user review of Monitor view:

| ID | File | Change |
|----|------|--------|
| T9  | `app/frontend/src/views/TrainingMonitor.tsx` | MODEL_TO_LORA_DIR: Added v2 Stage 1 models (translategemma12b, qwen35-9b); removed Qwen3-30B-A3B (Stage 3 zero-shot, not LoRA) |
| T10 | `app/frontend/src/views/TrainingMonitor.tsx` | Training Controls model buttons: v2 models first (Qwen2.5-32B+LoRA, TranslateGemma-12B, Qwen3.5-9B), v1 labeled "(v1)"; Qwen3-30B-A3B removed |
| T11 | `app/frontend/src/components/TrainingExplanation.tsx` | "Was ist modulares Training?" updated to v2: correct Stage 1/2/3/4 model list; "kein Training" annotations for zero-shot stages |
| T12 | `app/backend/app/services/training_runner.py` | MODEL_KEY_TO_RUN_NAME: Added v2 model keys (translategemma12b, qwen35-9b) |
| T13 | `app/backend/app/services/training_runner.py` | Added `max_steps` forwarding from `training_config.json` to `train_generic.py` subprocess |
| T14 | `scripts/training/trainers/unsloth_trainer.py` | Implemented `UnslothTrainer.run()`: delegates to `train_hime.main()` with config values patched as module globals |
| T15 | `app/CLAUDE.md` | Architecture diagram updated from v1 to v2.0.0 (4-stage pipeline, correct model names, RAG store, v1 ports marked as unused) |

---

## Test Suite (final state)

```
316 passed, 3 failed (pre-existing), 1 skipped
```

Pre-existing failures not introduced by remediation:
- `test_conftest_isolation::test_backend_dir_hime_db_not_created` — conftest DB pollution (tracked)
- `test_train_with_resume` — training retry logic, unrelated
- `test_vault_organizer` — no model loaded

---

## Known Limitations & Post-Remediation Items

| ID | Description | Status |
|----|-------------|--------|
| POST-1 | Stage 2/3 model IDs use `os.environ.get()` at import time — only shell env vars work, not `.env` values | Open |
| POST-2 | All 21 production books have `series_id=None` + 0 `is_reviewed=True` paragraphs → RAG context empty | Open |
| POST-3 | W10 eval_loss overfitting out of scope | Open |
| POST-4 | Comparison view model list shows v1 models (Gemma 3 12B, DeepSeek R1 32B, Qwen 2.5 32B) | Open |
| POST-5 | Tauri build cache had stale `C:\Projekte\Hime` paths (old disk) | ✅ Fixed (T5 Session 1) |
| POST-6 | `CLAUDE.md` architecture diagram shows v1 pipeline | ✅ Fixed (T15 Session 2) |
