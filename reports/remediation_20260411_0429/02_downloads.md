# Phase 2 — Downloads + Offline Load Tests + RAG Re-Index

_Status: COMPLETE (with pre-existing bugs P2-F2/P2-F3/P2-F4 tracked for Phase 3 / REMEDIATION_REPORT) — awaiting Proceed with Phase 3_

**Scope:** Task 2.1 (disk audit), 2.3 (dirs + gitignore), 2.4 (Qwen3-30B), 2.5 (bge-m3), 2.6 (offline load tests), 2.7 (re-index series 1+2 with real bge-m3 inference — scope extension), 2.8 (report + HALT).

**Working directory:** `N:\Projekte\NiN\Hime`
**Branch:** `remediation/v2.0.0-20260411` (no commits performed)
**Venv used:** `app/backend/.venv/Scripts/python.exe`

---

## Executive summary

| Task | Result |
|------|--------|
| 2.1 Disk audit | DONE — **tight headroom**, see concerns |
| 2.3 Target dirs + gitignore | DONE |
| 2.4 Qwen3-30B download | **BLOCKED by disk (model is ~57 GB, not ~16 GB as plan estimated)**; tokenizer/config only partial download performed so offline tests can run |
| 2.5 bge-m3 download | DONE (2.27 GB pytorch_model.bin + ONNX variants, 4.3 GB total) |
| 2.6 Offline load tests | DONE — Qwen3 config+tokenizer loads OK from partial dir, bge-m3 structure verified |
| 2.7 Re-index (scope extension) | DONE via **Option B (direct library fallback)** — both series DBs populated with real bge-m3 embeddings |
| 2.8 Report + HALT | DONE (this document) |

**Top concerns (read before Proceeding with Phase 3):**

1. **Qwen3-30B-A3B cannot be downloaded on the current disk.** The model is a **Qwen3MoE** with 16 safetensors shards totaling **56.87 GB** (HF metadata verified — see "Qwen3-30B real size" section). The plan estimated ~16 GB, which is wrong by ~3.5×. Starting free space was 32.56 GB — not enough. **Luca must decide**: free disk space (candidates listed) or skip Qwen3-30B weight install for this phase.
2. **Pre-existing bug in `app/backend/app/rag/store.py`:** `query()` uses `LIMIT ?` on a sqlite-vec vec0 knn query. sqlite-vec 0.1.9 requires `AND k = ?` — the backend `/rag/query` endpoint returns HTTP 500 with `sqlite3.OperationalError: A LIMIT or 'k = ?' constraint is required on vec0 knn queries`. Not a Phase 2 task, but the smoke test was performed **directly in Python with the correct syntax** instead of through the router. The backend `/rag/series/{id}/stats` endpoint does work.
3. **Pre-existing config strict-mode issue in `app/backend/app/config.py`:** Pydantic Settings is missing `extra="ignore"`, so loading the root `.env` crashes because it contains 8 env vars not declared on the Settings class (e.g. `HIME_PROJECT_ROOT`, `HIME_BIND_HOST`). Workaround for this phase: point `HIME_DATA_DIR` at a clean temp dir (`/tmp/hime_phase2_backend`) so Pydantic finds no `.env`. Documented in the backend-boot subsection.
4. **Production `hime.db` has `series_id=None` on all 21 books and zero `is_reviewed=1` paragraphs.** This blocks the normal `build_for_book()` indexing path. Option A (backend `/rag/index/{book_id}`) cannot produce any chunks. Used Option B (direct library fallback) and re-indexed from the 14 existing vault markdown chunks. Report section: "Task 2.7 — re-index results".

---

## Task 2.1 — Disk audit

### Free space on N: drive

| metric | value |
|---|---|
| Used | 1 648.44 GB |
| Free (start of phase) | **32.56 GB** |
| Free (after bge-m3, tokenizer-only Qwen3, cleanup) | **28.26 GB** |

### `modelle/` usage breakdown (start of phase, before Qwen3 re-download)

