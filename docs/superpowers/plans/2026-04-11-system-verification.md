# Hime Full System Verification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a structured diagnostic report on the entire Hime system — models, training, database, RAG, backend, frontend — without modifying anything. Read-only inspection only.

**Architecture:** 9 sequential phases, each producing a Markdown report file. After each phase, halt and wait for user confirmation (`Proceed with Phase N`). All output goes to `N:\Projekte\NiN\Hime\reports\verification_YYYYMMDD_HHMM\`. The final phase consolidates everything into `FINAL_REPORT.md`.

**Tech Stack:** Bash commands, Python one-liners (conda run -n hime), sqlite3, git, nvidia-smi, ollama CLI. No pip install, no git commit, no downloads, no training runs.

**Language:** All report content in German.

---

## CRITICAL EXECUTION GUARDS

1. **NO WRITES** outside `N:\Projekte\NiN\Hime\reports\verification_YYYYMMDD_HHMM\`
2. **NEVER** run: `pip install`, `uv add`, `git commit`, `git push`, `huggingface-cli download`, `ollama pull`, `ollama run`, training scripts without `--help`/`--dry-run`
3. **NEVER** start a server (`uvicorn`, `npm run dev`, `cargo tauri dev`)
4. **HALT** after each phase — wait for `Proceed with Phase N`
5. If >3 unexpected errors in a phase: **STOP**, document state, ask user
6. Write results **incrementally** to report files so partial progress survives interruptions

---

## Key Paths Reference

| What | Path |
|---|---|
| Project root | `N:\Projekte\NiN\Hime` |
| Backend | `N:\Projekte\NiN\Hime\app\backend` |
| Frontend | `N:\Projekte\NiN\Hime\app\frontend` |
| Scripts | `N:\Projekte\NiN\Hime\scripts` |
| Training data | `N:\Projekte\NiN\Hime\data\training` |
| Models | `N:\Projekte\NiN\Hime\modelle` |
| LoRA adapters | `N:\Projekte\NiN\Hime\modelle\lora` |
| Main DB | `N:\Projekte\NiN\Hime\hime.db` |
| Backend DB | `N:\Projekte\NiN\Hime\app\backend\hime.db` |
| VERSION file | `N:\Projekte\NiN\Hime\app\VERSION` |
| Backend main | `N:\Projekte\NiN\Hime\app\backend\app\main.py` |
| Routers | `N:\Projekte\NiN\Hime\app\backend\app\routers\` |
| Services | `N:\Projekte\NiN\Hime\app\backend\app\services\` |
| Pipeline | `N:\Projekte\NiN\Hime\app\backend\app\pipeline\` |
| RAG | `N:\Projekte\NiN\Hime\app\backend\app\rag\` |
| Tests | `N:\Projekte\NiN\Hime\app\backend\tests\` |
| Conda env | `hime` |
| Tauri conf | `N:\Projekte\NiN\Hime\app\frontend\src-tauri\tauri.conf.json` |

---

### Task -1: Offene Fragen an Luca (vor Phase 0)

Bevor Phase 0 startet, diese Fragen stellen — falls keine Antwort kommt, Defaults verwenden und Annahmen transparent im Report dokumentieren:

- [ ] **Step -1.1: Fragen stellen**

Dem User folgende Fragen ausgeben:

1. Gibt es Pfade die von obiger Struktur abweichen? (z.B. Daten auf anderem Laufwerk, AppData, etc.)
2. Soll der HuggingFace-Cache (`~/.cache/huggingface/`) mit inspiziert werden oder nur `N:\Projekte\NiN\Hime\modelle\`?
3. Darf `ollama list` und `nvidia-smi` ausgeführt werden? (Read-Only, sollte unproblematisch sein — nur zur Bestätigung.)
4. Gibt es ein bekanntes bestehendes `pipeline.py`, oder soll danach gesucht werden?

**Defaults (falls keine Antwort):**
- Nur `N:\Projekte\NiN\Hime` und Unterpfade
- HF-Cache wird mit inspiziert
- `ollama list` und `nvidia-smi` erlaubt
- Pipeline-Dateien werden per Suche ermittelt (bereits bekannt: `app/backend/app/pipeline/runner.py` und `runner_v2.py`)

Auf Antwort warten, dann mit Phase 0 fortfahren.

---

### Task 0: Setup & Repo-Inventar (Phase 0)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/00_inventory.md`

- [ ] **Step 0.1: Create report directory**

Set timestamp once (format: `YYYYMMDD_HHMM` from current time) and create the report directory:

```bash
TIMESTAMP=$(date +%Y%m%d_%H%M)
mkdir -p "N:/Projekte/NiN/Hime/reports/verification_${TIMESTAMP}"
echo "$TIMESTAMP" > "N:/Projekte/NiN/Hime/reports/verification_${TIMESTAMP}/.timestamp"
```

Store the `TIMESTAMP` value — reuse it in all subsequent tasks.

- [ ] **Step 0.2: Generate directory tree**

```bash
# Tree depth 3, excluding noise dirs
cd "N:/Projekte/NiN/Hime"
find . -maxdepth 3 -type d \
  ! -path './.git/*' \
  ! -path '*/node_modules/*' \
  ! -path '*/__pycache__/*' \
  ! -path '*/target/*' \
  ! -path '*/.mypy_cache/*' \
  ! -path '*/.pytest_cache/*' \
  | sort
```

Write the output as a code block into `00_inventory.md` under heading `## Verzeichnis-Tree (Tiefe 3)`.

