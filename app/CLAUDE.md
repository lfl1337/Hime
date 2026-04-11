# Hime — Project Context for Claude

## What this project is

Hime is a **local-first** Japanese-to-English light novel translation desktop app (yuri focus). It runs entirely on the user's machine with no cloud backend, no external auth, and no third-party storage. Translation is performed by local AI models served via llama.cpp or vllm — no data leaves the machine.

## Architecture (v2.0.0)

```
User
  └── Tauri desktop app (frontend/)
        └── HTTP/WebSocket → FastAPI (backend/, 127.0.0.1:18420)
              ├── SQLite (source texts, translations, EPUB library)
              ├── Pipeline v2 (backend/app/pipeline/)
              │     ├── Pre-Processing — MeCab + JMdict + Glossary + RAG
              │     ├── Stage 1 — 4 models in parallel (Unsloth/Transformers, local)
              │     │     ├── Qwen2.5-32B+LoRA   (Draft translator, fine-tuned)
              │     │     ├── TranslateGemma-12B  (Google translate architecture)
              │     │     ├── Qwen3.5-9B          (Reasoning-oriented, non-thinking)
              │     │     └── Gemma4-E4B          (Efficient Google model)
              │     ├── Stage 2 — TranslateGemma-27B merger (zero-shot)
              │     ├── Stage 3 — Qwen3-30B-A3B MoE polish (zero-shot, non-thinking)
              │     └── Stage 4 — 15-persona Reader Panel + LFM2-24B aggregator
              │           ├── fix_pass → Stage 3 retry (max 2×)
              │           └── full_retry → Stage 1→2→3 re-run (max 1×)
              ├── RAG Store (rag/store.py) — BGE-M3 embeddings, sqlite-vec KNN
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
| AI Models        | Qwen2.5-32B / TranslateGemma / Qwen3.5 / Qwen3-30B / LFM2 | Local-first; Stage 1 LoRA-trained |
| Inference        | Unsloth (Stage 1/2) / vLLM or direct (Stage 3/4)           | No external API calls             |
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

| Service                | Default Port | Notes                                  |
|------------------------|-------------|----------------------------------------|
| Hime Vite (dev)        | 1420        | Proxies /api, /ws → FastAPI            |
| Hime FastAPI           | 18420       | Range 18420–18430                      |
| v1 model servers       | 8001–8005   | Not used in v2 pipeline (llama.cpp)    |

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
| `backend/app/pipeline/runner_v2.py`      | v2 pipeline orchestrator (4 stages + retry loop) |
| `backend/app/pipeline/stage4_aggregator.py` | 15-persona panel + LFM2-24B verdict          |
| `backend/app/pipeline/prompts.py`        | Template loader (disk → inline fallback)         |
| `backend/app/services/model_manager.py`  | Health checks + v1 model port status             |
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
