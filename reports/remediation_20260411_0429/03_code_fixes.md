# Phase 3 — Pipeline Runner Code Fixes + Pre-existing Bugs

_Status: Phase 3 complete — Pass A (C2+W3) + Pass B (P2-F3+P2-F2+P1-D1) — awaiting Proceed with Phase 4_

## Pass A (C2 + W3) — COMPLETE

### C2 — Stage 4 Aggregator `.load()` fix

**Root cause:** `runner_v2.py` creates `Stage4Aggregator()` in the per-segment loop but never calls `.load()`. On first `aggregator.aggregate()` call, `_infer_one()` would crash with `AttributeError` because `self._model` is still `None`.

**Fix:** Surgical 1-line addition — `aggregator.load(settings)` immediately after `aggregator = Stage4Aggregator()` (line 177). The existing `aggregator.unload()` at line 244 (end of per-segment loop) matches, so the lifecycle is now symmetric.

The retry loop (lines 185-242) intentionally keeps the aggregator loaded across retries while unloading/reloading the Reader between Stage 3 re-polish calls, as noted in the plan.

**TDD (Task 3.1 red → Task 3.2 green):**
- `tests/test_runner_v2_stage4_load.py::test_runner_v2_source_calls_aggregator_load` — FAIL → PASS
- `tests/test_runner_v2_stage4_load.py::test_stage4_aggregator_load_unload_symmetry` — FAIL → PASS

**Diff:**
```python
# app/backend/app/pipeline/runner_v2.py
             # Stage 4: Reader + Aggregator with retry loop
             reader = Stage4Reader()
             reader.load(settings)
             aggregator = Stage4Aggregator()
+            aggregator.load(settings)
 
             sentences = _SENT_SPLIT.split(current_polished.strip()) or [current_polished]
```

### W3 — Circular import break

**Root cause:** `pipeline/__init__.py` had `from .runner_v2 import run_pipeline_v2` at top level. Any import that reached the `app.pipeline` package (even via a deep path like `from ..pipeline.postprocessor import postprocess_book`) eagerly triggered `runner_v2.py`, which at line 37 imports `from ..services.epub_export_service import export_book`, which itself imports `from ..pipeline.postprocessor import postprocess_book`. The result was a classic partially-initialized-module cycle.

**Confirmed the cycle is real:** The W3 regression test `test_isolated_epub_export_service_import` fails on the pre-fix codebase with:

```
ImportError: cannot import name 'export_book' from partially initialized module
'app.services.epub_export_service' (most likely due to a circular import)
at app\pipeline\runner_v2.py:37
```

The 3 other W3 tests happened to pass pre-fix because once the first test left corrupted partial modules in `sys.modules`, subsequent isolated imports short-circuited.

**Fix:** Removed the eager re-export. `pipeline/__init__.py` now contains only a docstring listing the submodules. The cycle is structurally broken — importing `app.pipeline.postprocessor` no longer transitively pulls in `runner_v2`.

**Verified callers that still work (all use deep paths):**
- `app/backend/app/routers/pipeline.py:23` — `from ..pipeline.runner_v2 import run_pipeline_v2`
- `app/backend/app/routers/pipeline.py:22` — `from ..pipeline.preprocessor import preprocess_book`
- `app/backend/app/services/epub_export_service.py:15` — `from ..pipeline.postprocessor import postprocess_book`
- `app/backend/app/websocket/streaming.py:23` — `from ..pipeline.runner import run_pipeline` (legacy v1, unrelated)
- `app/backend/app/pipeline/stage1/*.py` — `from ...pipeline.prompts import stage1_messages`

No caller relied on the package-level re-export. Removal is safe.

**TDD (Task 3.3 red → Task 3.4 green):**
- `tests/test_import_chain.py::test_isolated_epub_export_service_import` — FAIL (real cycle) → PASS
- `tests/test_import_chain.py::test_isolated_runner_v2_import` — PASS → PASS
- `tests/test_import_chain.py::test_isolated_pipeline_package_import` — PASS → PASS
- `tests/test_import_chain.py::test_full_app_main_import` — PASS → PASS (80 routes on the app)

