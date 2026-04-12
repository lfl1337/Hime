# WS4: System Check & Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all hardcoded absolute paths, create a centralized path resolution module, audit SQLite indexes, clean up dead code/TODOs, update project documentation, and produce a comprehensive AUDIT_REPORT.md.

**Architecture:** Create `app/backend/app/core/paths.py` as the single source of truth for all filesystem paths, reading from env vars with sensible relative defaults. Fix the 7 hardcoded `C:\Projekte\Hime` paths in backend config/database. Document all cross-workstream findings in AUDIT_REPORT.md.

**Tech Stack:** Python 3.11+, SQLite, TypeScript, Node.js

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `app/backend/app/core/__init__.py` | Package marker |
| Create | `app/backend/app/core/paths.py` | Centralized path resolution |
| Modify | `app/backend/app/config.py` | Import paths from core/paths.py, remove hardcoded defaults |
| Modify | `app/backend/app/database.py` | Fix hardcoded epub path in SQL seed, add indexes |
| Create | `.env.example` (project root) | Comprehensive env var template |
| Modify | `app/CLAUDE.md` | Update to v1.2.0 architecture |
| Create | `README.md` (project root) | Project README |
| Create | `AUDIT_REPORT.md` | Comprehensive audit findings |

**DO NOT touch:** `app/frontend/src/views/`, `app/backend/app/services/`, `app/backend/app/api/`, `.github/`, `scripts/train_*.py`

---

### Task 1: Create Centralized Path Resolution Module

**Files:**
- Create: `app/backend/app/core/__init__.py`
- Create: `app/backend/app/core/paths.py`

- [ ] **Step 1: Create the core package**

```python
# app/backend/app/core/__init__.py
# (empty file)
```

- [ ] **Step 2: Create paths.py**

```python
# app/backend/app/core/paths.py
"""
Centralized path resolution for the Hime backend.

All paths are derived from environment variables with sensible defaults
relative to the project root. This module is the SINGLE SOURCE OF TRUTH
for filesystem paths — import from here instead of hardcoding.

Environment variables (set in .env or system environment):
  HIME_PROJECT_ROOT     — base directory (default: 4 levels up from this file)
  HIME_DATA_DIR         — data directory (default: PROJECT_ROOT/data)
  HIME_MODELS_DIR       — models directory (default: PROJECT_ROOT/modelle)
  HIME_LOGS_DIR         — log directory (default: PROJECT_ROOT/app/backend/logs)
  HIME_EPUB_WATCH_DIR   — EPUB watch directory (default: DATA_DIR/epubs)
  HIME_TRAINING_DATA_DIR — training data (default: DATA_DIR/training)
  HIME_SCRIPTS_DIR      — scripts directory (default: PROJECT_ROOT/scripts)
"""
import os
from pathlib import Path

# PROJECT_ROOT: 4 levels up from app/backend/app/core/paths.py
_DEFAULT_ROOT = Path(__file__).resolve().parents[4]

PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT", str(_DEFAULT_ROOT)))
DATA_DIR = Path(os.environ.get("HIME_DATA_DIR", str(PROJECT_ROOT / "data")))
MODELS_DIR = Path(os.environ.get("HIME_MODELS_DIR", str(PROJECT_ROOT / "modelle")))
LOGS_DIR = Path(os.environ.get("HIME_LOGS_DIR", str(PROJECT_ROOT / "app" / "backend" / "logs")))
EPUB_WATCH_DIR = Path(os.environ.get("HIME_EPUB_WATCH_DIR", str(DATA_DIR / "epubs")))
TRAINING_DATA_DIR = Path(os.environ.get("HIME_TRAINING_DATA_DIR", str(DATA_DIR / "training")))
SCRIPTS_DIR = Path(os.environ.get("HIME_SCRIPTS_DIR", str(PROJECT_ROOT / "scripts")))
TRAINING_LOG_DIR = LOGS_DIR / "training"


def checkpoints_dir(model_name: str) -> Path:
    """Return the checkpoint directory for a specific LoRA model."""
    return Path(os.environ.get(
        "HIME_CHECKPOINTS_DIR",
        str(MODELS_DIR / "lora" / model_name / "checkpoint"),
    ))


def lora_dir(model_name: str) -> Path:
    """Return the LoRA adapter directory for a specific model."""
    return MODELS_DIR / "lora" / model_name
```

