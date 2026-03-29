# Hime

Local-first Japanese-to-English translation studio for light novels. Everything runs on your machine — no cloud API, no data leaves your computer.

Translation is performed by local Qwen 2.5 and Gemma models served via llama.cpp, running a multi-stage pipeline that produces polished English output from any Japanese source text.

![version](https://img.shields.io/badge/version-1.1.0-blue) ![platform](https://img.shields.io/badge/platform-Windows-lightgrey) ![license](https://img.shields.io/badge/license-private-lightgrey)

---

## Views

| View | Description |
|------|-------------|
| Translator (翻) | Paste Japanese text, stream a full pipeline translation with live token output |
| Comparison (比) | Compare all three Stage-1 models side by side and watch the consensus form in real time |
| Editor (編) | Review and refine completed translations paragraph by paragraph |
| Training Monitor (訓) | Track LoRA fine-tuning runs, live loss curves, checkpoint progress, and log output |

---

## Translation Pipeline

Three models translate in parallel. Their outputs are merged by a consensus model, then refined twice.

```
Input (Japanese text)
  │
  ├── Stage 1A  Gemma 3 27B         ─┐
  ├── Stage 1B  DeepSeek-R1 32B     ─┤  parallel
  └── Stage 1C  Qwen 2.5 32B        ─┘
                                     │
               Consensus  Qwen 2.5 32B    synthesises the three drafts
                                     │
               Stage 2    Qwen 2.5 72B    refinement pass
                                     │
               Stage 3    Qwen 2.5 14B    final polish
                                     │
                                Output (English translation)
```

All models run locally via OpenAI-compatible endpoints (llama.cpp / vllm, ports 8001–8005). No text ever leaves the machine.

---

## Architecture

```
User
  └── Tauri desktop app  (React + TypeScript, Vite)
        └── HTTP / WebSocket  →  127.0.0.1 only
              └── FastAPI backend  (Python 3.11, uv)
                    ├── SQLite           source texts, translations, per-stage outputs
                    ├── Pipeline runner  async, queue-based, WebSocket streaming
                    ├── EPUB ingest      watch folder, chapter extraction
                    ├── Training monitor SSE, loss history, checkpoint tracking
                    └── Inference servers  llama.cpp / vllm, ports 8001–8005
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| [uv](https://docs.astral.sh/uv/) | >= 0.5 | Python package manager |
| Node.js | >= 20 | Frontend build |
| Rust / Cargo | stable | Tauri compilation |
| [Tauri CLI](https://tauri.app/start/prerequisites/) | v2 | Desktop shell |
| llama.cpp or vllm | — | Local inference servers |

---

## Setup

```bash
# Clone
git clone https://github.com/lfl1337/Hime.git
cd Hime

# Backend — install Python dependencies
cd app/backend
uv sync

# Frontend — install Node dependencies
cd ../frontend
npm install
```

---

## Running

**Development mode — two terminals:**

```bash
# Terminal 1 — backend
cd app/backend
uv run python run.py
# Binds to 127.0.0.1, writes chosen port to .runtime_port

# Terminal 2 — frontend
cd app/frontend
npm run vite
# Opens http://127.0.0.1:1420
# Vite proxy forwards /api, /health, /ws to the backend port
```

Or launch both together via Tauri:

```bash
cd app/frontend
npm run tauri dev
```

**Production build (Windows installer):**

```bat
cd app
build.bat
```

Packages the Python backend with PyInstaller, then compiles the Tauri app. The installer is placed in `app/frontend/src-tauri/target/release/bundle/nsis/`.

---

## Fine-Tuning

`scripts/train_hime.py` trains a Qwen 2.5 32B LoRA adapter using HuggingFace Trainer. Start a run and switch to the **Training Monitor** view to follow progress live — loss curves, step counts, checkpoint list, and log tail.

```bash
python scripts/train_hime.py --log-file app/backend/logs/training/run1.log
```

---

## Project Layout

```
Hime/
├── app/
│   ├── backend/                FastAPI server (Python, uv)
│   │   ├── app/
│   │   │   ├── routers/        texts, translations, training, compare, models
│   │   │   ├── pipeline/       multi-stage runner and prompt templates
│   │   │   ├── services/       training monitor, EPUB ingest, hardware stats
│   │   │   └── websocket/      streaming endpoint (/ws/translate/{job_id})
│   │   └── run.py              entry point — binds to 127.0.0.1 only
│   ├── frontend/               Tauri + React (TypeScript, Vite)
│   │   ├── src/
│   │   │   ├── api/            typed HTTP and WebSocket client
│   │   │   ├── components/     Sidebar, comparison panels, training cards
│   │   │   ├── hooks/          useModelPolling, …
│   │   │   └── views/          Translator, Comparison, Editor, TrainingMonitor
│   │   └── src-tauri/          Rust shell (sidecar spawn, window management)
│   └── build.bat               one-command Windows production build
├── scripts/
│   ├── train_hime.py           LoRA fine-tuning (HuggingFace Trainer)
│   ├── build_backend.py        PyInstaller packaging helper
│   └── bump_version.py         semver bump, tag, and push
├── data/
│   ├── raw_jp/                 Japanese source texts
│   └── raw_en/                 English reference texts
└── modelle/
    ├── lmstudio-community/     GGUF quantised models (not in git)
    └── lora/                   LoRA adapters and checkpoints
```

---

## Security

- The backend binds to `127.0.0.1` exclusively — never exposed on the local network
- All user-supplied text is sanitized for prompt-injection patterns before reaching any model
- Every request is written to `app/backend/logs/audit.log`
- `.env` is git-ignored
