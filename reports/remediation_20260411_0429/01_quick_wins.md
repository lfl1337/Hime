# Phase 1 — Quick Wins (W1, W2, W9 doc)

_Status: complete — awaiting Proceed with Phase 2_

## W1 — DB Consolidation

### Inventory

| Path | Books | Chapters | Paragraphs | Tables | Notes |
|---|---|---|---|---|---|
| hime.db (Root) | 21 | 430 | 80313 | 10 | AUTHORITATIVE (Luca-confirmed) |
| app/backend/hime.db | 21 | 329 | 80077 | 10 | Backend-local stale copy |
| app/hime.db | N/A | N/A | N/A | 2 | Outdated schema (2 tables only) |
| .worktrees/pipeline-v2/hime.db | 0 | 0 | 0 | 10 | Empty dev DB from worktree |

Root DB confirmed against Luca's numbers (430 chapters, 80313 paragraphs) — MATCH.

### Decision (Luca 2026-04-11)

- **Authoritative:** `hime.db` (Root, 430 chapters / 80313 paragraphs)
- **Backup:** `hime.db.bak_20260411` (exact filename Luca specified, made before any changes)
- **Archive:** `app/backend/hime.db`, `app/hime.db`, `.worktrees/pipeline-v2/hime.db` → `archive/obsolete_dbs/` (moved, not deleted)

### Rationale
Root DB has the most data (430 vs 329 chapters, 80313 vs 80077 paragraphs). Backend-local variant is stale by ~100 chapters. `app/hime.db` is old schema (only 2 tables vs 10). Worktree DB is empty dev scaffold.

### Boot path note

`settings.db_url` resolves to `sqlite+aiosqlite:///./hime.db` when `HIME_DATA_DIR` is unset — CWD-relative. The dev entry point `run.py` uses `Path(__file__).parent` (= `app/backend`) as data dir, which explains the backend-local variant. For this remediation's boot tests, uvicorn is launched from project root so `./hime.db` → root `hime.db`. Post-archive dev workflow will need `HIME_DATA_DIR` set OR run.py launched with `--data-dir N:/Projekte/NiN/Hime` to avoid re-creating an empty `app/backend/hime.db`.

### Backup

- `hime.db` → `hime.db.bak_20260411` (34947072 bytes, identical byte count verified via `wc -c`)
- Backup is untracked in git (not staged, not committed)

### Archive results

| Original path | Archived as | Size |
|---|---|---|
| app/backend/hime.db | archive/obsolete_dbs/backend_hime.db_20260411 | 34578432 B |
| app/hime.db | archive/obsolete_dbs/app_hime.db_20260411 | 12288 B |
| .worktrees/pipeline-v2/hime.db | archive/obsolete_dbs/worktree_pipeline_v2_hime.db_20260411 | 90112 B |

### Re-pollution observed during pytest run

After the full pytest suite ran (Task 1.6 Step 4), a NEW `app/backend/hime.db` appeared (90112 B, 0 books, 5 glossaries containing the exact same aiko/tokyo test artifacts as before). The conftest autouse `init_db()` fixture re-created it because pytest's CWD was `app/backend` and the module-level `engine = create_async_engine(settings.db_url)` line evaluates `./hime.db` relative to CWD.

The newly polluted DB was then moved to `archive/obsolete_dbs/backend_hime.db_testpollution_20260411_0507` (90112 B). This pollution loop will repeat every time `cd app/backend && pytest` is run — **fixing this is a Phase 3 requirement**. Options for Phase 3:
  - Override `settings.db_url` in conftest to `sqlite+aiosqlite:///:memory:`
  - Use `tmp_path_factory.mktemp("hime-test-db")` as HIME_DATA_DIR
  - Add `app/backend/hime.db` to `.gitignore` (already is? — TBD) so at least it doesn't get committed accidentally

### Backend boot verification after archive