- [ ] **Step 3: Write test for paths.py**

```python
# app/backend/tests/test_paths.py
import os
from pathlib import Path

import pytest


class TestPaths:
    """Verify centralized path resolution."""

    def test_project_root_exists(self):
        from app.core.paths import PROJECT_ROOT
        assert PROJECT_ROOT.exists()

    def test_project_root_contains_app_dir(self):
        from app.core.paths import PROJECT_ROOT
        assert (PROJECT_ROOT / "app").exists()

    def test_models_dir_derived_from_root(self):
        from app.core.paths import PROJECT_ROOT, MODELS_DIR
        assert str(MODELS_DIR).startswith(str(PROJECT_ROOT))

    def test_env_override(self, monkeypatch, tmp_path):
        """HIME_PROJECT_ROOT env var overrides default."""
        monkeypatch.setenv("HIME_PROJECT_ROOT", str(tmp_path))
        # Re-import to pick up env change
        import importlib
        from app.core import paths
        importlib.reload(paths)
        assert paths.PROJECT_ROOT == tmp_path
        # Clean up: reload with original env
        monkeypatch.delenv("HIME_PROJECT_ROOT")
        importlib.reload(paths)

    def test_checkpoints_dir(self):
        from app.core.paths import checkpoints_dir, MODELS_DIR
        result = checkpoints_dir("Qwen2.5-32B-Instruct")
        assert "Qwen2.5-32B-Instruct" in str(result)
        assert "checkpoint" in str(result)

    def test_no_hardcoded_c_drive(self):
        """Ensure no C: drive paths in the module source."""
        from app.core import paths
        import inspect
        source = inspect.getsource(paths)
        assert "C:\\" not in source
        assert "C:/" not in source
```

- [ ] **Step 4: Run tests**

Run: `cd app/backend && python -m pytest tests/test_paths.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/backend/app/core/
git add app/backend/tests/test_paths.py
git commit -m "feat: add centralized path resolution module (core/paths.py) for disk migration prep"
```

---

### Task 2: Remove Hardcoded Paths from config.py

**Files:**
- Modify: `app/backend/app/config.py`

- [ ] **Step 1: Update config.py to use paths.py for defaults**

Replace lines 42-48 in `app/backend/app/config.py`:

Old:
```python
    epub_watch_folder_default: str = "C:/Projekte/Hime/data/epubs/"

    # Training / fine-tuning paths (override via .env if needed)
    models_base_path: str = r"C:\Projekte\Hime\modelle"
    lora_path: str = r"C:\Projekte\Hime\modelle\lora\Qwen2.5-32B-Instruct"
    training_log_path: str = r"C:\Projekte\Hime\app\backend\logs\training"
    scripts_path: str = r"C:\Projekte\Hime\scripts"
```

New:
```python
    epub_watch_folder_default: str = str(_paths.EPUB_WATCH_DIR)

    # Training / fine-tuning paths (override via .env if needed)
    models_base_path: str = str(_paths.MODELS_DIR)
    lora_path: str = str(_paths.lora_dir("Qwen2.5-32B-Instruct"))
    training_log_path: str = str(_paths.TRAINING_LOG_DIR)
    scripts_path: str = str(_paths.SCRIPTS_DIR)
```

Add the import near the top of the file (after existing imports):
```python
from .core import paths as _paths
```

- [ ] **Step 2: Verify config loads correctly**

Run: `cd app/backend && python -c "from app.config import settings; print('epub:', settings.epub_watch_folder_default); print('models:', settings.models_base_path); print('scripts:', settings.scripts_path)"`

