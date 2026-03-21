# Hime — Project Context for Claude

## What this project is

Hime is a **local-first** Japanese-to-English light novel translation app. It runs entirely on the user's machine. There is no cloud backend, no external auth service, no third-party storage. Translation is done by local Qwen2.5-Instruct models (14B/32B/72B) served via llama.cpp or vllm — no data leaves the machine.

## Goals

1. Ingest Japanese light novel text (copy-paste or file upload)
2. Translate it chapter-by-chapter using a local Qwen2.5 model, with streaming output
3. Store source texts and translations locally in SQLite
4. Present translations in a clean desktop UI (Tauri + React)
5. Allow the user to review, edit, and export translations

## Architecture

```
User
  └── Tauri desktop app (frontend/)
        └── HTTP/WebSocket → FastAPI (backend/, 127.0.0.1:8000)
              ├── SQLite (source texts, translations + pipeline outputs)
              ├── Pipeline (backend/app/pipeline/)
              │     ├── Stage 1 — 3 parallel translators (gemma/deepseek/qwen32b)
              │     ├── Consensus — merger model synthesises best translation
              │     ├── Stage 2 — 72B refinement
              │     └── Stage 3 — 14B final polish → final_output
              ├── Local inference servers (llama.cpp/vllm, ports 8001-8005)
              └── Audit log (logs/audit.log)
```

## Stack decisions

| Concern          | Choice                       | Why                                                   |
|------------------|------------------------------|-------------------------------------------------------|
| Backend language | Python 3.11+                 | Fast iteration, great AI library support              |
| Web framework    | FastAPI                      | Async, automatic OpenAPI docs, Pydantic validation    |
| Package manager  | uv                           | Fast, lockfile, same commands work in Docker          |
| Database         | SQLite + SQLAlchemy async    | Local-first, zero setup, good enough for single user  |
| Desktop shell    | Tauri                        | Small binaries, Rust security, React frontend         |
| AI model         | Qwen2.5-Instruct (14B/32B/72B) | Local-first; no data leaves the machine             |
| Inference server | llama.cpp / vllm (local)     | OpenAI-compatible API on localhost                    |

## Security constraints (non-negotiable)

- The FastAPI server **must** bind to `127.0.0.1` only. Never `0.0.0.0`.
- Every API endpoint requires `X-API-Key` header matching the key in `backend/.env`.
- The `.env` file must never be committed to git.
- All user-supplied text is sanitized for prompt-injection patterns before being passed to the local model.
- All requests are logged to `backend/logs/audit.log` (local only).
- Translation is performed by a **local model only** — no external API is ever called. The inference server (llama.cpp / vllm) runs on localhost.

## Key files

| File                              | Purpose                                          |
|-----------------------------------|--------------------------------------------------|
| `backend/run.py`                  | Entry point — enforces 127.0.0.1 binding         |
| `backend/app/config.py`           | Settings + first-run API key generation          |
| `backend/app/auth.py`             | FastAPI dependency: validates X-API-Key header   |
| `backend/app/database.py`         | Async SQLAlchemy engine + session factory        |
| `backend/app/models.py`           | SourceText and Translation ORM models            |
| `backend/app/schemas.py`          | Pydantic request/response schemas                |
| `backend/app/routers/texts.py`    | CRUD for source texts                            |
| `backend/app/inference.py`            | OpenAI-compat client; `complete()`, `stream_completion()`, legacy `translate`/`translate_stream` |
| `backend/app/routers/translations.py` | POST `/translate` returns `{"job_id": N}` (202); GET/DELETE unchanged |
| `backend/app/websocket/streaming.py`  | Legacy `/ws/translate` + new `/ws/translate/{job_id}` pipeline WS |
| `backend/app/pipeline/__init__.py`    | Package marker                                                  |
| `backend/app/pipeline/prompts.py`     | All prompt templates + message-builder functions                |
| `backend/app/pipeline/runner.py`      | `run_pipeline()` coroutine — orchestrates all stages, writes DB |
| `backend/app/middleware/audit.py` | Request audit logging middleware                 |
| `backend/app/middleware/rate_limit.py` | slowapi rate limiter instance               |
| `backend/app/utils/sanitize.py`   | Prompt-injection sanitization                    |

## Docker intent

The `docker/` directory will eventually contain a `Dockerfile` and `compose.yml` that reproduce the backend environment identically. The uv lockfile ensures the same package versions in both local and Docker runs.

## What has NOT been built yet

- Frontend (Tauri + React) — placeholder only
- File upload (PDF/EPUB ingestion)
- Export (EPUB/DOCX output)
- Docker configuration

## Coding conventions

- Python: use `async`/`await` throughout the backend
- FastAPI dependencies for cross-cutting concerns (auth, db session)
- Pydantic v2 for all data validation
- All new endpoints must call `sanitize_text()` on user-supplied string inputs
- Rate-limit decorators go on mutation/expensive endpoints, not reads

## Versioning

After every session where code changes were made, always run:
```
python scripts/bump_version.py patch
git push && git push --tags
```