- [ ] **Step 0.3: Git status snapshot**

```bash
cd "N:/Projekte/NiN/Hime"
echo "Branch: $(git branch --show-current)"
echo "Last commit: $(git log -1 --oneline)"
echo "Remote: $(git remote -v | head -2)"
echo ""
echo "=== Uncommitted Changes ==="
git status --short
```

Write output into `00_inventory.md` under `## Git-Status`. Do NOT commit anything.

- [ ] **Step 0.4: Read VERSION and key files**

Read these files and note their existence, size, and first few lines:

| File | Path |
|---|---|
| VERSION | `N:\Projekte\NiN\Hime\app\VERSION` |
| CLAUDE.md | `N:\Projekte\NiN\Hime\app\CLAUDE.md` |
| README.md | `N:\Projekte\NiN\Hime\README.md` |

For each: Read the file. Note: exists? size? last modified (via `git log -1 -- <path>` or `ls -la`)?

Write into `00_inventory.md` under `## Schlüsseldateien`.

- [ ] **Step 0.5: Check pipeline_v2 documentation**

Search for pipeline v2 documentation:

```bash
find "N:/Projekte/NiN/Hime" -maxdepth 3 -name "*pipeline*v2*" -o -name "*pipeline_v2*" 2>/dev/null | grep -v node_modules | grep -v __pycache__ | grep -v .git
```

Also check: `docs/`, `prompts/`, root level for any pipeline design docs.

Compare found docs against the Soll-Zustand table from the spec (Stages Pre-Processing through Post-Processing). Write a bullet-point comparison into `00_inventory.md` under `## Pipeline v2 — Soll vs. Doku`.

- [ ] **Step 0.6: Write 00_inventory.md**

Compile all findings from steps 0.2–0.5 into the report file. Format:

```markdown
# Phase 0 — Repo-Inventar

**Zeitstempel:** YYYYMMDD_HHMM
**Datum:** 2026-04-11

## Verzeichnis-Tree (Tiefe 3)
[tree output]

## Git-Status
[git output]

## Schlüsseldateien
| Datei | Existiert | Größe | Letztes Update |
|---|---|---|---|
| VERSION | ... | ... | ... |
| CLAUDE.md | ... | ... | ... |
| README.md | ... | ... | ... |

## Pipeline v2 — Soll vs. Doku
[comparison]
```

**HALT — Ausgabe: "Phase 0 abgeschlossen. `00_inventory.md` geschrieben. Warte auf `Proceed with Phase 1`."**

---

### Task 1: Environment & Dependencies (Phase 1)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/01_environment.md`

- [ ] **Step 1.1: Check conda env `hime`**

```bash
conda env list 2>&1 | grep hime
```

If `hime` exists, proceed. If not, note as CRITICAL finding and skip conda-dependent steps.

- [ ] **Step 1.2: Python version and CUDA**

```bash
conda run -n hime python --version
conda run -n hime python -c "import torch; print(f'torch={torch.__version__}, cuda_available={torch.cuda.is_available()}, cuda_version={torch.version.cuda}')"
conda run -n hime python -c "import torch; print(f'GPU={torch.cuda.get_device_name(0)}, VRAM={torch.cuda.get_device_properties(0).total_mem / 1e9:.1f} GB')" 2>&1
```

- [ ] **Step 1.3: Critical packages**

For each package, run:

```bash
conda run -n hime python -c "import <pkg>; print(f'<pkg>={<pkg>.__version__}')" 2>&1
```

Packages to check (one command each, log result or import error):
- `unsloth`
- `transformers`
- `trl`
- `accelerate`
- `bitsandbytes`
- `peft`
- `datasets`
- `flash_attn` (may fail — note as optional)
- `pynvml`
- `fugashi` (MeCab)
- `ebooklib`
- `fastapi`
- `uvicorn`
- `pydantic`
- `sentence_transformers`

For `sqlite_vec`:
```bash
conda run -n hime python -c "import sqlite_vec; print(f'sqlite_vec OK')" 2>&1
```

Collect all results into a table: Package | Version | Status (OK / FEHLT / ERROR).

- [ ] **Step 1.4: Backend uv-environment**

```bash
# Check pyproject.toml
cat "N:/Projekte/NiN/Hime/app/backend/pyproject.toml" | head -50
# Check lock file
ls -la "N:/Projekte/NiN/Hime/app/backend/"*.lock 2>/dev/null
# List installed packages (read-only)
cd "N:/Projekte/NiN/Hime/app/backend" && uv pip list 2>&1 | head -60
```

Note any discrepancies between pyproject.toml deps and installed packages.

- [ ] **Step 1.5: Frontend Node-environment**

Read `N:\Projekte\NiN\Hime\app\frontend\package.json` — extract `dependencies` and `devDependencies`.

```bash
node --version
npm --version 2>/dev/null || pnpm --version 2>/dev/null || bun --version 2>/dev/null
```

Check for lockfile:
```bash
ls -la "N:/Projekte/NiN/Hime/app/frontend/package-lock.json" "N:/Projekte/NiN/Hime/app/frontend/pnpm-lock.yaml" "N:/Projekte/NiN/Hime/app/frontend/bun.lockb" 2>/dev/null
```

Check Tauri CLI:
```bash
npx tauri --version 2>/dev/null || cargo tauri --version 2>/dev/null
```

- [ ] **Step 1.6: GPU health check**

```bash
nvidia-smi
```

Capture full output: driver version, CUDA version, GPU name, VRAM total/used/free, running processes.

- [ ] **Step 1.7: Write 01_environment.md**