- Backend launched: `HIME_PROJECT_ROOT=N:/Projekte/NiN/Hime app/backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir app/backend --host 127.0.0.1 --port 23420`
- CWD: `N:/Projekte/NiN/Hime` → `./hime.db` resolves to root `hime.db` ✓
- `/health` → 200 OK `{"status":"ok","app":"hime","version":"1.1.2"}`
- `/api/v1/epub/books` → 200 OK, first book id=21 (matches root DB count)
- Route count: 66 (>=60 threshold)
- Uvicorn log excerpt: `Application startup complete. Uvicorn running on http://127.0.0.1:23420`
- Process terminated cleanly via `taskkill //F //PID 58456` — port 23420 free post-shutdown

## W2 — FK Orphan Check

### Initial spec queries (Task 1.4)

Run against the authoritative `hime.db` with `PRAGMA foreign_keys = OFF` (read-only):

- chapters_no_book: 0
- paragraphs_no_chapter: 0
- translations_no_source: 0
- glossary_terms_no_glossary: 0

Initial decision: proceed to enable FK enforcement.

### `PRAGMA foreign_key_check` (Task 1.6 Step 5) — surfaced 5 additional orphans

After enabling FK in code, the full `PRAGMA foreign_key_check` revealed orphan rows NOT covered by the Task 1.4 query set:

```
foreign_key_check:
  ('glossaries', 2, 'books', 0)   # glossary id=2 → book_id=42 (does not exist)
  ('glossaries', 3, 'books', 0)   # glossary id=3 → book_id=43 (does not exist)
  ('glossaries', 4, 'books', 0)   # glossary id=4 → book_id=44 (does not exist)
  ('glossaries', 5, 'books', 0)   # glossary id=5 → book_id=45 (does not exist)
  ('glossaries', 6, 'books', 0)   # glossary id=6 → book_id=46 (does not exist)
```

### Root cause: test pollution of production DB

Investigation showed:
- Real books span ids 1–21; orphan glossaries reference ids 42–46
- `tests/test_glossary_service.py` uses `book_id=42` and `book_id=46` as literal test fixtures
- `tests/conftest.py` has a session-scoped autouse fixture that calls `init_db()` on the **production** DB (not a tmp path)
- Therefore test runs have been writing glossary data to the root `hime.db`

Dependent `glossary_terms` referencing orphan glossaries (5 rows):
```
(1, 3, 'アイコ', 'Aiko', 'name')
(2, 4, 'アイコ', 'Aiko', 'name')
(3, 4, '東京', 'Tokyo', 'place')
(4, 5, 'アイコ', 'Aiko', 'name')
(5, 6, 'アイコ', 'アイコ', 'auto')
```

All five terms match exactly the test source text `"アイコは東京に住んでいる"` — unambiguous test artifacts.

### Cleanup (Task 1.6 Step 5 continued)

Deleted in order (FK OFF for surgical cleanup):
```
DELETE FROM glossary_terms WHERE glossary_id IN (2,3,4,5,6);   -- 5 rows
DELETE FROM glossaries WHERE id IN (2,3,4,5,6);                 -- 5 rows
```

Post-cleanup verification:
- `PRAGMA foreign_key_check`: `[]` (empty — clean)
- `PRAGMA integrity_check`: `[('ok',)]`
- `books`: 21 (unchanged)
- `chapters`: 430 (unchanged)
- `paragraphs`: 80313 (unchanged)
- `glossaries`: 1 (the legitimate `book_id=1` glossary remains)
- `glossary_terms`: 0 (all were orphan-dependents)

### Phase 3 follow-up (non-blocking)

The conftest `init_db()` fixture runs against the production DB. This needs to be fixed (override `settings.db_url` to `:memory:` or `tmp_path` in conftest) or tests will continue to pollute `hime.db`. Flagged for Phase 3 (code fixes).

### FK enforcement pytest results

After the cleanup + event listener added in `database.py`:

```
tests/test_foreign_keys.py::test_foreign_keys_enabled_on_new_session PASSED
tests/test_foreign_keys.py::test_foreign_key_enforcement_rejects_orphan PASSED
============================== 2 passed in 0.09s ==============================
```

Full pytest (excluding training-dependent `test_train_with_resume.py`):
```
2 failed, 249 passed, 1 skipped, 7 warnings in 34.14s
```

