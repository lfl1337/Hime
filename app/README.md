# Hime

Local-first Japanese-to-English light novel translation app.

## Stack

| Layer    | Technology                                      |
|----------|-------------------------------------------------|
| Backend  | Python 3.11+, FastAPI, SQLite (via aiosqlite)   |
| Frontend | Tauri + React (placeholder — not yet built)     |
| Infra    | Docker (parity env — not yet configured)        |
| Packages | uv                                              |

---

## Quick start

### Backend

```bash
cd backend

# Install dependencies with uv
uv sync

# Run (binds to 127.0.0.1:8000 only)
uv run python run.py
```

On first run, a random API key is generated and written to `backend/.env`. It is printed to the console once — keep it.

### API docs

Once the backend is running:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc:       http://127.0.0.1:8000/redoc

All endpoints require the header `X-API-Key: <your-key>`.

### WebSocket streaming

```
ws://127.0.0.1:8000/ws/translate?api_key=<your-key>
```

Send JSON: `{"text": "...", "model": "claude-opus-4-6"}`
Receive: `{"type": "token", "content": "..."}` … `{"type": "done"}`

---

## Security

- FastAPI binds **only** to `127.0.0.1` — never `0.0.0.0`
- Every request requires a local API key (`X-API-Key` header)
- All text inputs are sanitized against prompt-injection patterns
- Every request is logged to `backend/logs/audit.log`

---

## Project layout

```
app/
├── backend/          FastAPI app
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── auth.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── routers/
│   │   ├── middleware/
│   │   ├── websocket/
│   │   └── utils/
│   ├── pyproject.toml
│   └── run.py
├── frontend/         Tauri + React (placeholder)
├── docker/           Docker configs (placeholder)
└── CLAUDE.md         Project context for AI assistants
```
