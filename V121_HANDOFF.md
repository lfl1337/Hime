# V1.2.1 Workstream Handoffs

## WS1 — Training, Curriculum & Auto-Resume

### Status: ✅ Complete (11 commits, 41 new tests, 0 regressions)

**Commits on `v1.2.1-ws1`:**

```
c06aeed feat(training): add empty training package for curriculum modules
2ce5439 feat(training): add CurriculumDataLoader with score-tier filter and literary merge
d62caa5 feat(training): add CurriculumCallback with eval-stagnation promotion and state persistence
a75a2c5 feat(training): add train_with_resume wrapper with checkpoint pre-flight scan
6031092 fix(training): drop None from train_with_resume --model-key choices
676803e feat(training): add crash retry loop and tier-promotion handling to train_with_resume
ecb926f fix(training): atomic curriculum_state write + tighten T5 test boundary and schema guard
ba454d5 feat(training): add SIGINT/SIGTERM handling to train_with_resume wrapper
9dbf1f8 feat(training): wire curriculum loader/callback into train_hime.py and verify resume passthrough (next run only)
0124740 chore(training): add NON-LIVE v1.2.1 hyperparameter proposal (merge after current run)
043ee19 feat(api): add Pydantic bounds for training hyperparameters (LR, batch, LoRA r/dropout)
```

### Deliverables

- **Curriculum data loader + callback** — `app/backend/app/training/curriculum.py` and `curriculum_callback.py`, 14 tests passing (`test_curriculum.py` + `test_curriculum_callback.py`)
- **Auto-resume wrapper** — `scripts/train_with_resume.py` with pre-flight checkpoint scan, crash retry loop (strict-`>` boundary at `max_restarts`), tier-promotion exit path, SIGINT/SIGTERM handling, atomic curriculum_state writes. 12 tests passing (`test_train_with_resume.py`).
- **API hyperparameter bounds** — `StartTrainingRequest` in `routers/training.py` now validates `epochs` (0.1-20.0 float), `learning_rate` (1e-6 to 1e-2), `batch_size` (1-64), `gradient_accumulation_steps` (1-128), `lora_r` (1-256), `lora_dropout` (0.0-0.5). 15 tests passing (`test_training_router_validation.py`).
- **NON-LIVE hyperparameter proposal** — `scripts/training_config_v121_proposed.json` with per-model defaults + curriculum block. **NOT merged into the live config.**
- **Curriculum wired into `scripts/train_hime.py`** — NEXT RUN ONLY. Legacy data loader preserved as fallback.

### Final verification

- WS1 test suite: **41/41 passing** (7 curriculum + 7 callback + 12 wrapper + 15 router)
- Full backend suite: **75/75 passing, 1 skipped, 0 failures**
- `scripts/training_config.json` — **unchanged** (confirmed via `git status`)
- Training PIDs still alive: confirmed (6 processes)
- `scripts/train_with_resume.py --dry-run --no-prompt --model-name Qwen2.5-32B-Instruct`: probes the WS1 worktree's (non-existent) checkpoint dir, prints `cmd:` line, exits 0. **Does NOT touch the live checkpoint dir in the main worktree.**

### Hard constraints for the reviewer / merge engineer

- ⚠️ **DO NOT** merge `scripts/training_config_v121_proposed.json` into `scripts/training_config.json` until the current Qwen2.5-32B-Instruct run has finished. The trainer reads the live config at startup; an external watcher restarting the run would pick up the new defaults mid-stream.
- ⚠️ **DO NOT** invoke `scripts/train_with_resume.py` in non-dry-run mode against `Qwen2.5-32B-Instruct` until the current run is stopped. Use `TestModel` or any other unused model name for testing.
- ⚠️ **DO NOT** pre-create `modelle/lora/Qwen2.5-32B-Instruct/curriculum_state.json`. The `CurriculumCallback` initializes it on first call during the NEXT training start.

### Known issues / follow-ups

- ⚠️ **`epochs` field type changed from `int` to `float`** in `StartTrainingRequest`. `app/backend/app/services/training_runner.py::start_training(..., epochs: int = 3, ...)` still annotates `int`, but the value is only used via `str(epochs)` in the subprocess cmd, so floats pass through transparently. Frontend that sends `epochs` as an integer still works (Pydantic coerces). Consider updating the `training_runner.py` signature to `epochs: float = 3` for type consistency — deferred as out-of-scope for WS1 T10.
- ⚠️ **LATENT BUG FIXED:** `app/backend/app/routers/training.py` at the branch point (commit `f5fe378`) was missing `Field` from its pydantic import: `from pydantic import BaseModel, field_validator`. The class `StartTrainingRequest` references `Field(...)` several times, so importing `routers.training` would raise `NameError` at module load, which in turn would break the entire FastAPI app startup via `app.include_router(training.router)`. The main worktree has a local **uncommitted** fix for this (git status at session start showed `M app/backend/app/routers/training.py`). WS1 T10's commit `043ee19` includes the same fix (`from pydantic import BaseModel, Field, field_validator`). When WS1 merges back to main, the user's local fix will merge cleanly (same line addition) or conflict trivially.
- ⚠️ **Curriculum path in train_with_resume.py is hardcoded** to `modelle/lora/<model_name>/curriculum_state.json`, matching the hardcoded path in `train_hime.py` (WS1 T7). If either side changes the layout, they must change together. The code review flagged this as a cross-task coupling risk but deferred the extraction to `core/paths.py::curriculum_state_path(model_name)` as a follow-up.
- ⚠️ **`_persist()` non-atomicity in `CurriculumCallback`** (T3) is non-atomic (plain `write_text`). Recovery is handled by `_load_or_init_state()` re-initializing on parse failure — acceptable for a training-time bookkeeping file, but a crash mid-write would lose the most recent entry in `promotion_history`. The wrapper's `_clear_curriculum_promotion_flag` was upgraded to atomic write-temp-and-rename in commit `ecb926f`; the callback side was left non-atomic as it was not in the code review's recommended-before-merge list. Consider parity upgrade as a follow-up.

### Conda env changes (shared across all worktrees)

- `pytest-asyncio` and `aiosqlite` were installed via pip during WS4 T2 (they were listed in `pyproject.toml` but missing from the env). This affects all worktrees using the `hime` env. WS1 tests use `pytest-asyncio` in some files (though WS1 T1-T10 itself doesn't — the dep is inherited from shared fixtures).