Compile all findings into:

```markdown
# Phase 1 — Environment & Dependencies

## Conda-Env `hime`
[exists/missing, Python version]

## CUDA & GPU
| Property | Value |
|---|---|
| GPU | ... |
| VRAM | ... |
| CUDA | ... |
| Treiber | ... |

## Python-Packages
| Package | Version | Status |
|---|---|---|
| unsloth | ... | OK / FEHLT |
| transformers | ... | ... |
[etc.]

## Backend uv-Environment
[pyproject.toml deps vs installed]

## Frontend Node-Environment
[node/npm versions, lockfile, Tauri CLI]

## nvidia-smi Output
[full output in code block]

## Probleme
[list any issues found]
```

**HALT — Ausgabe: "Phase 1 abgeschlossen. `01_environment.md` geschrieben. Warte auf `Proceed with Phase 2`."**

---

### Task 2: Modell-Inventar (Phase 2)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/02_models.md`

- [ ] **Step 2.1: LoRA adapters inventory**

List all directories under `N:\Projekte\NiN\Hime\modelle\lora\`:

```bash
ls -la "N:/Projekte/NiN/Hime/modelle/lora/"
```

For each adapter directory found, check:
```bash
# For each adapter dir:
ls -la "N:/Projekte/NiN/Hime/modelle/lora/<model_name>/"
# Check for required files
ls -la "N:/Projekte/NiN/Hime/modelle/lora/<model_name>/adapter_config.json" 2>/dev/null
ls -la "N:/Projekte/NiN/Hime/modelle/lora/<model_name>/adapter_model.safetensors" 2>/dev/null
```

For Qwen2.5-32B specifically, look for checkpoints:
```bash
ls -d "N:/Projekte/NiN/Hime/modelle/lora/Qwen2.5-32B-Instruct/"checkpoint-* 2>/dev/null
```

Read `trainer_state.json` from the latest checkpoint:
```bash
# Find latest checkpoint's trainer_state.json
cat "N:/Projekte/NiN/Hime/modelle/lora/Qwen2.5-32B-Instruct/<latest-checkpoint>/trainer_state.json" | python -c "import sys,json; d=json.load(sys.stdin); print(f'best_metric={d.get(\"best_metric\")}, best_checkpoint={d.get(\"best_model_checkpoint\")}, epoch={d.get(\"epoch\")}, global_step={d.get(\"global_step\")}')" 2>&1
```

- [ ] **Step 2.2: Base models inventory**

For each expected model, check directory existence and key files:

| Model | Expected Path | Check For |
|---|---|---|
| Qwen2.5-32B GGUF | `modelle/lmstudio-community/Qwen2.5-32B-Instruct-GGUF/` | `.gguf` files |
| TranslateGemma-12B | `modelle/translategemma-12b/` or `modelle/google/translategemma-12b-it/` | `config.json` + `.safetensors` shards |
| TranslateGemma-27B | `modelle/translategemma-27b/` or `modelle/google/translategemma-27b-it/` | `config.json` + `.safetensors` shards |
| Qwen3.5-9B | `modelle/qwen3-9b/` or `modelle/unsloth/Qwen3.5-9B/` | model files |
| Qwen3.5-35B-A3B | `modelle/qwen3-30b/` or `modelle/unsloth/Qwen3.5-35B-A3B/` | model files |
| Gemma4 E4B | `modelle/gemma4-e4b/` or `modelle/unsloth/gemma-4-E4B-it-GGUF/` | `.gguf` files |
| LFM2-2B | `modelle/lfm2-2b/` or `modelle/LiquidAI/LFM2-2B/` | model files |
| LFM2-24B | `modelle/lfm2-24b/` or `modelle/LiquidAI/LFM2-24B/` | model files |

For each:
```bash
ls -la "N:/Projekte/NiN/Hime/modelle/<path>/" 2>/dev/null
du -sh "N:/Projekte/NiN/Hime/modelle/<path>/" 2>/dev/null
```

- [ ] **Step 2.3: Ollama models**

```bash
ollama list 2>&1
```

Cross-reference with expected models.

- [ ] **Step 2.4: Legacy models (cleanup candidates)**

Check for old v1 models:
```bash
ls -d "N:/Projekte/NiN/Hime/modelle/"*DeepSeek* "N:/Projekte/NiN/Hime/modelle/"*gemma-3-27b* "N:/Projekte/NiN/Hime/modelle/"*Qwen2.5-14B* "N:/Projekte/NiN/Hime/modelle/"*Qwen2.5-72B* 2>/dev/null
```

For each found: note size with `du -sh`.

- [ ] **Step 2.5: HuggingFace cache**

```bash
du -sh ~/.cache/huggingface/hub/ 2>/dev/null
ls ~/.cache/huggingface/hub/ 2>/dev/null | head -30
```

Identify duplicates between HF cache and `modelle/`.

- [ ] **Step 2.6: Write 02_models.md**

```markdown
# Phase 2 — Modell-Inventar

## LoRA-Adapter
| Adapter | Pfad | adapter_config.json | adapter_model.safetensors | Checkpoints | Größe |
|---|---|---|---|---|---|
| Qwen2.5-32B | ... | OK/FEHLT | OK/FEHLT | [list] | ... |
[etc.]

### Qwen2.5-32B Checkpoint-Details
- Best metric: ...
- Best checkpoint: ...
- Epoch: ...
- Global step: ...