Expected: Paths are relative to project root, no `C:\Projekte\Hime` in output (unless that IS the project root, which is fine — the point is it's derived, not hardcoded).

- [ ] **Step 3: Commit**

```bash
git add app/backend/app/config.py
git commit -m "fix: replace hardcoded C:\Projekte\Hime paths in config.py with core/paths.py"
```

---

### Task 3: Fix Hardcoded Path in database.py Seed Data

**Files:**
- Modify: `app/backend/app/database.py`

- [ ] **Step 1: Update the SQL seed value**

In `app/backend/app/database.py`, replace line 95-97:

Old:
```python
        await conn.execute(text(
            "INSERT OR IGNORE INTO settings (key, value) VALUES "
            "('epub_watch_folder', 'C:/Projekte/Hime/data/epubs/'), "
            "('auto_scan_interval', '60')"
        ))
```

New:
```python
        from .core.paths import EPUB_WATCH_DIR
        _epub_default = str(EPUB_WATCH_DIR).replace("\\", "/")
        await conn.execute(text(
            "INSERT OR IGNORE INTO settings (key, value) VALUES "
            f"('epub_watch_folder', '{_epub_default}'), "
            "('auto_scan_interval', '60')"
        ))
```

- [ ] **Step 2: Add missing database indexes**

In the same `init_db()` function, after the existing index creation (lines 79-85), add:

```python
        # Indexes for EPUB query patterns
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_chapters_book_id ON chapters(book_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_paragraphs_chapter_id ON paragraphs(chapter_id)"
        ))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_translations_source_text_id ON translations(source_text_id)"
        ))
```

- [ ] **Step 3: Verify database initializes correctly**

Run: `cd app/backend && python -c "import asyncio; from app.database import init_db; asyncio.run(init_db()); print('DB init OK')"`
Expected: "DB init OK" with no errors.

- [ ] **Step 4: Commit**

```bash
git add app/backend/app/database.py
git commit -m "fix: remove hardcoded path in DB seed, add missing indexes for chapters/paragraphs"
```

---

### Task 4: Create Project-Root .env.example

**Files:**
- Create: `.env.example` (project root)

- [ ] **Step 1: Create comprehensive .env.example**

```env
# Hime — Environment Configuration
# Copy this file to .env and adjust values for your system.
# All paths are optional — sensible defaults are derived from the project root.

# === Paths (override for disk migration) ===
# HIME_PROJECT_ROOT=            # Auto-detected from code location
# HIME_DATA_DIR=                # Default: ${HIME_PROJECT_ROOT}/data
# HIME_MODELS_DIR=              # Default: ${HIME_PROJECT_ROOT}/modelle
# HIME_LOGS_DIR=                # Default: ${HIME_PROJECT_ROOT}/app/backend/logs
# HIME_CHECKPOINTS_DIR=         # Default: ${HIME_MODELS_DIR}/lora/{model}/checkpoint
# HIME_EPUB_WATCH_DIR=          # Default: ${HIME_DATA_DIR}/epubs
# HIME_TRAINING_DATA_DIR=       # Default: ${HIME_DATA_DIR}/training
# HIME_SCRIPTS_DIR=             # Default: ${HIME_PROJECT_ROOT}/scripts

# === Backend ===
PORT=18420
RATE_LIMIT_PER_MINUTE=60

# === Legacy single-model inference ===
INFERENCE_URL=http://127.0.0.1:8080/v1
INFERENCE_MODEL=qwen2.5-14b-instruct

# === Pipeline Model Endpoints ===
# Stage 1 — Three parallel translators
HIME_GEMMA_URL=http://127.0.0.1:8001/v1
HIME_GEMMA_MODEL=hime-gemma
HIME_DEEPSEEK_URL=http://127.0.0.1:8002/v1
HIME_DEEPSEEK_MODEL=hime-deepseek
HIME_QWEN32B_URL=http://127.0.0.1:8003/v1
HIME_QWEN32B_MODEL=hime-qwen32b

# Consensus — Merger model
HIME_MERGER_URL=http://127.0.0.1:8003/v1
HIME_MERGER_MODEL=hime-qwen32b

# Stage 2 — 72B Refinement
HIME_QWEN72B_URL=http://127.0.0.1:8004/v1
HIME_QWEN72B_MODEL=hime-qwen72b

# Stage 3 — 14B Final Polish
HIME_QWEN14B_URL=http://127.0.0.1:8005/v1
HIME_QWEN14B_MODEL=hime-qwen14b

# === App Config ===
# HIME_API_KEY=              # Auto-generated on first run if empty
HIME_BIND_HOST=127.0.0.1
HIME_BACKEND_PORT=18420

# === Training paths (legacy, prefer HIME_MODELS_DIR) ===
# MODELS_BASE_PATH=
# LORA_PATH=
# TRAINING_LOG_PATH=
# SCRIPTS_PATH=
# EPUB_WATCH_FOLDER_DEFAULT=
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add comprehensive .env.example at project root for disk migration prep"
```

---

### Task 5: TypeScript `any` Audit

**Files:**
- Audit: `app/frontend/src/`

- [ ] **Step 1: Search for all `any` types**

Run: `grep -rn ": any" app/frontend/src/ --include="*.ts" --include="*.tsx" | grep -v node_modules`

Document each occurrence with file, line, and whether it can be replaced with a proper type.

- [ ] **Step 2: Document findings in AUDIT_REPORT.md (Task 9)**

For each `any` usage, note:
- File and line
- Whether it's replaceable
- Suggested replacement type (if applicable)
- Justification if `any` is intentional

**Do NOT fix these** — only document. WS3 owns the frontend files.

---

### Task 6: Dead Code & TODO Scan

**Files:**
- Audit: entire project

- [ ] **Step 1: Scan for TODOs and FIXMEs**

Run: `grep -rn "TODO\|FIXME\|HACK\|XXX" . --include="*.py" --include="*.ts" --include="*.tsx" | grep -v node_modules | grep -v __pycache__ | grep -v ".git/"`

- [ ] **Step 2: Scan for unused imports in WS4-owned files**

Run: `grep -rn "^import\|^from" app/backend/app/core/ app/backend/app/database.py`

Only remove dead code in files owned by this workstream.

- [ ] **Step 3: Document all findings**

Add findings to AUDIT_REPORT.md (Task 9).

---

### Task 7: Update CLAUDE.md

**Files:**
- Modify: `app/CLAUDE.md`

- [ ] **Step 1: Rewrite CLAUDE.md for v1.2.0**

Replace the full content of `app/CLAUDE.md`:

```markdown
# Hime — Project Context for Claude

## What this project is

Hime is a **local-first** Japanese-to-English light novel translation desktop app (yuri focus). It runs entirely on the user's machine with no cloud backend, no external auth, and no third-party storage. Translation is performed by local AI models served via llama.cpp or vllm — no data leaves the machine.

## Architecture

```
User
  └── Tauri desktop app (frontend/)
        └── HTTP/WebSocket → FastAPI (backend/, 127.0.0.1:18420)
              ├── SQLite (source texts, translations, EPUB library)
              ├── Pipeline (backend/app/pipeline/)
              │     ├── Stage 1 — 3 parallel translators
              │     │     ├── Gemma 3 12B (port 8001)
              │     │     ├── DeepSeek R1 32B (port 8002)
              │     │     └── Qwen 2.5 32B (port 8003)
              │     ├── Consensus — merger model (port 8003)
              │     ├── Stage 2 — Qwen 2.5 72B refinement (port 8004)
              │     └── Stage 3 — Qwen 2.5 14B final polish (port 8005)
              ├── Model Manager (services/model_manager.py) — health checks
              ├── Training Runner (services/training_runner.py) — LoRA fine-tuning
              └── Audit log (logs/audit.log)
```

## Stack

| Concern          | Choice                        | Why                                              |
|------------------|-------------------------------|--------------------------------------------------|
| Backend          | Python 3.11+ / FastAPI        | Async, OpenAPI docs, Pydantic validation         |
| Frontend         | React 19 + Tauri              | Small binaries, Rust security, modern React      |
| CSS              | Tailwind CSS                  | Utility-first, dark theme, Japanese font support |
| State            | Zustand + persist             | Lightweight, localStorage persistence            |
| Database         | SQLite + SQLAlchemy async     | Local-first, zero setup, single user             |
| AI Models        | Qwen2.5 / Gemma 3 / DeepSeek | Local-first; LoRA adapters trained on JP→EN data |
| Inference        | llama.cpp / vllm              | OpenAI-compatible API on localhost               |
| Package mgr      | uv (backend), npm (frontend)  | Fast, lockfile support                           |

## Path Configuration

All paths are resolved from environment variables with relative fallbacks. See `app/backend/app/core/paths.py`.

Key environment variables (set in `.env` or system):
```
HIME_PROJECT_ROOT     — base directory (auto-detected)
HIME_DATA_DIR         — data/ (epubs, training data)
HIME_MODELS_DIR       — modelle/ (LoRA adapters, GGUF)
HIME_LOGS_DIR         — app/backend/logs/
HIME_EPUB_WATCH_DIR   — data/epubs/
HIME_TRAINING_DATA_DIR — data/training/
HIME_SCRIPTS_DIR      — scripts/
```

## Port Registry

| Service                | Default Port | Range        |
|------------------------|-------------|--------------|
| Hime Vite (dev)        | 1420        | —            |
| Hime FastAPI           | 18420       | 18420–18430  |
| Gemma 3 12B            | 8001        | —            |
| DeepSeek R1 32B        | 8002        | —            |
| Qwen 2.5 32B           | 8003        | —            |
| Qwen 2.5 72B           | 8004        | —            |
| Qwen 2.5 14B           | 8005        | —            |

## Security Constraints (non-negotiable)

- FastAPI binds to `127.0.0.1` only — never `0.0.0.0`
- CORS restricted to `http://localhost:1420` and `https://tauri.localhost`
- `.env` never committed to git
- All user text sanitized for null bytes, env var syntax, prompt injection
- All requests logged to `logs/audit.log` (local only)
- Translation by local model only — no external API calls
- Training subprocesses use Windows Job Objects for child cleanup

## Key Files

| File                                      | Purpose                                         |
|-------------------------------------------|--------------------------------------------------|
| `backend/run.py`                          | Entry point — enforces 127.0.0.1 binding        |
| `backend/app/core/paths.py`              | Centralized path resolution from env vars        |
| `backend/app/config.py`                  | Pydantic settings (reads .env)                   |
| `backend/app/database.py`               | Async SQLAlchemy + inline migrations             |
| `backend/app/models.py`                 | ORM: SourceText, Translation, Book, Chapter, etc |
| `backend/app/pipeline/runner.py`         | 4-stage pipeline orchestrator                    |
| `backend/app/pipeline/prompts.py`        | Template loader (disk → inline fallback)         |
| `backend/app/services/model_manager.py`  | Health checks for all 6 pipeline models          |
| `backend/app/services/training_runner.py`| LoRA training subprocess management              |
| `backend/app/services/epub_service.py`   | EPUB parsing, import, library management         |
| `backend/app/websocket/streaming.py`     | Pipeline WebSocket streaming                     |
| `backend/app/middleware/audit.py`        | JSON-lines request audit logging                 |
| `backend/app/utils/sanitize.py`         | Input validation + prompt injection defense      |

## Coding Conventions

- Python: `async`/`await` throughout, Pydantic v2 for validation
- FastAPI dependencies for auth, db sessions
- All new endpoints must call `sanitize_text()` on user-supplied strings
- Rate-limit decorators on mutation/expensive endpoints
- Prompt templates: editable `.txt` files in `backend/app/prompts/`
- Frontend: React 19, TypeScript strict, Tailwind utility classes, Zustand for state
- Do NOT touch `TrainingMonitor.tsx` — recently refactored, memory leak fixes

## Versioning

Source of truth: `app/VERSION`

After code changes:
```
python scripts/bump_version.py patch
git push && git push --tags
```

Updates: tauri.conf.json, Cargo.toml, package.json, main.py, Sidebar.tsx

## Disk Migration Note

The project will be transferred to a different disk. All paths MUST be derived from environment variables or relative paths — never hardcoded. See `core/paths.py` and `.env.example`.
```

- [ ] **Step 2: Commit**

```bash
git add app/CLAUDE.md
git commit -m "docs: update CLAUDE.md for v1.2.0 — pipeline architecture, path config, port registry"
```

---

### Task 8: Create README.md

**Files:**
- Create: `README.md` (project root)

- [ ] **Step 1: Write README.md**

```markdown
# Hime — Japanese-to-English Light Novel Translation Suite

Hime is a local-first desktop application for translating Japanese light novels to English using AI. All translation happens on your machine — no data leaves your computer.

## Features

- **Multi-stage translation pipeline** — 3 models translate in parallel, results are merged, refined, and polished
- **EPUB import** — drag & drop Japanese EPUBs, translate chapter by chapter
- **Live streaming** — watch translations appear in real-time via WebSocket
- **Training monitor** — fine-tune LoRA adapters with built-in loss charts and hardware monitoring
- **Offline-first** — EPUB library and translation history work without models running

## Architecture

```
Stage 1 — Parallel Draft Translation
  ├── Gemma 3 12B        (LoRA adapter)
  ├── DeepSeek R1 32B    (LoRA adapter)
  └── Qwen 2.5 32B       (LoRA adapter)

Stage 1.5 — Consensus Merge

Stage 2 — Refinement (Qwen 2.5 72B)

Stage 3 — Final Polish (Qwen 2.5 14B)
```

## Prerequisites

- Windows 10/11 (primary target)
- [Conda](https://docs.conda.io/) with a `hime` environment
- Node.js 20+ and npm
- Rust toolchain (for Tauri)
- A local inference server (llama.cpp, vllm, Ollama, or LM Studio)

## Setup

1. **Clone and configure paths:**

```bash
git clone <repo-url> Hime
cd Hime
cp .env.example .env
# Edit .env to set paths for your system (or leave defaults)
```

2. **Backend:**

```bash
cd app/backend
conda activate hime
uv pip install -r requirements.txt  # or: pip install -r requirements.txt
python run.py
```

3. **Frontend:**

```bash
cd app/frontend
npm install
npm run tauri dev    # or: npm run vite (browser-only dev mode)
```

4. **Start inference servers** on ports 8001-8005 with your LoRA adapters loaded.

## Path Configuration

All paths are derived from environment variables. Set them in `.env`:

| Variable               | Default                          | Purpose                    |
|------------------------|----------------------------------|----------------------------|
| `HIME_PROJECT_ROOT`   | Auto-detected                    | Base directory             |
| `HIME_DATA_DIR`       | `${ROOT}/data`                  | EPUBs, training data       |
| `HIME_MODELS_DIR`     | `${ROOT}/modelle`               | LoRA adapters, GGUF models |
| `HIME_LOGS_DIR`       | `${ROOT}/app/backend/logs`      | Backend and training logs  |

## License

[To be determined]
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add project README with setup instructions and architecture overview"
```

---

### Task 9: Bundle Size Check

- [ ] **Step 1: Run frontend build**

Run: `cd app/frontend && npm run vite build 2>&1`

- [ ] **Step 2: Check output size**

Run: `du -sh app/frontend/dist/ && find app/frontend/dist -name "*.js" -exec du -sh {} \; | sort -rh | head -10`

Flag anything over 500KB as a finding for AUDIT_REPORT.md.

---

### Task 10: Generate AUDIT_REPORT.md

**Files:**
- Create: `AUDIT_REPORT.md` (project root)

- [ ] **Step 1: Compile all findings into AUDIT_REPORT.md**

```markdown
# Hime v1.2.0 Audit Report

Generated: 2026-04-06

## Summary

| Severity | Count |
|----------|-------|
| Critical | TBD   |
| High     | TBD   |
| Medium   | TBD   |
| Low      | TBD   |
| Info     | TBD   |

## Top 5 Most Urgent Fixes

1. TBD (filled after running all scans)
2. TBD
3. TBD
4. TBD
5. TBD

---

## Findings

### AUDIT-001: Hardcoded Paths in Backend (FIXED by WS4)
- **Severity:** High
- **Category:** Disk Migration
- **Files:** `app/backend/app/config.py:42-48`, `app/backend/app/database.py:96`
- **Description:** 7 hardcoded `C:\Projekte\Hime` paths in backend config defaults and DB seed.
- **Recommendation:** Fixed — replaced with `core/paths.py` env-var-driven resolution.
- **Effort:** Done

### AUDIT-002: Hardcoded Paths in Scripts (NOT FIXED — different owner)
- **Severity:** High
- **Category:** Disk Migration
- **Files:**
  - `scripts/align_shuukura.py:16`
  - `scripts/analyze_training_data.py:19`
  - `scripts/check_format.py:1`
  - `scripts/convert_jparacrawl.py:11`
  - `scripts/epub_extractor.py:15`
  - `scripts/scraper.py:15`
  - `scripts/scraper_kakuyomu.py:12`
  - `scripts/scraper_skythewood.py:16`
  - `scripts/download_jparacrawl.py:14`
  - `scripts/train_debug.py:22-23`
  - `scripts/train_generic.py:91`
  - `scripts/train_hime.py:63`
  - `scripts/train_restart_loop.py:30`
- **Description:** 13 scripts have hardcoded `C:\Projekte\Hime` as PROJECT_ROOT.
- **Recommendation:** Replace with `Path(__file__).resolve().parent.parent` or env var. `train_hime.py` and `train_generic.py` are handled by WS2 (path audit). Data prep scripts need separate attention.
- **Effort:** 30min per script

### AUDIT-003: Hardcoded Path in Tauri Rust Code
- **Severity:** High
- **Category:** Disk Migration
- **File:** `app/frontend/src-tauri/src/lib.rs:265`
- **Description:** `r"C:\Projekte\Hime\app\backend\hime-backend.lock"` hardcoded in Tauri Rust source.
- **Recommendation:** Use Tauri's `app.path_resolver().app_data_dir()` instead.
- **Effort:** 15min

### AUDIT-004: Missing SQLite Indexes (FIXED by WS4)
- **Severity:** Medium
- **Category:** Performance
- **Files:** `app/backend/app/database.py`
- **Description:** Missing indexes on `chapters.book_id`, `paragraphs.chapter_id`, `translations.source_text_id`.
- **Recommendation:** Fixed — added in init_db().
- **Effort:** Done

### AUDIT-005: TypeScript `any` Usage
- **Severity:** Low
- **Category:** Code Quality
- **Files:** (list each occurrence found in Task 5)
- **Description:** `any` types reduce type safety.
- **Recommendation:** Replace with proper types where feasible. Document remaining uses.
- **Effort:** 1-2h

### AUDIT-006: TODO/FIXME Findings
- **Severity:** Info
- **Category:** Code Quality
- **Files:** (list each occurrence found in Task 6)
- **Description:** Outstanding TODOs in codebase.
- **Recommendation:** Triage and either fix or convert to GitHub issues.
- **Effort:** Varies

### AUDIT-007: Bundle Size
- **Severity:** (TBD based on measurement)
- **Category:** Performance
- **Description:** Frontend bundle size analysis from Task 9.
- **Recommendation:** (TBD)

### AUDIT-008: Gemma Model Name
- **Severity:** Low
- **Category:** UI
- **File:** `app/frontend/src/components/comparison/modelConfig.ts:2`
- **Description:** Gemma displayed as "27B" but should be "12B" per updated model list.
- **Recommendation:** Fixed by WS3.
- **Effort:** Done
```

**Important:** Run the actual scans (Tasks 5, 6, 9) and fill in the TBD sections with real data before finalizing.

- [ ] **Step 2: Commit**

```bash
git add AUDIT_REPORT.md
git commit -m "docs: generate v1.2.0 audit report with hardcoded paths, indexes, and code quality findings"
```

---

### Task 11: Final System Check Verification

- [ ] **Step 1: Run all backend tests**

Run: `cd app/backend && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Verify no C:\Projekte\Hime in WS4-owned files**

Run: `grep -rn "C:\\\\Projekte\|C:/Projekte" app/backend/app/config.py app/backend/app/database.py app/backend/app/core/`
Expected: No matches.

- [ ] **Step 3: Verify database initializes with new paths**

Run: `cd app/backend && python -c "import asyncio; from app.database import init_db; asyncio.run(init_db()); print('OK')"`
Expected: "OK"

- [ ] **Step 4: Verify file ownership**

Run: `git diff --name-only HEAD~8` (adjust count)
Confirm only WS4-owned files were modified. No files from:
- `app/frontend/src/views/`
- `app/backend/app/services/`
- `app/backend/app/routers/`
- `.github/`
- `scripts/train_*.py`
