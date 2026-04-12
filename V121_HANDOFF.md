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

### Hard constraints

- ⚠️ **DO NOT** merge `scripts/training_config_v121_proposed.json` into `scripts/training_config.json` until the current Qwen2.5-32B-Instruct run has finished. The trainer reads the live config at startup; an external watcher restarting the run would pick up the new defaults mid-stream.
- ⚠️ **DO NOT** invoke `scripts/train_with_resume.py` in non-dry-run mode against `Qwen2.5-32B-Instruct` until the current run is stopped. Use `TestModel` or any other unused model name for testing.
- ⚠️ **DO NOT** pre-create `modelle/lora/Qwen2.5-32B-Instruct/curriculum_state.json`. The `CurriculumCallback` initializes it on first call during the NEXT training start.

### Known issues / follow-ups

- ⚠️ **`epochs` field type changed from `int` to `float`** in `StartTrainingRequest`. `app/backend/app/services/training_runner.py::start_training(..., epochs: int = 3, ...)` still annotates `int`, but the value is only used via `str(epochs)` in the subprocess cmd, so floats pass through transparently. Consider updating the `training_runner.py` signature to `epochs: float = 3` for type consistency — deferred as out-of-scope for WS1 T10.
- ⚠️ **Curriculum path in train_with_resume.py is hardcoded** to `modelle/lora/<model_name>/curriculum_state.json`, matching the hardcoded path in `train_hime.py` (WS1 T7). If either side changes the layout, they must change together. The code review flagged this as a cross-task coupling risk but deferred the extraction to `core/paths.py::curriculum_state_path(model_name)` as a follow-up.
- ⚠️ **`_persist()` non-atomicity in `CurriculumCallback`** (T3) is non-atomic (plain `write_text`). Recovery is handled by `_load_or_init_state()` re-initializing on parse failure — acceptable for a training-time bookkeeping file, but a crash mid-write would lose the most recent entry in `promotion_history`. The wrapper's `_clear_curriculum_promotion_flag` was upgraded to atomic write-temp-and-rename in commit `ecb926f`; the callback side was left non-atomic as it was not in the code review's recommended-before-merge list. Consider parity upgrade as a follow-up.

---

## WS4 — Security & Migration Cleanup

### Status: ✅ Complete (9 commits, 10 new tests, 0 regressions)

**Commits on `v1.2.1-ws4`:**

```
ea3ad12 feat(paths): add EMBEDDINGS_DIR and RAG_DIR constants and env vars
8255c5c fix(tests): tighten test_paths_v121 isolation and default-anchor assertions
d2da91b fix(security): make EPUB path validation mandatory in import_epub()
b6658a8 test(epub): remove dev-DB-mutating positive test from path traversal regression suite
fa110da fix(tauri): resolve dev-mode lock path from HIME_PROJECT_ROOT instead of hardcoded literal
c378d5f fix(paths): replace hardcoded C:\Projekte\Hime in 8 data-prep scripts with HIME_PROJECT_ROOT
0f20037 fix(paths): replace hardcoded C:\Projekte\Hime in train_debug, train_restart_loop, check_format
5ec1ff0 feat(migration): add post-migration validator script
0e4c0e1 feat(migration): add HIME_SKIP_TRAINING_PROBE escape hatch
```

### Deliverables

- ✅ EPUB `import_epub()` validates path against `EPUB_WATCH_DIR` by default (commits `d2da91b` + `b6658a8`)
- ✅ 11 standalone scripts no longer reference `C:\Projekte\Hime` (commits `c378d5f` + `0f20037`)
- ✅ Tauri `lib.rs` dev-mode lock path is `HIME_PROJECT_ROOT`-driven with binary-relative fallback (commit `fa110da`)
- ✅ `paths.py` has `EMBEDDINGS_DIR` and `RAG_DIR` constants (commits `ea3ad12` + `8255c5c`)
- ✅ `scripts/verify_migration.py` available for post-migration validation, with `HIME_SKIP_TRAINING_PROBE` escape hatch (commits `5ec1ff0` + `0e4c0e1`)

### Known issues / follow-ups

- ⚠️ **LATENT v1.2.0 BUG DISCOVERED AND FIXED (WS4 T2):** `epub_service.py` `_validate_epub_path()` used `Path()` without importing `pathlib.Path`. Every call from `scan_watch_folder()` was crashing silently inside its `try/except Exception`. **This means `scan_watch_folder()` has been rejecting every EPUB since v1.2.0 merged — auto-import on startup has been broken.** After merging WS4 to main, the user should run a manual rescan of the EPUB watch folder to pick up any previously-rejected imports. 21 EPUBs currently sit in `data/epubs/`.
- ⚠️ **Second latent v1.2.0 bug (WS1 T10):** `routers/training.py` was missing `Field` from its pydantic import. Fix included in WS1 commit `043ee19`. The user's main worktree had a local uncommitted fix for this — identical to WS1's, merged cleanly.
- ⚠️ **Conda env dev deps installed:** `pytest-asyncio` and `aiosqlite` were listed in `pyproject.toml` but not installed. WS4 T2 installed them via pip. This affects all worktrees that use the `hime` env.
- ⚠️ **Tauri dev-mode fallback uses `current_exe()`**, which points to the cargo target dir (not the source tree). Devs MUST set `HIME_PROJECT_ROOT` before running `npm run tauri dev`. Add to setup docs.
- ⚠️ **`Path(settings.<x>)` indirections** in `training_monitor.py` and `training_runner.py` (14 occurrences) were NOT refactored — the v1.2.0 audit accepted them as acceptable indirection through `config.settings`. If disk migration requires direct `paths.py` imports everywhere, a follow-up pass would need to touch these.
- ⚠️ **Cargo.lock and `gen/schemas/*.json`** may show as modified in the worktree after a `cargo check` run. These are build artifacts and should not be committed. Can be safely discarded with `git restore`.
