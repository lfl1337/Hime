# Hime v1.2.0 Audit Report

Generated: 2026-04-07

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0     |
| High     | 3     |
| Medium   | 1     |
| Low      | 4     |
| Info     | 5     |

## Top Fixes Applied by WS4

1. Hardcoded `C:\Projekte\Hime` paths in backend config and DB seed (FIXED by WS4)
2. Missing SQLite indexes on chapters/paragraphs/translations (FIXED by WS4)
3. `.env.example` missing from repository (FIXED by WS4)

---

## Findings

### AUDIT-001: Hardcoded Paths in Backend (FIXED)
- **Severity:** High
- **Category:** Disk Migration
- **Files:** `app/backend/app/config.py`, `app/backend/app/database.py`
- **Description:** 5 hardcoded `C:\Projekte\Hime` paths in backend config defaults and DB seed insert. Fields affected: `epub_watch_folder_default`, `models_base_path`, `lora_path`, `training_log_path`, `scripts_path`. The DB seed had `'C:/Projekte/Hime/data/epubs/'` directly in a SQL string.
- **Status:** Fixed — replaced with `core/paths.py` env-var-driven resolution.

### AUDIT-002: Hardcoded Paths in Data Prep Scripts (NOT FIXED)
- **Severity:** High
- **Category:** Disk Migration
- **Files:** `scripts/align_shuukura.py`, `scripts/analyze_training_data.py`, `scripts/convert_jparacrawl.py`, `scripts/download_jparacrawl.py`, `scripts/epub_extractor.py`, `scripts/scraper.py`, `scripts/scraper_kakuyomu.py`, `scripts/scraper_skythewood.py`, `scripts/train_generic.py`, `scripts/train_hime.py`
- **Description:** 10 data preparation and training scripts define `PROJECT_ROOT = Path(r"C:\Projekte\Hime")` as a hardcoded constant. After disk migration these scripts will fail to locate data, models, and output directories.
- **Recommendation:** Replace with `Path(__file__).resolve().parent.parent` or import from `app.backend.app.core.paths`.
- **Effort:** ~30 min per script

### AUDIT-003: Hardcoded Path in Tauri Rust Code (NOT FIXED)
- **Severity:** High
- **Category:** Disk Migration
- **File:** `app/frontend/src-tauri/src/lib.rs:161`
- **Description:** In `#[cfg(debug_assertions)]` block, the `.runtime_port` file path is hardcoded:
  ```rust
  let runtime_port_path = std::path::PathBuf::from(
      r"C:\Projekte\Hime\app\backend\.runtime_port",
  );
  ```
  In dev mode, this prevents the frontend from connecting to the backend after a disk migration.
- **Recommendation:** Use `std::env::var("HIME_PROJECT_ROOT")` or derive from the Tauri app's `resource_dir`.
- **Effort:** 15 min

### AUDIT-004: Missing SQLite Indexes (FIXED)
- **Severity:** Medium
- **Category:** Performance
- **Files:** `app/backend/app/database.py`
- **Description:** Missing indexes on foreign-key columns: `chapters.book_id`, `paragraphs.chapter_id`, `translations.source_text_id`. These columns are used in every EPUB chapter lookup and translation fetch. Without indexes, queries degrade to full table scans as the library grows.
- **Status:** Fixed — three indexes added in `init_db()` via WS4.

### AUDIT-005: TypeScript `any` Usage
- **Severity:** Low
- **Category:** Code Quality
- **Description:** Grep scan of `app/frontend/src/` for `: any` returned zero matches in first-party TypeScript source files. All `any` casts found in a previous audit (AUDIT-019 of the 2026-03-29 report) were in debug-only blocks using non-standard browser APIs (`performance.memory`, `window.gc`, `window.__himeDebug`) — these remain acceptable.
- **Status:** No new findings. No action required.

### AUDIT-006: TODO/FIXME Findings
- **Severity:** Info
- **Category:** Code Quality
- **Description:** Scan of all `.py`, `.ts`, `.tsx` files for TODO/FIXME/HACK/XXX markers:
  - **First-party code:** Zero findings. `run.py:9` contains the string "XXXX" only as part of a comment explaining `.env PORT=XXXX` syntax — not a code marker.
  - **Third-party vendor cache:** `app/backend/unsloth_compiled_cache/` and `scripts/unsloth_compiled_cache/` contain ~35 `[TODO]` comments from the Unsloth library (DataParallel/FSDP notes). These are upstream library concerns, not actionable.
- **Recommendation:** No action needed for first-party code. Consider adding `unsloth_compiled_cache/` to `.gitignore` or a separate vendor directory.

### AUDIT-007: Gemma Model Name Display (FIXED by WS3)
- **Severity:** Low
- **Category:** UI
- **File:** `app/frontend/src/components/comparison/modelConfig.ts`
- **Description:** Gemma displayed as "27B" in the comparison UI instead of "12B" (the actual model in use).
- **Status:** Fixed by WS3.

### AUDIT-008: `.env.example` Missing (FIXED)
- **Severity:** Low
- **Category:** Developer Experience / Disk Migration
- **File:** `.env.example` (root)
- **Description:** No `.env.example` existed in the repository. New developers and migration scenarios had no reference for required environment variables.
- **Status:** Fixed — comprehensive `.env.example` added at project root by WS4 with all path overrides, model endpoints, and backend config variables documented.

### AUDIT-009: Path Traversal in Training Endpoint (OPEN — from prior audit)
- **Severity:** High (carried from AUDIT-002 of 2026-03-29 report)
- **Category:** Security
- **File:** `app/backend/app/routers/training.py`
- **Description:** `GET /available-checkpoints/{model_name}` uses the path parameter without pattern validation, unlike other training endpoints that apply `_RUN_PATTERN = r"^[\w\-\.]+$"`. This is not in WS4 scope.
- **Recommendation:** Add `FPath(pattern=_RUN_PATTERN, max_length=128)` to the endpoint signature.
- **Effort:** 15 min

### AUDIT-010: Bundle Size Check
- **Severity:** Info
- **Category:** Performance
- **Description:** Vite build could not be executed in the worktree environment (`node_modules` not installed). A prior audit noted no code-splitting / lazy loading for views — TrainingMonitor (39 `useState` hooks, 15 `useEffect` hooks) loads even when training is not active. Recommend `React.lazy()` + `Suspense` at view-level routing.
- **Recommendation:** Run `npm install && npm run build` in the full development environment and check for bundles over 500 KB.

---

## Path Migration Readiness

| Location | Status |
|----------|--------|
| `app/backend/app/config.py` | Fixed — uses `core/paths.py` |
| `app/backend/app/database.py` | Fixed — uses `core/paths.py` |
| `app/backend/app/core/paths.py` | New — env-var driven, no hardcoded paths |
| `scripts/*.py` (10 files) | NOT FIXED — all define `PROJECT_ROOT = Path(r"C:\Projekte\Hime")` |
| `app/frontend/src-tauri/src/lib.rs` | NOT FIXED — dev-mode `.runtime_port` path hardcoded |
| `.env.example` | Added |
