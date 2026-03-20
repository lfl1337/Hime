# Hime — Local Japanese-to-English Translation Studio

Hime is a **local-first** desktop app for translating Japanese light novels into English. Everything runs on your own machine — no cloud API, no data leaves your computer. Translation is performed by local Qwen2.5-Instruct models (14B / 32B / 72B) served via llama.cpp or vllm.

---

## Project Structure

```
Hime/
├── app/
│   ├── backend/          # FastAPI server (Python, uv)
│   │   ├── app/
│   │   │   ├── config.py
│   │   │   ├── main.py
│   │   │   ├── routers/      # texts, translations, training
│   │   │   ├── pipeline/     # multi-stage translation pipeline
│   │   │   ├── services/     # training monitor
│   │   │   ├── websocket/    # streaming WebSocket
│   │   │   └── utils/
│   │   ├── run.py            # entry point (binds to 127.0.0.1 only)
│   │   ├── pyproject.toml
│   │   └── .env.example
│   ├── frontend/         # Tauri + React (TypeScript, npm)
│   │   ├── src/
│   │   │   ├── api/          # typed API client
│   │   │   ├── components/   # Sidebar, StatusBadge, …
│   │   │   └── views/        # Translator, Editor, TrainingMonitor, …
│   │   ├── src-tauri/        # Rust shell (sidecar spawn, capabilities)
│   │   └── vite.config.ts
│   └── build.bat         # One-command production build (Windows)
├── scripts/
│   ├── train_hime.py     # LoRA fine-tuning script (HuggingFace Trainer)
│   ├── build_backend.py  # PyInstaller packaging helper
│   └── …                 # data prep / scraping utilities
├── data/
│   ├── raw_jp/           # Japanese source texts
│   ├── raw_en/           # English reference texts
│   └── analysis/         # Dataset analysis outputs
└── modelle/
    ├── lmstudio-community/   # GGUF quantised models (not in git)
    └── lora/                 # LoRA adapters and checkpoints
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| [uv](https://docs.astral.sh/uv/) | ≥ 0.5 | Python package manager |
| Node.js | ≥ 20 | Frontend build |
| Rust / Cargo | stable | Tauri compilation |
| [Tauri CLI](https://tauri.app/start/prerequisites/) | v2 | Desktop shell |
| llama.cpp or vllm | — | Local inference server |

---

## Setup

```bash
# 1. Clone
git clone <repo-url>
cd Hime

# 2. Backend — install Python dependencies
cd app/backend
uv sync

# 3. Frontend — install Node dependencies
cd ../frontend
npm install
```

On first run the backend auto-generates a random API key and writes it to
`app/backend/.env`. The key is printed to the console once — copy it if you
need it elsewhere.

---

## Running in Dev Mode

Open **two terminals**:

```bash
# Terminal 1 — backend
cd app/backend
uv run python run.py
# Starts on http://127.0.0.1:8004 (or next free port)
# Writes the chosen port to app/backend/.runtime_port

# Terminal 2 — frontend
cd app/frontend
npm run vite
# Opens http://127.0.0.1:1420
# Vite proxy forwards /api, /health, /ws to the backend port
```

Or use the Tauri dev shell (combines both):

```bash
cd app/frontend
npm run tauri dev
```

---

## Production Build (Windows installer)

```bat
cd app
build.bat
```

This runs:
1. `scripts/build_backend.py` — packages the Python backend into a single
   `.exe` via PyInstaller and places it in
   `app/frontend/src-tauri/binaries/`
2. `npm run tauri build` — compiles the Tauri app and produces an NSIS
   installer at
   `app/frontend/src-tauri/target/release/bundle/nsis/Hime_0.1.0_x64-setup.exe`

The installed app spawns the backend sidecar automatically on launch and
kills it when the window closes.

---

## Translation Pipeline

```
Input (Japanese text)
  │
  ├─ Stage 1 ── Translator A  (Gemma 27B)       ─┐
  ├─ Stage 1 ── Translator B  (DeepSeek-R1 32B) ─┤ parallel
  └─ Stage 1 ── Translator C  (Qwen2.5-32B)     ─┘
                                                  │
                        Consensus Merger  (Qwen2.5-32B)
                        synthesises the three drafts
                                                  │
                        Stage 2 Refinement  (Qwen2.5-72B)
                                                  │
                        Stage 3 Final Polish (Qwen2.5-14B)
                                                  │
                               Output (English translation)
```

All inference runs on **localhost** via OpenAI-compatible endpoints
(llama.cpp / vllm). No text ever leaves the machine.

---

## Fine-Tuning

The `scripts/train_hime.py` script trains a Qwen2.5-32B LoRA adapter using
HuggingFace Trainer. Progress can be monitored in the app's **Training
Monitor** view, which reads `trainer_state.json` files written by the
trainer and streams live updates via SSE.

```bash
cd scripts
python train_hime.py --log-file ..\app\backend\logs\training\run1.log
```

---

## Security

- The backend binds to `127.0.0.1` only — never `0.0.0.0`
- Every endpoint requires an `X-API-Key` header
- All requests are written to `app/backend/logs/audit.log`
- The `.env` file (containing the API key) is git-ignored