## Basismodelle — Soll vs. Ist
| Modell | Erwartetes Format | Pfad | Status | Größe |
|---|---|---|---|---|
| Qwen2.5-32B-Instruct | GGUF Q4_K_M | ... | OK/FEHLT/UNVOLLSTÄNDIG | ... |
[etc.]

## Ollama-Registrierung
| Modell | Registriert | Größe |
|---|---|---|
[from ollama list]

## Alt-Modelle (Aufräum-Kandidaten)
| Modell | Pfad | Größe | Empfehlung |
|---|---|---|---|
[list with sizes]

## HuggingFace-Cache
- Gesamtgröße: ...
- Duplikate mit modelle/: [list]

## Fehlende Modelle
[list with exact HF-IDs for download]
```

**HALT — Ausgabe: "Phase 2 abgeschlossen. `02_models.md` geschrieben. Warte auf `Proceed with Phase 3`."**

---

### Task 3: Trainings-Infrastruktur (Phase 3)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/03_training.md`

- [ ] **Step 3.1: Training scripts inventory**

```bash
ls -la "N:/Projekte/NiN/Hime/scripts/train_generic.py" 2>/dev/null
ls -la "N:/Projekte/NiN/Hime/scripts/train_hime.py" 2>/dev/null
wc -l "N:/Projekte/NiN/Hime/scripts/train_generic.py" 2>/dev/null
```

Run help to document CLI interface:
```bash
conda run -n hime python "N:/Projekte/NiN/Hime/scripts/train_generic.py" --help 2>&1
```

Extract supported `--model` values from source code:
```bash
grep -n "model.*choices\|add_argument.*model\|MODEL_CONFIGS\|SUPPORTED_MODELS" "N:/Projekte/NiN/Hime/scripts/train_generic.py"
```

- [ ] **Step 3.2: Training data verification**

For each expected file:

| File | Expected Path | Expected Lines |
|---|---|---|
| jparacrawl_500k.jsonl | `data/training/jparacrawl_500k.jsonl` or `data/jparacrawl_500k.jsonl` | raw data |
| hime_training_filtered.jsonl | `data/training/hime_training_filtered.jsonl` | 104,866 |
| shuukura_wn_aligned.jsonl | `data/training/shuukura_wn_aligned.jsonl` | 66 |
| hime_training_all.jsonl | `data/training/hime_training_all.jsonl` | 104,932 |

For each found file:
```bash
wc -l "<path>"
ls -la "<path>"
# Validate first 3 lines as JSON
head -3 "<path>" | conda run -n hime python -c "import sys,json; [json.loads(l) for l in sys.stdin]; print('JSON valid')" 2>&1
# Show field names from first line
head -1 "<path>" | conda run -n hime python -c "import sys,json; print(list(json.loads(sys.stdin.readline()).keys()))" 2>&1
```

- [ ] **Step 3.3: Curriculum learning reserve**

Check for data with scores between 0.62 and 0.7:
```bash
# Check if train_generic.py or curriculum.py references score thresholds
grep -n "0\.62\|0\.7\|score.*threshold\|curriculum" "N:/Projekte/NiN/Hime/scripts/train_generic.py" "N:/Projekte/NiN/Hime/app/backend/app/training/curriculum.py" 2>/dev/null
```

If no curriculum fallback data source found, note as open item.

- [ ] **Step 3.4: Training logs**

```bash
ls -la "N:/Projekte/NiN/Hime/logs/training/"*.log 2>/dev/null
# If logs exist, show tail of most recent
ls -t "N:/Projekte/NiN/Hime/logs/training/"*.log 2>/dev/null | head -1 | xargs tail -30 2>/dev/null
```

Cross-reference last training run's global_step with checkpoint directories from Phase 2.

- [ ] **Step 3.5: Dry-run check**

```bash
# Check if --dry-run flag exists
conda run -n hime python "N:/Projekte/NiN/Hime/scripts/train_generic.py" --help 2>&1 | grep -i "dry"
```

If no `--dry-run` flag: note as open item ("Kein Dry-Run-Flag in train_generic.py").

**DO NOT** run any actual training, not even `--max-steps 1`.

- [ ] **Step 3.6: Write 03_training.md**

```markdown
# Phase 3 — Trainings-Infrastruktur

## Skripte
| Skript | Existiert | Zeilen | Letztes Update |
|---|---|---|---|
| train_generic.py | ... | ... | ... |
| train_hime.py | ... | ... | ... |

### train_generic.py CLI-Interface
[--help output]

### Unterstützte Modelle
[extracted model values]

## Trainingsdaten
| Datei | Existiert | Zeilen (Soll) | Zeilen (Ist) | JSON-Schema | Größe |
|---|---|---|---|---|---|
| hime_training_all.jsonl | ... | 104.932 | ... | ... | ... |
[etc.]

## Curriculum-Learning-Reserve
[status: vorhanden / fehlt / offen]

## Trainings-Logs
[latest log summary, last global_step]

## Dry-Run Verfügbarkeit
[--dry-run flag: vorhanden / fehlt]

## Offene Punkte
[list]
```

**HALT — Ausgabe: "Phase 3 abgeschlossen. `03_training.md` geschrieben. Warte auf `Proceed with Phase 4`."**

---

### Task 4: Datenbank (Phase 4)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/04_database.md`

- [ ] **Step 4.1: Find all database files**

```bash
find "N:/Projekte/NiN/Hime" -maxdepth 3 -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" 2>/dev/null | grep -v node_modules | grep -v .git | grep -v __pycache__
```

For each found file:
```bash
ls -la "<db_path>"
```

- [ ] **Step 4.2: Integrity and journal mode**