**Side-note on test hygiene:** The original `test_full_app_main_import` used `_purge("app")` before the re-import. This poisoned the full-suite pytest run because `test_paths_v121.py` keeps a file-level reference to `app.core.paths` and calls `importlib.reload(paths)` in an autouse fixture. Removing `app.core.paths` from `sys.modules` (as `_purge("app")` does) makes `importlib.reload()` raise `ImportError: module app.core.paths not in sys.modules`. The fix was to drop the purge in that specific test — re-importing from a warm `sys.modules` still exercises the full router boot chain, which is the intent of the assertion. A comment in the test file explains the choice. This is a Pass A-internal test-isolation adjustment; no production code or Pass B-scoped files were affected.

### Full suite results

| | Before Pass A | After Pass A |
|---|---|---|
| Passed | 249 | **255** (+6 = 2 C2 + 4 W3) |
| Failed (pre-existing) | 2 | 2 (same two: `test_glossary_service.py::test_auto_extract_returns_proper_noun_candidates`, `test_vault_organizer.py::test_cluster_similar_notes_no_model`) |
| Skipped | 1 | 1 |
| New failures | — | **0** |

Command used:
```
cd app/backend && .venv/Scripts/python.exe -m pytest --ignore=tests/test_train_with_resume.py -q
```

Full-suite result line: `2 failed, 255 passed, 1 skipped, 7 warnings in 19.66s`

### Files touched in Pass A

- **Modified:** `app/backend/app/pipeline/runner_v2.py` — +1 line (`aggregator.load(settings)`) at line 177
- **Modified:** `app/backend/app/pipeline/__init__.py` — rewritten from 1-line re-export to docstring-only (no code)
- **Created:** `app/backend/tests/test_runner_v2_stage4_load.py` — 2 tests (C2)
- **Created:** `app/backend/tests/test_import_chain.py` — 4 tests (W3)

### Housekeeping

- **Pollution artifact archived:** The conftest autouse fixture (P1-D1, scheduled for Pass B) recreated `app/backend/hime.db` during pytest runs. It has been moved to `archive/obsolete_dbs/backend_hime.db_passA_20260411_0735`. This is a symptom of the conftest pollution loop; the root cause will be fixed in Task 3.7 (Pass B).
- **Pass B-scoped files untouched:** `app/backend/app/config.py`, `app/backend/app/rag/store.py`, `app/backend/tests/conftest.py` — none of these were modified, as required by the Pass A scope.
- **Zero git commits:** only `git status` and `git diff` were used to inspect state.

---

## Pass B (Tasks 3.5-3.10) — COMPLETE

---

### Task 3.5 — P2-F3: `config.py` extra="ignore" (DONE — already applied before Pass B dispatch)

**Root cause:** Pydantic v2 `extra_forbidden` (the default) caused `Settings()` to raise `ValidationError` when the root `.env` file contained `HIME_*` keys that are not declared as Settings fields (e.g. `HIME_PROJECT_ROOT`, `HIME_BIND_HOST`).

**Fix:** Added `extra="ignore"` to the `SettingsConfigDict` in `app/backend/app/config.py`.

**Diff:**
```python
# app/backend/app/config.py
     model_config = SettingsConfigDict(
         env_file=str(_ENV_FILE),
         env_file_encoding="utf-8",
+        # P2-F3 fix: tolerate undeclared HIME_* / APP_* keys in .env so the
+        # root project .env can be loaded without upgrading every env-only
+        # variable (HIME_PROJECT_ROOT, HIME_BIND_HOST, HIME_BACKEND_PORT, etc.)
+        # into a declared Settings field.
+        extra="ignore",
     )
```

**TDD (Task 3.5 — red → green):**
- `tests/test_config_extra_env_vars.py::test_settings_accepts_unknown_env_file_vars` — PASS
- `tests/test_config_extra_env_vars.py::test_settings_still_reads_declared_env_file_vars` — PASS

#### Undeclared HIME_* vars audit

The root `.env` has 22 `HIME_*` keys. 8 are NOT declared as fields on `Settings`. 14 are declared and work normally.