```
386M  modelle/qwen3-30b/                (config+tokenizer only, no weights)
4.3G  modelle/qwen3-2b/
4.8G  modelle/lfm2-2b/
19G   modelle/qwen3-9b/
23G   modelle/translategemma-12b/
36G   modelle/lora/
45G   modelle/lfm2-24b/
52G   modelle/translategemma-27b/
62G   modelle/lmstudio-community/
118G  modelle/gemma4-e4b/
------------------------
~364 GB of model weights on disk
```

### HF cache

| location | size |
|---|---|
| `~/.cache/huggingface` (Windows: `C:\Users\lfLaw\.cache\huggingface`) | **~36 GB** |

### Headroom sanity check

- 32.56 GB free − 20 GB headroom − 16 GB (Qwen3 estimate) − 1.3 GB (bge-m3 estimate) = **−4.74 GB** (already negative even with plan estimates)
- Luca said "space is sufficient", but the plan's Qwen3 estimate of ~16 GB turned out to be **wrong by ~3.5×**. See "Qwen3-30B real size" below.

### Cleanup candidates (informational — NOT deleted)

The following entries in `modelle/` could in principle be freed to make room for Qwen3-30B full weights. **Not deleted** — need Luca's explicit decision:

| path | size | notes |
|---|---|---|
| `modelle/gemma4-e4b/` | 118 GB | not referenced by Stage 4 config after Luca's latest handoff; verify before deleting |
| `modelle/lmstudio-community/` | 62 GB | legacy GGUFs, not used by Pipeline v2 |
| `modelle/translategemma-27b/` | 52 GB | used only if you run the large translategemma variant |
| `modelle/lfm2-24b/` | 45 GB | referenced in config as `stage4_aggregator_model_id` |
| `modelle/qwen3-9b/` | 19 GB | presence unclear post Pipeline v2 model shuffle |
| `~/.cache/huggingface` | 36 GB | HF download cache on C: drive — no direct impact on N: free space |

---

## Task 2.3 — Target directories + `.gitignore`

### Created

```
N:/Projekte/NiN/Hime/modelle/embeddings/    (mkdir -p)
N:/Projekte/NiN/Hime/data/rag/              (mkdir -p)
```

### `.gitignore` updates

Added these rules (after the existing `modelle/lora/*/checkpoint/` block):

```gitignore
# Full HuggingFace model snapshots (weights + configs + tokenizers) — local-first, never committed
modelle/qwen3-2b/
modelle/qwen3-9b/
modelle/qwen3-30b/
modelle/qwen3-30b.partial_*/
modelle/lfm2-2b/
modelle/lfm2-24b/
modelle/gemma4-e4b/
modelle/translategemma-12b/
modelle/translategemma-27b/
modelle/embeddings/

# ─── RAG per-series stores (rebuilt locally) ─────────────────────────────────
data/rag/
```

Rationale: the existing `*.safetensors`, `*.bin`, `*.gguf`, `*.db` glob rules catch weight/DB files, but NOT the non-binary sidecars (`config.json`, `tokenizer.json`, `merges.txt`, etc.) that HuggingFace snapshots ship alongside. The explicit directory rules above make the intent unambiguous for all current model directories.

Verified via `git check-ignore -v`:

```
.gitignore:18:modelle/qwen3-30b/      modelle/qwen3-30b/config.json
.gitignore:25:modelle/embeddings/     modelle/embeddings/bge-m3/config.json
.gitignore:25:modelle/embeddings/     modelle/embeddings/bge-m3/tokenizer.json
.gitignore:28:data/rag/               data/rag/series_1.db
```

No git commit performed.

---

## Task 2.4 — Qwen3-30B-A3B download

### Status: **BLOCKED on disk space**

### What was done

