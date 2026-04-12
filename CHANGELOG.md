# Changelog

## v2.0.0 — 2026-04-11 — Remediation Release

### Critical fixes
- **C1**: Downloaded `Qwen/Qwen3-30B-A3B` (~57 GB, 16 bf16 shards) to `modelle/qwen3-30b/` — Stage 3 Polish model weights are now present.
- **C2**: `runner_v2.py` now calls `aggregator.load(settings)` before `aggregator.aggregate()`. Stage 4 aggregation no longer crashes with AttributeError.
- **C3**: `scripts/train_generic.py` rewritten as a thin dispatcher; `scripts/training/configs/` and `scripts/training/trainers/` package added. All Pipeline v2 model configs (TranslateGemma-12B, Qwen3.5-9B, Qwen3-30B-A3B) now registered alongside legacy v1 configs (backward-compatible).
- **C4**: Data registry foundation — `data/registry.jsonl`, `scripts/hime_data.py` CLI (`register`/`list`/`export`), `GET /api/v1/data/registry` router. 4 training sources registered. Flywheel retraining is future work.
- **C5**: Curriculum-learning block added to `scripts/training_config.json` (strict / expanded / loose tiers, promotion trigger). Checkpoint cycle-1 preserved under pre-curriculum config.

### Warning fixes
- **W1**: Database consolidation — authoritative `hime.db` at project root selected; 3 duplicate copies archived to `archive/obsolete_dbs/`.
- **W2**: `PRAGMA foreign_keys = ON` enforced on every SQLAlchemy connection via event listener in `app/backend/app/database.py`.
- **W3**: Circular import between `epub_export_service` and `pipeline.runner_v2` resolved — `pipeline/__init__.py` no longer eagerly re-exports `run_pipeline_v2`; callers import directly from `app.pipeline.runner_v2`.
- **W4**: Downloaded `BAAI/bge-m3` to `modelle/embeddings/bge-m3/`. `modelle/embeddings/` and `data/rag/series_1.db` + `data/rag/series_2.db` populated from Obsidian vault markdown chunks (14 total).
- **W6**: Pipeline v2 model IDs centralised in `app/backend/app/config/pipeline_v2.py`. Stage 2 and Stage 3 now read their HF IDs and local paths from this single source (env-overridable).
- **W7**: Frontend test infrastructure — Vitest 2.x + React Testing Library 16.x + jsdom. Smoke tests for Translator, Comparison, Editor, Settings, BookLibrary, GlossaryEditor. 15 tests, all passing.
- **W8**: Pipeline `--dry-run` mode (`HIME_DRY_RUN=1`). `DryRunModel` stubs all four stages in `runner_v2.py`. Every integration test and the E2E test run end-to-end without loading model weights.
- **W9**: VERSION bumped to 2.0.0 across all 6 version files.

### Test infrastructure
- Backend: `temp_db`, `test_client`, `sample_book_fixture` fixtures; integration tests for 5 routers; E2E dry-run WebSocket pipeline test; 301 tests passing, 58% total coverage.
- Frontend: Vitest setup, Tauri/WebSocket/ResizeObserver mocks, per-view smoke tests, `npm test` CI script.

### Known gaps (documented, out of scope)
- **W5**: 10 backend routes without active frontend caller — classified in Phase 8 report; W5 annotations added to each router file.
- **W10**: eval_loss (1.0066) > target_loss (0.4) on Qwen2.5-32B checkpoint-12400 — overfitting mitigation requires retraining; curriculum block is the preparation step.
- **C4 flywheel**: Registry foundation only; incremental adapter updates and automatic retraining loop are follow-up projects.
- **POST-1**: Stage 2/3 model IDs use `os.environ.get()` at import time — `.env` file values require declaring fields in `Settings` (documented in REMEDIATION_REPORT).
- **POST-2**: All 21 production books have `series_id=None` → RAG indexer is a no-op against current library.

### Breaking changes
- `from app.pipeline import run_pipeline_v2` no longer works — use `from app.pipeline.runner_v2 import run_pipeline_v2`.
- Database connections now enforce foreign keys — orphan inserts raise `IntegrityError`.
- `app/backend/app/config.py` promoted to `app/backend/app/config/__init__.py` + `config/pipeline_v2.py` package; all `from app.config import settings` imports still work.
