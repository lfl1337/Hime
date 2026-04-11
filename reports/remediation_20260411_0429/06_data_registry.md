# Phase 6 — Data Registry Foundation (C4)

_Status: complete — awaiting Proceed with Phase 7_

## Schema

| Field | Type | Description |
|---|---|---|
| `id` | str | Unique identifier for the dataset |
| `path` | str | Repo-relative path to the JSONL file (forward slashes) |
| `kind` | str | Category: `parallel_corpus`, `curated_lightnovel`, `literary_aligned`, `synthetic` |
| `source` | str | Human-readable source name |
| `lines` | int | Actual line count (measured at registration time) |
| `quality_field` | str | JSONL field used as score (empty if none) |
| `quality_range` | list[float] | `[min, max]` of quality_field values (empty if field absent) |
| `added` | str | ISO 8601 timestamp of registration |
| `notes` | str | Free-form notes |

## CLI Results

### Registered files

```
id                               kind                        lines  path
--------------------------------------------------------------------------------
jparacrawl_500k                  parallel_corpus            500000  data/training/jparacrawl_500k.jsonl
hime_training_filtered           curated_lightnovel         104866  data/training/hime_training_filtered.jsonl
shuukura_wn_aligned              literary_aligned               66  data/training/shuukura_wn_aligned.jsonl
hime_training_all                curated_lightnovel         104932  data/training/hime_training_all.jsonl
```

### Actual vs. spec line counts

| id | Spec estimate | Actual |
|---|---|---|
| jparacrawl_500k | 500,000 | 500,000 (exact) |
| hime_training_filtered | 104,866 | 104,866 (exact) |
| shuukura_wn_aligned | 66 | 66 (exact) |
| hime_training_all | 104,932 | 104,932 (exact) |

All counts match spec exactly.

### shuukura_wn_aligned quality_range note

`shuukura_wn_aligned` uses `instruction`/`input`/`output` format (no `score` field), so `quality_range` is `[]`. This is expected — the file is a literary aligned set without a numeric score. The `quality_field` is recorded as `"score"` in the registry (for forward-compatibility) but the range is empty because no values were found.

### Export smoke test

```
python scripts/hime_data.py export --min-score 0.70 --out /tmp/registry_export_070.jsonl
[OK] exported 709732 lines -> C:\Users\lfLaw\AppData\Local\Temp\registry_export_070.jsonl
```

Line count: **709,732** at `--min-score 0.70`.

- jparacrawl_500k: all 500,000 qualify (score range [0.7, 0.794])
- hime_training_filtered: 104,866 qualify
- shuukura_wn_aligned: 0 lines exported (no score field, filtered out)
- hime_training_all: 104,866 qualify

## Backend Router

Routes added:
- `GET /api/v1/data/registry` — returns list of all registry entries
- `GET /api/v1/data/registry/{id}` — returns one entry with up to 3 sample rows

`DATA_DIR` resolution: imported directly from `app.core.paths` which reads `HIME_DATA_DIR` env var at module load time. Router always reads from `DATA_DIR / "registry.jsonl"`.

Total routes after Phase 6: **68** (was 66 after Phase 4, +2 new registry routes).

## Test Results

- `test_data_registry.py` CLI tests: **4/4 PASS**
- `test_data_registry.py` router test: **1/1 PASS** (monkeypatches `DATA_DIR` on the router module directly)
- Total new tests: 5

## Full suite: 290 passed, 1 failed, 1 skipped

- Baseline: 285 passed, 1 failed, 1 skipped
- Phase 6 adds 5 new tests: 290 passed
- Pre-existing failure (`test_vault_organizer.py::test_cluster_similar_notes_no_model`) unchanged

## Files created

| File | Purpose |
|---|---|
| `scripts/hime_data.py` | CLI: register / list / export |
| `app/backend/app/routers/data_registry.py` | Read-only REST router |
| `app/backend/tests/test_data_registry.py` | 5 tests (4 CLI + 1 router) |
| `data/registry.jsonl` | Seeded registry with 4 training sources |

## Scope note

This phase builds the registry foundation only. Flywheel retraining, incremental adapter updates, and data versioning are separate post-remediation projects.