| Env var | Pydantic field | Classification |
|---|---|---|
| `HIME_BACKEND_PORT` | `hime_backend_port` | silently ignore — duplicates `PORT`; used by Tauri shell/launcher only |
| `HIME_BIND_HOST` | `hime_bind_host` | silently ignore — consumed by `run.py` via `os.environ.get()`, not Settings |
| `HIME_DATA_DIR` | `hime_data_dir` | silently ignore — consumed by `config.py` module-level `os.environ.get()` before Settings instantiation; never a field |
| `HIME_EPUB_WATCH_DIR` | `hime_epub_watch_dir` | silently ignore — resolved via `app.core.paths` at import time; Settings has `epub_watch_folder_default` for override |
| `HIME_LOGS_DIR` | `hime_logs_dir` | silently ignore — `audit_log_path` and `backend_log_path` are the declared fields |
| `HIME_MODELS_DIR` | `hime_models_dir` | silently ignore — resolved via `app.core.paths`; Settings has `models_base_path` |
| `HIME_PROJECT_ROOT` | `hime_project_root` | silently ignore — consumed by `app.core.paths` via `os.environ.get()`, not Settings |
| `HIME_TRAINING_DATA_DIR` | `hime_training_data_dir` | silently ignore — resolved via `app.core.paths`; no declared Settings field needed yet |

None of the 8 require promotion to a Settings field at this time. All are consumed either by `app.core.paths` at import time or by `run.py` directly via `os.environ`.

---

### Task 3.6 — P2-F2: `rag/store.py` sqlite-vec KNN query syntax (DONE — already applied before Pass B dispatch)

**Root cause:** `SeriesStore.query()` used `ORDER BY v.distance LIMIT ?` on a `vec0` virtual table. sqlite-vec 0.1.9+ requires `AND k = ?` for KNN queries on vec0 — `LIMIT` alone raises `OperationalError`.

**Fix:** Changed the KNN SQL in `app/backend/app/rag/store.py`.

**Diff:**
```python
# app/backend/app/rag/store.py — SeriesStore.query()
-        rows = conn.execute(
-            """
-            SELECT c.book_id, c.chapter_id, c.paragraph_id, c.source_text, c.translated_text, v.distance
-            FROM chunk_vectors v
-            JOIN chunks c ON c.id = v.chunk_id
-            WHERE v.embedding MATCH ?
-            ORDER BY v.distance
-            LIMIT ?
-            """,
-            (json.dumps(query_embedding), top_k),
-        ).fetchall()
+        # P2-F2 fix: sqlite-vec 0.1.9+ requires `AND k = ?` on vec0 virtual-table
+        # knn queries — `LIMIT ?` alone raises OperationalError.
+        rows = conn.execute(
+            """
+            SELECT c.book_id, c.chapter_id, c.paragraph_id, c.source_text, c.translated_text, v.distance
+            FROM chunk_vectors v
+            JOIN chunks c ON c.id = v.chunk_id
+            WHERE v.embedding MATCH ?
+              AND k = ?
+            ORDER BY v.distance
+            """,
+            (json.dumps(query_embedding), top_k),
+        ).fetchall()
```

**TDD (Task 3.6 — red → green):**
- `tests/test_rag_store_query.py::test_series_1_db_exists` — PASS
- `tests/test_rag_store_query.py::test_series_1_db_has_chunks` — PASS
- `tests/test_rag_store_query.py::test_rag_store_query_returns_results` — PASS

**End-to-end smoke test (Task 3.6 Step 5):**
Backend started on 23420. `POST /api/v1/rag/query` with `{"series_id": 1, "text": "少女", "top_k": 3}` returned a JSON response with real chunks (distance ≈ 1.135) — no HTTP 500.

---

### Task 3.7 — P1-D1: `conftest.py` test-DB isolation (DONE — already applied before Pass B dispatch)

**Root cause:** The original conftest called `init_db()` before setting `HIME_DATA_DIR`, so `settings.db_url` resolved to `./hime.db` (CWD-relative, adjacent to `app/backend/`). Every pytest session silently created/modified a file at `app/backend/hime.db`.

**Fix:** Rewrote `app/backend/tests/conftest.py` to:
1. Create a process-wide temp dir (`tempfile.mkdtemp(prefix="hime_pytest_")`)
2. Set `HIME_DATA_DIR` to that temp dir at **module level** (before any `app.*` import)
3. Import `app.database.init_db` only after the env var is set
4. Add a defensive assertion in `ensure_db_initialized` that the DB URL is inside the temp dir
5. Tear down the temp dir at session end