For each database file:
```bash
sqlite3 "<db_path>" "PRAGMA integrity_check;"
sqlite3 "<db_path>" "PRAGMA journal_mode;"
```

- [ ] **Step 4.3: Tables and row counts**

```bash
sqlite3 "<db_path>" ".tables"
# For each table:
sqlite3 "<db_path>" "SELECT name, (SELECT count(*) FROM [name]) FROM sqlite_master WHERE type='table';" 2>/dev/null
```

If the above doesn't work, get table list first, then count each individually:
```bash
sqlite3 "<db_path>" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
# Then for each table:
sqlite3 "<db_path>" "SELECT count(*) FROM <table_name>;"
```

- [ ] **Step 4.4: Schema dump**

```bash
sqlite3 "<db_path>" ".schema"
```

- [ ] **Step 4.5: Check indexes and foreign keys**

```bash
sqlite3 "<db_path>" "SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name;"
sqlite3 "<db_path>" "PRAGMA foreign_keys;"
sqlite3 "<db_path>" "PRAGMA foreign_key_list(<table>);" # for each table with FKs
```

- [ ] **Step 4.6: Migrations system**

Check what migration system is used. The backend uses SQLAlchemy with inline migrations in `database.py`:

```bash
grep -n "migrate\|migration\|alembic\|yoyo\|CREATE TABLE\|ALTER TABLE" "N:/Projekte/NiN/Hime/app/backend/app/database.py" | head -30
```

Also check for Alembic directory:
```bash
ls -la "N:/Projekte/NiN/Hime/app/backend/alembic/" 2>/dev/null
ls -la "N:/Projekte/NiN/Hime/app/backend/migrations/" 2>/dev/null
```

Compare expected tables (from `app/backend/app/models.py`) with actual tables.

- [ ] **Step 4.7: Cross-reference ORM models with DB**

Read `N:\Projekte\NiN\Hime\app\backend\app\models.py` and extract all model class names and their `__tablename__`. Compare with actual tables found in step 4.3.

- [ ] **Step 4.8: Write 04_database.md**

```markdown
# Phase 4 — Datenbank

## Datenbank-Dateien
| Pfad | Größe | Integrität | Journal Mode |
|---|---|---|---|
| hime.db | ... | ok/FEHLER | ... |
[etc.]

## Tabellen & Zeilenzahlen
| Tabelle | Zeilen | In ORM | Kommentar |
|---|---|---|---|
| books | ... | Ja | ... |
[etc.]

## Schema
[full schema dump in code block]

## Indexe
[index list]

## Foreign Keys
[status: aktiviert/deaktiviert]

## Migrations-System
[description: inline/Alembic/custom]
[history vs DB state comparison]

## ORM-Abgleich
| ORM-Model | __tablename__ | In DB | Diskrepanz |
|---|---|---|---|
[comparison]

## Probleme
[list]
```

**HALT — Ausgabe: "Phase 4 abgeschlossen. `04_database.md` geschrieben. Warte auf `Proceed with Phase 5`."**

---

### Task 5: RAG-System (Phase 5)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/05_rag.md`

- [ ] **Step 5.1: Check RAG module existence**

```bash
ls -la "N:/Projekte/NiN/Hime/app/backend/app/rag/" 2>/dev/null
```

The RAG module exists at `app/backend/app/rag/` with these files: `chunker.py`, `embeddings.py`, `indexer.py`, `retriever.py`, `store.py`, `vault_exporter.py`. List each file with line count:

```bash
wc -l "N:/Projekte/NiN/Hime/app/backend/app/rag/"*.py
```

- [ ] **Step 5.2: Inspect RAG components**

For each file in the RAG module, extract public classes and functions:

```bash
grep -n "^class \|^def \|^async def " "N:/Projekte/NiN/Hime/app/backend/app/rag/"*.py
```

Check imports for external dependencies:

```bash
grep "^import \|^from " "N:/Projekte/NiN/Hime/app/backend/app/rag/"*.py | sort -u
```

- [ ] **Step 5.3: sqlite_vec availability**

```bash
conda run -n hime python -c "import sqlite_vec; print('sqlite_vec: OK')" 2>&1
```

- [ ] **Step 5.4: bge-m3 embedding model**

```bash
# Check in modelle/
find "N:/Projekte/NiN/Hime/modelle" -maxdepth 3 -name "*bge*" -o -name "*BGE*" 2>/dev/null
# Check in HF cache
find ~/.cache/huggingface/hub -maxdepth 2 -name "*bge*" 2>/dev/null
```

- [ ] **Step 5.5: JMdict and MeCab dictionary**

```bash
# JMdict dump
find "N:/Projekte/NiN/Hime" -maxdepth 3 -name "*jmdict*" -o -name "*JMdict*" 2>/dev/null | grep -v node_modules | grep -v .git
# MeCab dictionary
conda run -n hime python -c "import unidic; print(unidic.DICDIR)" 2>&1
```

- [ ] **Step 5.6: RAG router**

```bash
grep -n "rag\|RAG" "N:/Projekte/NiN/Hime/app/backend/app/routers/rag.py" | head -20
# Check endpoints
grep -n "@router\.\|prefix\|tags" "N:/Projekte/NiN/Hime/app/backend/app/routers/rag.py" | head -20
```

- [ ] **Step 5.7: Frontend RAG calls**

```bash
grep -rn "rag\|/rag" "N:/Projekte/NiN/Hime/app/frontend/src/" --include="*.ts" --include="*.tsx" 2>/dev/null
```

