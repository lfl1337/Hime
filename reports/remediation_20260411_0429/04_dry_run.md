# Phase 4 — Pipeline Dry-Run Mode (W6 + W8)

_Status: complete — awaiting Proceed with Phase 5_

## W6 — Centralized Pipeline v2 Config

### Changes
- Created: `app/backend/app/config/__init__.py` — full Settings class (migrated from flat `config.py` which was deleted; all existing imports `from ..config import settings` and `from .config import settings` continue to work unmodified)
- Created: `app/backend/app/config/pipeline_v2.py` — 8 model IDs, all env-overridable
- Deleted: `app/backend/app/config.py` (contents promoted to `config/__init__.py`)
- Modified: `app/backend/app/pipeline/stage2_merger.py` — removed hardcoded `_HF_MODEL_ID` and `_MODELS_DIR`/`_LOCAL_MODEL_DIR` block; now imports `STAGE2_MODEL_ID as _HF_MODEL_ID` and `STAGE2_LOCAL_PATH as _LOCAL_MODEL_DIR` from `..config.pipeline_v2`
- Modified: `app/backend/app/pipeline/stage3_polish.py` — removed hardcoded `_HF_MODEL_ID`, `_MODELS_DIR`, `_LOCAL_MODEL_DIR`; now imports `STAGE3_MODEL_ID as _HF_MODEL_ID` and `STAGE3_LOCAL_PATH as _LOCAL_MODEL_DIR` from `..config.pipeline_v2`

### Key diffs

**stage2_merger.py** — removed:
```python
_HF_MODEL_ID = "google/translategemma-27b-it"
_MODELS_DIR = Path(os.environ.get("HIME_MODELS_DIR") or Path(__file__).resolve().parents[4] / "modelle")
_LOCAL_MODEL_DIR = _MODELS_DIR / "translategemma-27b"
```
Added:
```python
from ..config.pipeline_v2 import STAGE2_MODEL_ID as _HF_MODEL_ID
from ..config.pipeline_v2 import STAGE2_LOCAL_PATH as _LOCAL_MODEL_DIR
```

**stage3_polish.py** — removed:
```python
_HF_MODEL_ID = "Qwen/Qwen3-30B-A3B"
_MODELS_DIR = Path(os.environ.get("HIME_MODELS_DIR") or Path(__file__).resolve().parents[4] / "modelle")
_LOCAL_MODEL_DIR = _MODELS_DIR / "qwen3-30b"
```
Added:
```python
from ..config.pipeline_v2 import STAGE3_MODEL_ID as _HF_MODEL_ID
from ..config.pipeline_v2 import STAGE3_LOCAL_PATH as _LOCAL_MODEL_DIR
```

---

## W8 — DryRunModel Stubs + HIME_DRY_RUN Flag

### Changes
- Modified: `app/backend/app/config/__init__.py` — added `hime_dry_run: bool = False` field (activated via `HIME_DRY_RUN=1` env var)
- Created: `app/backend/app/pipeline/dry_run.py` — `DryRunModel`, `make_dry_run_stage1_drafts`, `dry_run_stage2_merge`, `dry_run_stage3_polish`, `DryRunStage4Reader`, `DryRunStage4Aggregator`, `make_dry_run_stage4_reader`, `make_dry_run_stage4_aggregator`
- Modified: `app/backend/app/pipeline/runner_v2.py` — dry-run branching for all 5 stage calls (stage1, stage2, stage3-initial, stage3-retry, stage4 instantiation)

### Implementation notes
- `Stage1Drafts` requires `source_jp: str` (positional) and `jmdict: str` (not dict) — fixed from plan template
- `DryRunModel.generate()` format is `"[DRY-RUN {name}] {hash} {snippet}"` so `"[DRY-RUN {name}]"` is always a substring
- `Book.file_path` is NOT NULL UNIQUE — E2E test uses `file_path="test-dry-run.epub"` to satisfy constraint
- Settings mutation via `monkeypatch.setattr(_settings, "hime_dry_run", True)` — works because `runner_v2.py` holds a reference to the same Settings object (not frozen)

### Test Results
- `test_pipeline_v2_config.py`: 3/3 PASS
- `test_pipeline_dry_run.py`: 7/7 PASS
- `test_runner_v2_dry_run.py`: 1/1 PASS (E2E, 1.58s)
- `test_runner_v2_stage4_load.py` (C2 regression): 2/2 PASS

### CLI Smoke Test
```
HIME_DRY_RUN=1 uv run python -c "from app.config import settings; print(f'dry_run={settings.hime_dry_run}')"
# → dry_run=True

HIME_DRY_RUN=1 uvicorn app.main:app --host 127.0.0.1 --port 23420
curl http://127.0.0.1:23420/health
# → {"status":"ok","app":"hime","version":"1.1.2"}
```
Backend boots cleanly with HIME_DRY_RUN=1. No crash, health endpoint responds.

### Chrome MCP
Unavailable — browser extension not connected. UI baseline check skipped.

---

## Full Suite After Phase 4

```
274 passed, 2 failed, 1 skipped
```

Both failures are pre-existing, not caused by Phase 4:
1. `test_vault_organizer::test_cluster_similar_notes_no_model` — pre-existing assertion error
2. `test_conftest_isolation::test_backend_dir_hime_db_not_created` — pre-existing `app/backend/hime.db` pollution file (documented in MEMORY.md under "Conftest pollutes production DB")

11 new tests added: 3 (W6 config) + 7 (dry-run stubs) + 1 (E2E runner dry-run)