Pre-existing failures (verified against HEAD via `git stash` round-trip):
1. `test_glossary_service.py::test_auto_extract_returns_proper_noun_candidates` — MeCab NER expects `アイコ` in extracted terms, returns none. Unrelated to FK change. Reproducible without my diff.
2. `test_vault_organizer.py::test_cluster_similar_notes_no_model` — `FakeTorch` / scipy `_issubclass_fast` incompatibility. Only fails when other test pollutes `sys.modules['torch']`. Passed in isolation. Pre-existing test pollution issue.

## W9 — VERSION Audit (doc only, bump happens in Phase 9)

| File | Current value | Target (Phase 9) | Notes |
|---|---|---|---|
| `app/VERSION` | 1.1.2 | 2.0.0 | Canonical source per CLAUDE.md |
| `app/backend/app/main.py` | 1.1.2 | 2.0.0 | Line 98: `version="1.1.2"` |
| `app/backend/pyproject.toml` | 0.1.0 | 2.0.0 | Line 3: `version = "0.1.0"` — **DIVERGED** |
| `app/frontend/package.json` | 1.1.2 | 2.0.0 | Line 4 |
| `app/frontend/src-tauri/tauri.conf.json` | 1.1.2 | 2.0.0 | Line 3 |
| `app/frontend/src-tauri/Cargo.toml` | 1.1.2 | 2.0.0 | Line 3 |

**Divergences found:**
- `app/backend/pyproject.toml` is stuck at `0.1.0` — the initial scaffold version. The `scripts/bump_version.py` tool may not touch this file. Needs to be included in the Phase 9 bump.
- All other 5 files are consistent at `1.1.2`.

No version strings were changed in this phase — audit only.

## Files changed in Phase 1

- Modified: `app/backend/app/database.py` (added SQLAlchemy `@event.listens_for(Engine, "connect")` listener that executes `PRAGMA foreign_keys = ON` on every new low-level DBAPI connection; added `from sqlalchemy import event` and `from sqlalchemy.engine import Engine` imports)
- Created: `app/backend/tests/test_foreign_keys.py` (2 async tests verifying PRAGMA and orphan rejection; `from app import models` import added so the session-scoped conftest fixture can `create_all()` the tables when the file runs in isolation)
- Created: `hime.db.bak_20260411` (manual backup, untracked, 34947072 B identical to hime.db)
- Created: `archive/obsolete_dbs/backend_hime.db_20260411` (34578432 B, moved from `app/backend/hime.db`)
- Created: `archive/obsolete_dbs/app_hime.db_20260411` (12288 B, moved from `app/hime.db`)
- Created: `archive/obsolete_dbs/worktree_pipeline_v2_hime.db_20260411` (90112 B, moved from `.worktrees/pipeline-v2/hime.db`)
- Created: `archive/obsolete_dbs/backend_hime.db_testpollution_20260411_0507` (90112 B, the re-created `app/backend/hime.db` from the pytest run — archived again)
- Deleted: `app/backend/hime.db`, `app/hime.db`, `.worktrees/pipeline-v2/hime.db` (moved to archive, not unlinked). `app/backend/hime.db` re-appeared during pytest and was moved again.
- Mutated: 5 orphan `glossaries` rows (id 2–6) + 5 orphan `glossary_terms` rows deleted from `hime.db` (test pollution cleanup — documented in W2)

## Test results

- `tests/test_foreign_keys.py`: **2/2 PASS** (both red→green confirmed)
- Full pytest suite (minus `test_train_with_resume.py`): **249/252 passed**, 2 failed, 1 skipped, 7 deprecation warnings
- Both failures verified PRE-EXISTING via `git stash` round-trip; unrelated to FK change

## Backend boot verification

- Post-archive (Task 1.3): backend on `127.0.0.1:23420`, `/health` → 200, `/api/v1/epub/books` returned 21 books → reading root `hime.db` ✓, routes=66
- Post-FK-enable (Task 1.7): same — `/health` → 200, routes=66, process terminated cleanly