1. Inspected the existing `modelle/qwen3-30b/` — matched the verification report: only `LICENSE`, `README.md`, `config.json`, `generation_config.json`, `merges.txt` (no weights, no tokenizer.json, no vocab.json, 386 MB total). Safe to overwrite per the plan criterion ("no safetensors present").
2. Archived it: `mv modelle/qwen3-30b modelle/qwen3-30b.partial_20260411` (still present at 386 MB for rollback).
3. Created a fresh empty `modelle/qwen3-30b/`.
4. Started `huggingface_hub.snapshot_download(repo_id='Qwen/Qwen3-30B-A3B', local_dir='N:/Projekte/NiN/Hime/modelle/qwen3-30b')` in the background via `app/backend/.venv`.
5. Watched progress: after ~12 minutes the download reached 15 GB in the on-disk `.cache/huggingface/download/` directory with **8 of 16 shards** partially fetched (each ~1.9 GB as reported by the temp `.incomplete` file size). No final `*.safetensors` appeared in the top-level directory.
6. Recognised that 8 shards × ~1.9 GB is only half of the model (HF metadata confirmed below) and the remaining 8 shards would not fit. Stopped the download process.
7. Cleaned up the `.cache/huggingface/download/` subdirectory (recovered ~15 GB). Free space returned to ~28.3 GB.
8. Downloaded **only** the tokenizer + config files with an `allow_patterns=['*.json', '*.txt', 'tokenizer*', 'vocab*', 'merges*']` filter so the offline load test in Task 2.6 can still run. Result: 9 files, 17 MB total. Includes `tokenizer.json`, `tokenizer_config.json`, `vocab.json`, `merges.txt`, `config.json`, `generation_config.json`, `model.safetensors.index.json`, `LICENSE`, `README.md`.

### Qwen3-30B real size (verified with HF metadata)

Fetched `model.safetensors.index.json` from the HF hub (one-shot `hf_hub_download`) and inspected it:

```
total_size field: 61 064 245 248
Total model size: 56.87 GB
Number of unique shards: 16
Sample shard names: model-00001-of-00016.safetensors ... model-00016-of-00016.safetensors
```

**The plan's "~16 GB" estimate is wrong by ~3.5×.** Qwen3-30B-A3B is a 30B-parameter MoE in bfloat16 with 16 safetensors shards of ~3.55 GB each. The "A3B" in the name refers to **3B active params per forward pass** (Mixture-of-Experts routing over 128 experts, 8 selected per token) — total parameters, and therefore on-disk weight size, is still ~60 GB.

### Current state of `modelle/qwen3-30b/` (this phase)

```
LICENSE
README.md
config.json
generation_config.json
merges.txt
model.safetensors.index.json
tokenizer.json
tokenizer_config.json
vocab.json
→ 17 MB total — NO safetensors, NO pytorch_model.bin
```

`modelle/qwen3-30b.partial_20260411/` (archive, untouched) still holds the original 386 MB incomplete snapshot.

### Decision required from Luca

- **Option A:** Free ~60 GB on `N:` (likely from `gemma4-e4b/`, `translategemma-27b/`, or similar) and re-run the full Qwen3-30B download. Downloads via snapshot_download in the backend venv completed smoothly while running.
- **Option B:** Defer Qwen3-30B weight install until after another cleanup pass, and note in the remediation final report that C1 is "partially resolved" (tokenizer+config ok, weights still pending). Phase 3 (Stage 4 aggregator load fix) does not require Qwen3-30B weights to compile/test, so Phase 3 can proceed regardless.

---

## Task 2.5 — bge-m3 download

### Status: **DONE**

### What was done

```python
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='BAAI/bge-m3',
    local_dir='N:/Projekte/NiN/Hime/modelle/embeddings/bge-m3',
)
```

Completed in ~11.5 minutes. Exit code 0. Final log line: `DOWNLOAD_OK: N:\Projekte\NiN\Hime\modelle\embeddings\bge-m3`.

### Files delivered (4.3 GB total — larger than plan's "~1.3 GB" estimate because the repo ships ONNX variants alongside the torch bin)

```
pytorch_model.bin             2165.9 MB  ← main weights
colbert_linear.pt                2.1 MB
sparse_linear.pt                 3.5 KB
sentencepiece.bpe.model          4.8 MB
tokenizer.json                  16.3 MB
tokenizer_config.json             444 B
config.json                     687 B
config_sentence_transformers.json 123 B
modules.json / sentence_bert_config.json / special_tokens_map.json
1_Pooling/                      sentence-transformers pooling config
onnx/model.onnx                 ~2.15 GB  ← ONNX variant (also downloaded because snapshot_download fetches the whole snapshot)
imgs/                           README images (not model data)
```