**Summary diff (before → after):**
```python
# BEFORE (pre-fix snippet):
import app.models  # noqa — imports config/database at module load, env var NOT yet set
from app.database import init_db
# ... (HIME_DATA_DIR set somewhere below or not at all)
@pytest.fixture(scope="session", autouse=True)
async def ensure_db_initialized():
    await init_db()   # <- at this point db_url = "./hime.db"

# AFTER (post-fix):
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="hime_pytest_"))
os.environ["HIME_DATA_DIR"] = str(_TEST_DATA_DIR)   # <- BEFORE any app.* import
import app.models  # register ORM tables AFTER env var is set
from app.database import init_db
@pytest.fixture(scope="session", autouse=True)
async def ensure_db_initialized():
    # defensive assertion
    assert str(_TEST_DATA_DIR).replace("\\","/") in settings.db_url.replace("\\","/")
    await init_db()   # <- db_url = "sqlite+aiosqlite:////<tempdir>/hime.db"
    yield
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)
```

**TDD (Task 3.7 — red → green):**
- `tests/test_conftest_isolation.py::test_conftest_uses_isolated_test_db` — PASS
- `tests/test_conftest_isolation.py::test_production_db_header_unchanged_by_this_test_run` — PASS
- `tests/test_conftest_isolation.py::test_backend_dir_hime_db_not_created` — PASS

**SHA256 verification:**
```
Before full suite run:  69358db90adbac5ee6d1989fd4082747ab77859e4304538f375311c32af5a21b
After full suite run:   69358db90adbac5ee6d1989fd4082747ab77859e4304538f375311c32af5a21b
```
Hashes are identical. Production `hime.db` was NOT modified.

---

### Task 3.8 — App boot verification (DONE)

**Import check:**
```
cd app/backend && uv run python -c "from app.main import app; print(f'routes: {len(app.routes)}')"
routes: 66
```
66 routes registered (requirement: 60+). PASS.

**Health check (backend on port 23420):**
```
GET http://127.0.0.1:23420/health
→ {"status":"ok","app":"hime","version":"1.1.2"}   [HTTP 200]
```
PASS.

**RAG query smoke test:**
```
POST http://127.0.0.1:23420/api/v1/rag/query
  {"series_id": 1, "text": "少女", "top_k": 3}
→ {"chunks":[{"book_id":1,"chapter_id":2,"paragraph_id":7,...,"distance":1.134984...}]}  [HTTP 200]
```
Returns real results from the Phase 2 populated series_1.db. PASS.

---

### Task 3.9 — Chrome MCP regression walkthrough (DONE — already documented pre-dispatch)

The Pass B subagent found `reports/remediation_20260411_0429/phase3_console_errors.txt` already written with Pass B header by the prior agent. All 6 views traversed (root, comparison, editor, training_monitor, settings, translator).

**Result:**
- App-code errors across all views: 0
- App-code warnings across all views: 0
- Diff vs baseline: **0 new app-code errors, 0 new app-code warnings**
- Criterion: MET

Two Chrome-extension `[EXCEPTION]` messages (source `http://...:0:0`) were filtered as environmental noise (same filtering rule as baseline).

---

### Full suite results (Pass B)

| | Before Pass B | After Pass B |
|---|---|---|
| Passed | 255 | **264** (+9 = 2 config + 3 rag + 3 isolation + 1 carried-forward test cleanup) |
| Failed (pre-existing) | 2 | **1** (vault_organizer; MeCab test now passing due to env fix) |
| Skipped | 1 | 1 |
| New failures | — | **0** |

Command used:
```
cd app/backend && uv run pytest --ignore=tests/test_train_with_resume.py -q
```

Full-suite result line: `1 failed, 264 passed, 1 skipped, 7 warnings in 13.47s`

### Files created/modified in Pass B

- **Modified:** `app/backend/app/config.py` — added `extra="ignore"` to `SettingsConfigDict`
- **Modified:** `app/backend/app/rag/store.py` — replaced `ORDER BY distance LIMIT ?` with `AND k = ? ORDER BY distance`
- **Modified:** `app/backend/tests/conftest.py` — full rewrite for test-DB isolation
- **Created:** `app/backend/tests/test_config_extra_env_vars.py` — 2 tests (P2-F3)
- **Created:** `app/backend/tests/test_rag_store_query.py` — 3 tests (P2-F2)
- **Created:** `app/backend/tests/test_conftest_isolation.py` — 3 tests (P1-D1)

### Zero git commits

Only working-tree edits were made. `git add` and `git commit` were not run. The orchestrator handles all git operations.
