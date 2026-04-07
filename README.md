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