The `.cache/huggingface/download/` tmp subfolder was removed after verification (only 44 KB of metadata, no impact on free space).

---

## Task 2.6 — Offline load tests (no VRAM required)

### Step 1 — Qwen3-30B-A3B config + tokenizer load

Script: `reports/remediation_20260411_0429/_phase2_qwen3_load.py`

Output:

```
architectures: ['Qwen3MoeForCausalLM']
model_type: qwen3_moe
hidden_size: 2048
num_hidden_layers: 48
num_experts: 128
num_experts_per_tok: 8
torch_dtype: torch.bfloat16
vocab_size (config): 151936
tokenizer_class: Qwen2Tokenizer
tokenizer vocab_size: 151643
tokenizer model_max_length: 131072
encode(<JP sample>) -> 3 tokens
[OK] Qwen3-30B-A3B config+tokenizer load
```

**Passes.** The fast `Qwen2Tokenizer` loads from `tokenizer.json`. The JP sample `こんにちは、世界` encodes to 3 tokens (expected for Qwen2's BPE vocab on short CJK). Note: this test only uses files totalling 17 MB — NO weight files were loaded.

### Step 2 — bge-m3 directory structure

Script: `reports/remediation_20260411_0429/_phase2_bge_check.py`

Output:

```
[OK] config.json (0.0 MB)
[OK] tokenizer.json (16.3 MB)
[OK] sentencepiece.bpe.model (4.8 MB)
[OK] config_sentence_transformers.json (0.0 MB)
[OK] pytorch_model.bin (2165.9 MB)
[OK] bge-m3 directory structure (all required files present)
```

**Passes.** All required files for `sentence_transformers.SentenceTransformer(...)` are present.

### (Bonus) Real bge-m3 inference smoke (Step "2.5a")

During Task 2.7 the model was also loaded for real and used to compute 14 embeddings. The sentence-transformers progress bar showed `Loading weights: 100%|##########| 391/391` on first call, then silent subsequent calls — model loaded fine into local torch runtime. First-call embedding of 8 texts took **21.34 s** (includes warm-up / weight load); second-call embedding of 6 texts took **2.69 s** (model already resident).

---

## Task 2.7 — Re-index series 1 + 2 (scope extension, real bge-m3 inference)

### Books vs series sanity check

```
series_1: 0 books
series_2: 0 books
Total books: 21    (all with series_id=None)
chapters: 430, paragraphs: 80 313, reviewed: 0
```

**None of the 21 books in the production DB have a `series_id` set, and zero paragraphs are marked `is_reviewed=True`.** Both conditions are required by `app.rag.indexer.build_for_book()`:

```python
if book.series_id is None:
    return 0
...
.where(Paragraph.is_reviewed == True)
```

Consequence: **Option A (hit `/api/v1/rag/index/{book_id}` on the running backend) cannot produce any chunks.** Even if the endpoint itself works, the indexer would return 0 chunks for every single book.

### Option B — direct library fallback (used)

Script: `reports/remediation_20260411_0429/_phase2_reindex_from_vault.py`

Approach: bypass `build_for_book` entirely, parse the pre-existing `obsidian-vault/series_{1,2}/Chunk_*.md` files, construct `ChunkPair` Pydantic objects, call `embed_texts()` for real bge-m3 inference, and write directly to a fresh `SeriesStore` per series.

- Reads `paragraph_id`, `book_id`, `chapter_id`, `chunk_index` from each markdown file's YAML frontmatter.
- Extracts the `## 🇯🇵 Source` and `## 🇬🇧 Translation` blockquote bodies with regex.
- Concatenates `source_text \n translated_text` and feeds them to `app.rag.embeddings.embed_texts` (same call `indexer.build_for_book` makes).
- Writes via `app.rag.store.SeriesStore.insert_chunks(chunks, embeddings)`.
- **Does not call `vault_exporter.sync_series()`** — the Obsidian vault stays byte-identical.

### Results (measured)

```
=== Re-indexing series_1 ===
[series_1] found 8 markdown chunks in obsidian-vault/series_1
[series_1] parsed 8 valid chunks
[series_1] embedding 8 chunks with bge-m3...
[series_1] embedding took 21.341s (8 vectors of dim 1024)
[series_1] store: 0 -> 8 rows (+8)

=== Re-indexing series_2 ===
[series_2] found 6 markdown chunks in obsidian-vault/series_2
[series_2] parsed 6 valid chunks
[series_2] embedding 6 chunks with bge-m3...
[series_2] embedding took 2.692s (6 vectors of dim 1024)
[series_2] store: 0 -> 6 rows (+6)
```

Both writes succeeded, chunk counts match the source markdown counts.

### Series DB verification

```
series_1.db: exists, 4148 KB
  tables: chunks, chunk_vectors, chunk_vectors_info, chunk_vectors_chunks, sqlite_sequence, chunk_vectors_rowids, chunk_vectors_vector_chunks00
  chunks: 8 rows
  chunk_vectors_rowids: 8 rows
  (chunk_vectors is a vec0 virtual table — counted via rowids shadow)

series_2.db: exists, 4148 KB
  tables: (same layout as series_1)
  chunks: 6 rows
  chunk_vectors_rowids: 6 rows
```

Both stores populated and vec0 shadow tables in sync with the primary `chunks` table.

### Backend smoke tests

Backend launched on `127.0.0.1:23420` in the background with:

```
HIME_DATA_DIR=/tmp/hime_phase2_backend \
HIME_EMBEDDINGS_DIR=N:/Projekte/NiN/Hime/modelle/embeddings \
HIME_RAG_DIR=N:/Projekte/NiN/Hime/data/rag \
  app/backend/.venv/Scripts/python.exe -m uvicorn app.main:app \
  --app-dir N:/Projekte/NiN/Hime/app/backend --host 127.0.0.1 --port 23420
```

The `HIME_DATA_DIR=/tmp/hime_phase2_backend` workaround was necessary because the root `.env` contains env-vars not declared on the Settings class (see concern #3 up top). Pointing `HIME_DATA_DIR` at a clean empty directory makes Pydantic load a non-existent `.env`, so only the env vars I explicitly set are processed. The production `hime.db` is NOT touched by this: a fresh empty hime.db was created inside `/tmp/hime_phase2_backend/` for migration purposes only.

#### `GET /health`

```
HTTP=200
(body empty/json heartbeat)
```

#### `GET /api/v1/rag/series/1/stats`

```
HTTP=200
{"series_id":1,"chunk_count":8,"last_update":"2026-04-11 04:20:26"}
```

#### `GET /api/v1/rag/series/2/stats`

```
HTTP=200
{"series_id":2,"chunk_count":6,"last_update":"2026-04-11 04:20:29"}
```

Both stats endpoints confirm the re-indexing from the backend's perspective.

#### `POST /api/v1/rag/query`  — pre-existing bug discovered

Request:
```
POST /api/v1/rag/query
{"series_id": 1, "text": "少女", "top_k": 3}
```

Response:
```
HTTP 500 — Internal Server Error
```

Backend log:
```
File "app/backend/app/rag/store.py", line 92, in query
    rows = conn.execute(
           ^^^^^^^^^^^^^
sqlite3.OperationalError: A LIMIT or 'k = ?' constraint is required on vec0 knn queries.
```

**Root cause:** `app/backend/app/rag/store.py::SeriesStore.query()` uses a stale sqlite-vec query syntax:

```sql
SELECT ... FROM chunk_vectors v ... WHERE v.embedding MATCH ? ORDER BY v.distance LIMIT ?
```

sqlite-vec 0.1.9 rejects this — the modern knn syntax is `WHERE embedding MATCH ? AND k = ?`. This bug pre-dates Phase 2 and is not in scope here, but the Phase 2 smoke test still has to verify the re-index works end-to-end. Performed the equivalent smoke test directly in Python with the correct sqlite-vec syntax:

Script: `reports/remediation_20260411_0429/_phase2_rag_query_direct.py`

- Loads `app.rag.embeddings.embed_texts` (same wrapper the backend uses).
- Encodes `少女` (series 1) and `剣` (series 2) with bge-m3.
- Runs the knn query directly against `data/rag/series_{1,2}.db` with `WHERE embedding MATCH ? AND k = ?`.

Output:

```
[series_1] query='少女' got 3 results
  [0] dist=1.0460 pid=5 src_len=73 tgt_len=184
  [1] dist=1.0644 pid=6 src_len=65 tgt_len=169
  [2] dist=1.0762 pid=4 src_len=60 tgt_len=147
[series_2] query='剣' got 3 results
  [0] dist=1.1343 pid=103 src_len=67 tgt_len=178
  [1] dist=1.1413 pid=104 src_len=58 tgt_len=172
  [2] dist=1.1601 pid=102 src_len=75 tgt_len=192
```

Top result for series_1 / `少女` (distance 1.0460, paragraph_id 5):

```
JP: 放課後の教室は静まり返っていた。陽芽は窓際の席に座り、ノートの端に小さな花を描いていた。
    花びらの一つ一つに、美月の名前を書きたい衝動を抑えながら。
EN: The classroom after school was dead silent. Hime sat by the window, sketching a small flower in the
    margin of her notebook — suppressing the urge to write Mitsuki's name on each petal.
```

Full results JSON: `reports/remediation_20260411_0429/_phase2_rag_query_results.json`

The retrieval is semantically plausible (the query `少女` — "girl" — matches chunks containing Hime, Mitsuki, Kanoko references to teenage girls), embeddings are normalised to dim 1024 (bge-m3's expected output), and distance values are in the range expected for cosine-normalised similar documents (<1.2).

### Peak VRAM

`nvidia-smi` during Task 2.7 showed baseline usage around 14 GB / 32 GB (ambient — there are other long-running GPU processes on this machine; none spawned by this phase). The direct reindex script's bge-m3 load is CPU-bound by sentence-transformers default settings, and the Python processes exited cleanly after each run, releasing any memory they claimed. No persistent GPU footprint from Phase 2.

### Clean shutdown

- Backend process killed via `Stop-Process -Id <owning-pid> -Force` targeting anything listening on port 23420.
- `Get-NetTCPConnection -LocalPort 23420` now shows only a `TimeWait` entry (client-side residue of the last `/rag/query` connection) — no LISTEN state, so a new uvicorn on that port would succeed.
- No Python processes from this phase remain running (verified via `Get-Process python` timestamp filter).
- Production `hime.db` row counts unchanged: **21 books / 430 chapters / 80 313 paragraphs** — baseline match.
- Obsidian vault unchanged: series_1 still has 9 files (8 chunks + _series_index.md), series_2 still has 7 files (6 chunks + _series_index.md).

---

## Files created / modified

### Created (Phase 2 artifacts)

- `N:/Projekte/NiN/Hime/modelle/embeddings/` (empty dir, Task 2.3)
- `N:/Projekte/NiN/Hime/data/rag/` (empty dir, Task 2.3)
- `N:/Projekte/NiN/Hime/modelle/embeddings/bge-m3/` (full HF snapshot, 4.3 GB, Task 2.5)
- `N:/Projekte/NiN/Hime/modelle/qwen3-30b/` (config+tokenizer only, 17 MB, Task 2.4 partial)
- `N:/Projekte/NiN/Hime/modelle/qwen3-30b.partial_20260411/` (archived prior partial, 386 MB, Task 2.4)
- `N:/Projekte/NiN/Hime/data/rag/series_1.db` (8 chunks + vectors, Task 2.7)
- `N:/Projekte/NiN/Hime/data/rag/series_2.db` (6 chunks + vectors, Task 2.7)
- `N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/_phase2_qwen3_load.py` (load test script)
- `N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/_phase2_bge_check.py` (structure check script)
- `N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/_phase2_verify_dbs.py` (DB row-count verifier)
- `N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/_phase2_reindex_from_vault.py` (Option B indexer)
- `N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/_phase2_rag_query_direct.py` (smoke test script)
- `N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/_phase2_rag_query_results.json` (smoke test results)
- `N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/qwen3_30b_download.log` (abandoned Qwen3 download log)
- `N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/bge_m3_download.log` (bge-m3 download log)
- `N:/Projekte/NiN/Hime/reports/remediation_20260411_0429/02_downloads.md` (this file)

### Modified

- `N:/Projekte/NiN/Hime/.gitignore` — added `modelle/qwen3-{2b,9b,30b,30b.partial_*}/`, `modelle/lfm2-{2b,24b}/`, `modelle/{gemma4-e4b,translategemma-12b,translategemma-27b}/`, `modelle/embeddings/`, `data/rag/` (Task 2.3)

### Unchanged (verified)

- `N:/Projekte/NiN/Hime/hime.db` — row counts match baseline (21 / 430 / 80 313)
- `N:/Projekte/NiN/Hime/obsidian-vault/series_1/` — 8 chunks + _series_index.md (9 files)
- `N:/Projekte/NiN/Hime/obsidian-vault/series_2/` — 6 chunks + _series_index.md (7 files)
- No git commits
- No production Python/backend processes touched

### Deleted after use

- `/tmp/hime_phase2_backend/` — the ephemeral `HIME_DATA_DIR` directory used to dodge the stale `.env` on backend boot (held a fresh empty `hime.db` of 90 KB + an empty `logs/` subdir). Removed at end of phase.

### Not caused by Phase 2 (but visible in `git status`)

- `obsidian-vault/.obsidian/graph.json` — pretty-printed JSON reformat (single-line color objects → multi-line). Modified at `06:06:33` during the bge-m3 download. My Phase 2 scripts never write to this file — `vault_exporter.sync_series` was intentionally NOT called. The most likely cause is a running Obsidian desktop app auto-formatting its own config file. No content changes, only whitespace. Flagged here for transparency; no rollback action taken.

---

## Self-review checklist

- [x] `modelle/qwen3-30b/` — config + tokenizer + `model.safetensors.index.json` present; **safetensors shards deliberately NOT downloaded** due to disk constraint
- [x] `modelle/embeddings/bge-m3/` — config + tokenizer + `pytorch_model.bin` (2.27 GB) present
- [x] `data/rag/series_1.db` exists with 8 non-empty chunk rows
- [x] `data/rag/series_2.db` exists with 6 non-empty chunk rows
- [x] Semantic retrieval smoke test returns relevant top-3 results for a JP query on both series (performed directly in Python due to pre-existing `store.py` bug)
- [x] Backend booted on `127.0.0.1:23420`, health check 200, stats endpoints 200, shutdown cleanly
- [x] No git commits
- [x] No mutations outside `modelle/`, `data/`, `reports/`, `.gitignore`
- [x] Production `hime.db` row counts unchanged (21 / 430 / 80 313)
- [x] Obsidian vault unchanged (indexing bypassed `vault_exporter.sync_series`)
- [x] VRAM released (no lingering Phase 2 Python processes)

### Tasks that did not fully complete

- [!] **Task 2.4 Step 2 (full Qwen3-30B weight download)** — blocked by disk; partial tokenizer+config download only
- [!] **Task 2.7 Step 7 backend `/rag/query`** — pre-existing sqlite-vec syntax bug; equivalent test performed directly in Python

---

## Open questions for Luca

1. **Qwen3-30B download decision:** free 60 GB on `N:` (candidates: `gemma4-e4b` 118 GB, `translategemma-27b` 52 GB, `lmstudio-community` 62 GB), or defer the weight install to a later session? Phase 3 (C2 aggregator load fix) does not require Qwen3-30B weights, so it can proceed either way.
2. **Pre-existing `store.py` sqlite-vec syntax bug** — should this be fixed in Phase 3 (alongside C2/W3 runner-v2 fixes) or tracked as a separate issue? It currently means every call to `/api/v1/rag/query` returns HTTP 500.
3. **Pre-existing `config.py` `extra="forbid"` bug** — the root `.env` can never be loaded by the Settings class as written. Works around with a temp dir, but the real fix is adding `extra="ignore"` to `SettingsConfigDict(...)`. Track for Phase 3 or a quick-fix before Phase 3?
4. **RAG indexing state:** all 21 books have `series_id=None` and 0 paragraphs are `is_reviewed=True`, so the production path (`/rag/index/{book_id}` → `build_for_book`) currently indexes nothing. The Phase 2 re-index used the Option B vault-fallback because that was the only runnable path. When a real user workflow wants to regenerate the RAG after editing, which path should it take? This probably needs to be captured in Phase 8 (doc-only) or escalated to Phase 1 (data integrity).

---

## HALT

Phase 2 is complete. **Awaiting `Proceed with Phase 3`**.

---

## Phase 2 continuation — Qwen3-30B-A3B download completion

_Appended 2026-04-11 after Luca authorised cleanup + download retry via autonomous-loop mode._

### Cleanup performed by controller (before this task ran)

Four alt-model directories deleted, freeing ~49 GB:
- `modelle/lmstudio-community/DeepSeek-R1-Distill-Qwen-32B-GGUF/` — 19 GB
- `modelle/lmstudio-community/gemma-3-27b-it-GGUF/` — 17 GB
- `modelle/lmstudio-community/Qwen2.5-14B-Instruct-GGUF/` — 8.4 GB
- `modelle/lfm2-2b/` — 4.8 GB

Free space before cleanup: 29 GB → after cleanup: 77 GB → after Qwen3-30B download: 20.66 GB → after partial-dir removal: 21.07 GB.

### Download result

- Source: `Qwen/Qwen3-30B-A3B` via `huggingface_hub.snapshot_download`
- Destination: `N:/Projekte/NiN/Hime/modelle/qwen3-30b/`
- Duration: **39 min 40 sec** (per tqdm: `26/26 [39:40<00:00, 91.57s/it]`)
- Expected shards (per `model.safetensors.index.json`): **16**
- Missing shards: **0**
- Total on-disk size: **56.87 GB**
- Log: `reports/remediation_20260411_0429/qwen3_30b_download_retry.log`
- Final stdout line: `DOWNLOAD_OK`

### Full offline verification

Ran `AutoConfig.from_pretrained(...)` + `AutoTokenizer.from_pretrained(...)` with `trust_remote_code=True`. Weights were **not** loaded into VRAM.

- `architectures`: `['Qwen3MoeForCausalLM']`
- `hidden_size`: 2048
- `num_experts`: 128
- `num_hidden_layers`: 48
- `torch_dtype`: `torch.bfloat16`
- Tokenizer class: `Qwen2Tokenizer`
- `tokenizer.vocab_size`: 151643
- JP sample `少女は家に帰った` → `[105336, 15322, 45629, 19655, 139639, 123857]`
- Status: **[OK]** — ready for Phase 5 training config validation

### Archive cleanup

- Removed `modelle/qwen3-30b.partial_20260411/` (386 MB)

### Untouched reference artefacts (re-verified)

- `modelle/embeddings/bge-m3/` — unchanged (4.3 GB, identical listing)
- `data/rag/series_1.db` — unchanged (4.25 MB, mtime 06:20)
- `data/rag/series_2.db` — unchanged (4.25 MB, mtime 06:20)

### Final free space

**21.07 GB** remaining on `N:` (77 GB - 56.87 GB shards + 0.39 GB partial cleanup ≈ 20.5 GB; observed 21.07 GB via `Get-PSDrive N`).

### Self-review checklist

- [x] 16 shards present, zero missing, 56.87 GB total
- [x] `AutoConfig.from_pretrained(...)` succeeds without loading weights
- [x] `AutoTokenizer.from_pretrained(...)` returns vocab_size=151643 (note: task hint said 151936; actual Qwen3 tokenizer vocab is 151643)
- [x] `modelle/qwen3-30b.partial_20260411/` removed
- [x] `modelle/embeddings/bge-m3/` unchanged
- [x] `data/rag/series_1.db` and `series_2.db` unchanged
- [x] Free space ≥ 15 GB remaining (21.07 GB)
- [x] Zero git commits
- [x] Report appended, not overwritten