- [ ] **Step 5.8: Write 05_rag.md**

```markdown
# Phase 5 — RAG-System

## Status: implementiert / teilweise / fehlt

## Modul-Übersicht
| Datei | Zeilen | Klassen/Funktionen |
|---|---|---|
| chunker.py | ... | ... |
[etc.]

## Abhängigkeiten
| Dependency | Import | Verfügbar |
|---|---|---|
| sqlite_vec | ... | OK/FEHLT |
| sentence_transformers | ... | OK/FEHLT |
| bge-m3 Modell | ... | OK/FEHLT |

## JMdict / MeCab
[status]

## RAG-Router
| Endpoint | Methode | Implementiert |
|---|---|---|
[list]

## Frontend-Integration
[grep results: which frontend files call /rag endpoints]

## Was zur vollständigen Implementierung fehlt
[if applicable: missing files, dependencies, estimated LOC]
```

**HALT — Ausgabe: "Phase 5 abgeschlossen. `05_rag.md` geschrieben. Warte auf `Proceed with Phase 6`."**

---

### Task 6: Backend-Code-Integration (Phase 6)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/06_backend.md`

- [ ] **Step 6.1: Entry point inspection**

Read `N:\Projekte\NiN\Hime\app\backend\app\main.py` and check:
- FastAPI app instance created?
- All routers registered?
- Binding address (should be `127.0.0.1` only)
- Port in range `18420–18430`?
- CORS config: which origins allowed?

Read `N:\Projekte\NiN\Hime\app\backend\run.py` for the actual server start configuration.

- [ ] **Step 6.2: Router inventory**

For each file in `N:\Projekte\NiN\Hime\app\backend\app\routers\`:

```bash
for f in "N:/Projekte/NiN/Hime/app/backend/app/routers/"*.py; do
  echo "=== $(basename $f) ==="
  grep -n "prefix\|@router\.\|tags\|APIRouter" "$f" | head -20
done
```

Build a table: Router file | Prefix | Endpoints (Method + Path) | Auth | Rate-Limit.

Expected routers from spec: `translate.py`, `compare.py`, `models.py`, `training.py`, `history.py`, `books.py`/`epub.py`, `rag.py`. Note which exist and which are missing/renamed.

- [ ] **Step 6.3: Services inventory**

```bash
for f in "N:/Projekte/NiN/Hime/app/backend/app/services/"*.py; do
  echo "=== $(basename $f) ==="
  wc -l "$f"
  grep -n "^class \|^def \|^async def " "$f" | head -15
done
```

- [ ] **Step 6.4: Pipeline orchestrator inspection**

Read key files:
- `N:\Projekte\NiN\Hime\app\backend\app\pipeline\runner.py`
- `N:\Projekte\NiN\Hime\app\backend\app\pipeline\runner_v2.py`

Check:
- Does it orchestrate Stage 1 → Stage 4 in order?
- Is model list from config or hardcoded?
- VRAM management (`torch.cuda.empty_cache`, `del model`)?
- Retry loop with reader feedback (max 3 iterations)?

- [ ] **Step 6.5: Security basics**

Check:
```bash
# API key mechanism
grep -rn "api.key\|API_KEY\|x-api-key\|Bearer\|Authorization" "N:/Projekte/NiN/Hime/app/backend/app/" --include="*.py" | head -20

# Path traversal protection
grep -rn "path_traversal\|sanitize.*path\|\.\./" "N:/Projekte/NiN/Hime/app/backend/app/" --include="*.py" | head -10

# Input sanitization
cat "N:/Projekte/NiN/Hime/app/backend/app/utils/sanitize.py" | head -40

# Audit log
grep -rn "audit" "N:/Projekte/NiN/Hime/app/backend/app/middleware/" --include="*.py" | head -10
```

- [ ] **Step 6.6: Import test (no server start)**

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
conda run -n hime python -c "
import sys
sys.path.insert(0, '.')
try:
    from app.main import app
    print(f'App imported OK. Routes: {len(app.routes)}')
    for r in app.routes:
        if hasattr(r, 'path') and hasattr(r, 'methods'):
            print(f'  {r.methods} {r.path}')
except Exception as e:
    print(f'IMPORT FEHLER: {type(e).__name__}: {e}')
" 2>&1
```

Log all import errors. Do NOT start uvicorn.

- [ ] **Step 6.7: Write 06_backend.md**

```markdown
# Phase 6 — Backend-Code-Integration

## Einstiegspunkt
- main.py: [status]
- run.py: [status]
- Binding: [127.0.0.1:port]
- CORS: [origins]

## Router-Inventar
| Router | Prefix | Endpoints | Auth | Rate-Limit |
|---|---|---|---|---|
| pipeline.py | ... | ... | ... | ... |
[etc.]

### Soll-Abgleich
| Erwarteter Router | Status |
|---|---|
| translate.py | vorhanden / fehlt / umbenannt zu X |
[etc.]

## Services
| Service | Zeilen | Klassen/Funktionen |
|---|---|---|
[list]

## Pipeline-Orchestrator
- runner.py: [beschreibung]
- runner_v2.py: [beschreibung]
- Stage-Reihenfolge: [korrekt/fehlt]
- VRAM-Management: [vorhanden/fehlt]
- Retry-Loop: [vorhanden/fehlt]

## Sicherheit
| Check | Status |
|---|---|
| API-Key-Mechanismus | ... |
| Path-Traversal-Schutz | ... |
| Input-Sanitization | ... |
| Audit-Log | ... |

## Import-Test
[result: success with N routes / FEHLER with details]

## Probleme
[list]
```