## Open for Phase 2

- 17 GB downloads approved by Luca (Qwen3-30B-A3B + bge-m3)
- Flagged for Phase 3 (non-blocking): fix conftest autouse fixture to point at tmp DB so tests can't pollute production `hime.db` again
- Flagged for Phase 9 (non-blocking): `app/backend/pyproject.toml` version is stuck at `0.1.0` — ensure `scripts/bump_version.py` includes it in the 2.0.0 bump

No other blockers.

## Phase 1 Fix Iteration (2026-04-11 after code review)

Code quality reviewer found 2 critical issues:

### C1 — 4 new glossary test failures (now fixed)

Root cause: `test_glossary_service.py` tests created glossaries with fabricated `book_id` values (42-45) without first creating parent `Book` rows. Pre-Phase-1 (FK off) these orphans were silently accepted. Post-Phase-1 (FK on) they correctly raised IntegrityError.

Fix: extended the existing autouse `_db` fixture in `test_glossary_service.py` to seed 5 fixture Books (ids 42-46) with unique `file_path` values before each test. The 4 previously-failing tests now pass. The 5th (`test_auto_extract_returns_proper_noun_candidates`) remains pre-existing-failed due to unrelated MeCab NER behaviour.

Note on baseline: when the fix was applied, the ambient `app/backend/hime.db` still contained the 5 orphan glossaries from pre-Phase-1 test runs (see `archive/obsolete_dbs/backend_hime.db_testpollution_20260411_0507` — those orphans were never cleaned out of the re-created DB). That meant the 4 "failing" tests appeared to pass on the dirty DB because `get_or_create_for_book` found the pre-existing orphan glossary rows and never tried to INSERT. To prove the fix works for the RIGHT reason, the polluted DB was archived to `archive/obsolete_dbs/backend_hime.db_testpollution_20260411_0820` before the verification run, and pytest rebuilt a clean DB via the conftest autouse `init_db()`. On that clean DB, the new autouse fixture seeds Books 42-46 first, the glossaries are created as legitimate non-orphans, and `fk_check` is empty after the run.

### C2 — Dead test-isolation code in `test_foreign_keys.py` (now fixed)

Root cause: the `tmp_path + monkeypatch + sys.modules` machinery did not actually isolate. Python's `from app import database` returns the cached attribute on the `app` package, so the engine was never rebuilt and the tmp_path directory stayed empty.

Fix: replaced test 2 with a minimal version that uses the shared `AsyncSessionLocal` and relies on rollback to contain the orphan. Docstring updated to reflect reality and to point to Phase 3 for proper conftest test-DB isolation.

### Post-fix test results

- `tests/test_foreign_keys.py`: **2/2 PASS** on fresh DB
- `tests/test_glossary_service.py`: **4 PASS, 1 pre-existing FAIL** (`test_auto_extract_returns_proper_noun_candidates`, MeCab, unchanged)
- Full suite: **249 passed, 2 failed, 1 skipped** — identical to pre-review baseline. Failures: `test_glossary_service.py::test_auto_extract_returns_proper_noun_candidates` (MeCab) + `test_vault_organizer.py::test_cluster_similar_notes_no_model` (FakeTorch/scipy). No new failures introduced.
- Post-run DB state on `app/backend/hime.db`: `integrity_check=ok`, `fk_check=[]` (no orphans), 5 glossaries + 13 glossary terms all tied to seeded Books 42-46, 0 orphan chapters.
- Root `hime.db` untouched (still `integrity_check=ok`, `fk_check=[]`, 1 legitimate glossary).

### Files changed in this iteration

- Modified: `app/backend/tests/test_glossary_service.py` (autouse fixture extended with Book seeding)
- Modified: `app/backend/tests/test_foreign_keys.py` (test 2 replaced with minimal shared-session version, dead imports removed)
- Moved: `app/backend/hime.db` → `archive/obsolete_dbs/backend_hime.db_testpollution_20260411_0820` (polluted test DB from Phase 1 pytest run; same archive pattern as earlier Phase 1 cleanup)