**HALT — Ausgabe: "Phase 6 abgeschlossen. `06_backend.md` geschrieben. Warte auf `Proceed with Phase 7`."**

---

### Task 7: Frontend-Integration (Phase 7)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/07_frontend.md`

- [ ] **Step 7.1: Frontend structure**

```bash
find "N:/Projekte/NiN/Hime/app/frontend/src" -name "*.tsx" -o -name "*.ts" | sort
```

- [ ] **Step 7.2: Tauri config**

Read `N:\Projekte\NiN\Hime\app\frontend\src-tauri\tauri.conf.json`. Check:
- `identifier` == `dev.Ninym.hime`?
- Bundle config?
- No duplicate `winresource` block?

- [ ] **Step 7.3: API client**

```bash
# Find API client files
find "N:/Projekte/NiN/Hime/app/frontend/src" -path "*/api/*" -name "*.ts" -o -path "*/api/*" -name "*.tsx" | sort
```

Read each API client file. Check:
- Base URL matches backend port?
- List all API functions

- [ ] **Step 7.4: Backend route ↔ Frontend caller matching**

Cross-reference all backend routes (from Task 6) with frontend API calls. Build a table:

| Backend Route | Frontend Caller | Match |
|---|---|---|
| POST /pipeline/{book_id}/preprocess | api/pipeline.ts:preprocess() | OK |
| ... | ... | FEHLT (kein Frontend-Caller) |

- [ ] **Step 7.5: Views inventory**

```bash
find "N:/Projekte/NiN/Hime/app/frontend/src/views" -name "*.tsx" -o -name "*.ts" | sort
```

Expected views: Translator, Comparison, Editor, Training Monitor, Library, Glossary. Check which exist and which are missing.

- [ ] **Step 7.6: Build sanity (inspection only)**

Read `package.json` scripts section. Do NOT run `npm run build` or `cargo tauri build`.

Check for known issues:
```bash
# Tauri winresource conflicts
grep -rn "winresource\|WinRes" "N:/Projekte/NiN/Hime/app/frontend/src-tauri/" --include="*.toml" --include="*.json" 2>/dev/null
```

- [ ] **Step 7.7: Write 07_frontend.md**

```markdown
# Phase 7 — Frontend-Integration

## Dateistruktur
[file tree]

## Tauri-Konfiguration
- Identifier: [value, matches dev.Ninym.hime?]
- Bundle: [config]
- winresource: [conflicts?]

## API-Client
- Base-URL: [value, matches backend port?]
| API-Funktion | Backend-Route | Match |
|---|---|---|

## Views
| Erwartete View | Status | Datei |
|---|---|---|
| Translator | ... | ... |
[etc.]

## Build-Scripts
[from package.json, inspect only]

## Probleme
[list]
```

**HALT — Ausgabe: "Phase 7 abgeschlossen. `07_frontend.md` geschrieben. Warte auf `Proceed with Phase 8`."**

---

### Task 8: Integrations-Tests (Phase 8)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/08_integration_tests.md`

- [ ] **Step 8.1: Backend import chain**

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
conda run -n hime python -c "
import sys
sys.path.insert(0, '.')
errors = []

# Import all routers
import os
for f in os.listdir('app/routers'):
    if f.endswith('.py') and f != '__init__.py':
        mod = f'app.routers.{f[:-3]}'
        try:
            __import__(mod)
            print(f'  OK: {mod}')
        except Exception as e:
            errors.append(f'{mod}: {type(e).__name__}: {e}')
            print(f'  FEHLER: {mod}: {e}')

# Import all services
for f in os.listdir('app/services'):
    if f.endswith('.py') and f != '__init__.py':
        mod = f'app.services.{f[:-3]}'
        try:
            __import__(mod)
            print(f'  OK: {mod}')
        except Exception as e:
            errors.append(f'{mod}: {type(e).__name__}: {e}')
            print(f'  FEHLER: {mod}: {e}')

print(f'\nGesamt-Fehler: {len(errors)}')
for e in errors:
    print(f'  - {e}')
" 2>&1
```

- [ ] **Step 8.2: Ollama availability**

```bash
ollama list 2>&1
ollama ps 2>&1
curl -s http://127.0.0.1:11434/api/tags 2>&1 | head -50
```

Do NOT run `ollama run` or send any prompts.

- [ ] **Step 8.3: DB read tests**

For each table found in Phase 4:

```bash
sqlite3 "N:/Projekte/NiN/Hime/hime.db" "SELECT count(*) FROM <table>;"
```

No writes. Just counts.

- [ ] **Step 8.4: MeCab sanity check**

```bash
conda run -n hime python -c "
import fugashi
t = fugashi.Tagger()
result = [w.surface for w in t('今日はいい天気です')]
print(f'MeCab OK: {result}')
" 2>&1
```

If fails: note as finding, do NOT install anything.

- [ ] **Step 8.5: Pipeline dry-run inspection**

Check if the pipeline orchestrator has a dry-run flag or can be initialized without running:

```bash
# Check runner.py for dry-run support
grep -n "dry.run\|DRY_RUN\|dry_run\|simulate" "N:/Projekte/NiN/Hime/app/backend/app/pipeline/runner.py" "N:/Projekte/NiN/Hime/app/backend/app/pipeline/runner_v2.py" 2>/dev/null
```

Inspect the constructor of the pipeline runner — can it be instantiated without loading models or calling `.run()`?

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
conda run -n hime python -c "
import sys
sys.path.insert(0, '.')
# Only inspect the class, do NOT call .run()
try:
    from app.pipeline.runner_v2 import *
    import inspect
    for name, obj in locals().copy().items():
        if inspect.isclass(obj):
            print(f'Klasse: {name}')
            print(f'  __init__ params: {inspect.signature(obj.__init__)}')
            methods = [m for m in dir(obj) if not m.startswith('_') and callable(getattr(obj, m, None))]
            print(f'  Methoden: {methods}')
except Exception as e:
    print(f'FEHLER: {type(e).__name__}: {e}')
" 2>&1
```

Do NOT instantiate the class or call any methods that could load models. Only inspect the interface.

If no dry-run flag exists: note as open item ("Kein Dry-Run-Flag im Pipeline-Orchestrator").

- [ ] **Step 8.6: Config path validation**

Read `N:\Projekte\NiN\Hime\app\backend\app\core\paths.py` and check all configured paths actually exist:

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
conda run -n hime python -c "
import sys, os
sys.path.insert(0, '.')
os.environ.setdefault('HIME_PROJECT_ROOT', 'N:/Projekte/NiN/Hime')
try:
    from app.core.paths import *
    # Check each path attribute that exists
    import inspect
    mod = sys.modules['app.core.paths']
    for name, val in sorted(vars(mod).items()):
        if isinstance(val, (str,)) and ('/' in val or '\\\\' in val):
            exists = os.path.exists(val)
            status = 'OK' if exists else 'FEHLT'
            print(f'  {name}: {val} [{status}]')
except Exception as e:
    print(f'FEHLER: {e}')
" 2>&1
```

- [ ] **Step 8.7: Write 08_integration_tests.md**

```markdown
# Phase 8 — Integrations-Tests

## Backend Import-Chain
| Modul | Status |
|---|---|
| app.routers.pipeline | OK / FEHLER |
[etc.]

## Ollama-Verfügbarkeit
- Daemon: [läuft / nicht erreichbar]
- Registrierte Modelle: [list]
- API: [erreichbar / nicht erreichbar]

## DB-Read-Tests
| Tabelle | Zeilen | Status |
|---|---|---|
[counts]

## MeCab Sanity-Check
[result: OK / FEHLT]

## Config-Pfad-Validierung
| Pfad-Variable | Wert | Existiert |
|---|---|---|
[list]

## Zusammenfassung
- Erfolgreiche Checks: N
- Fehlgeschlagene Checks: N
- Details: [list failures]
```

**HALT — Ausgabe: "Phase 8 abgeschlossen. `08_integration_tests.md` geschrieben. Warte auf `Proceed with Final Report`."**

---

### Task 9: FINAL REPORT (Phase 9)

**Files:**
- Create: `reports/verification_YYYYMMDD_HHMM/FINAL_REPORT.md`

- [ ] **Step 9.1: Collect all findings**

Read all 8 partial reports (00–08) and categorize every finding as:
- Critical (blockiert Pipeline)
- Warning (nicht blockierend, aber zu beachten)
- OK (funktioniert)

- [ ] **Step 9.2: Write FINAL_REPORT.md**

Use this exact structure:

```markdown
# Hime — System Verification Report
**Datum:** YYYY-MM-DD HH:MM
**Pfad:** N:\Projekte\NiN\Hime
**Git Commit:** <hash>
**Branch:** <branch>

---

## TL;DR

- ✅ Was funktioniert (max 5 Bullet-Points)
- ⚠️ Was teilweise funktioniert (max 5 Bullet-Points)
- ❌ Was fehlt / kaputt ist (max 5 Bullet-Points)
- 🎯 Nächste 3 empfohlene Schritte

---

## 1. Environment
[Zusammenfassung aus 01_environment.md]

## 2. Modelle
[Tabelle Soll vs. Ist aus 02_models.md]
[Liste fehlender Modelle mit HF-IDs und geschätzten Download-Größen]
[Liste Alt-Modelle als Aufräum-Kandidaten]

## 3. Training
[Status aus 03_training.md]
[Welche Modelle sind trainings-ready, welche nicht, warum]

## 4. Datenbank
[Status aus 04_database.md]

## 5. RAG
[Status aus 05_rag.md: implementiert / teilweise / fehlt]

## 6. Backend
[Router-Matrix, Services-Status]

## 7. Frontend
[Views-Status, API-Matching]

## 8. Integrations-Tests
[Ergebnisse]

---

## 🔴 Critical Issues (blockieren Pipeline)

[Pro Eintrag:]
- Was fehlt / ist kaputt
- Warum es blockiert
- Was zum Fix nötig wäre (keine Umsetzung, nur Beschreibung)

## 🟡 Warnings (nicht blockierend, aber zu beachten)

## 🟢 Alles OK
[Liste der Komponenten die vollständig funktionsfähig sind]

---

## Aufräum-Empfehlungen

Alt-Modelle aus v1-Pipeline die gelöscht werden könnten (mit Gesamtgröße).
**Claude Code löscht nichts automatisch — Luca entscheidet.**

---

## Nächste Schritte — empfohlene Reihenfolge

1. …
2. …
3. …
```

Quality requirements:
- Every claim references the specific phase report and check it came from
- Missing models include **exact HuggingFace model IDs** for download
- No vague statements — "getestet" or "ungetestet"
- Critical/Warning/OK derived only from phase reports, no new information

- [ ] **Step 9.3: Output final path**

Print the full path to the report and a max 10-line chat summary. No automatic follow-up actions beyond "Luca liest den Report".

**END — Keine weiteren Phasen.**
