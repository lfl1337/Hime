# Hime — Japanese-to-English Light Novel Translation Suite

Hime is a local-first desktop application for translating Japanese light novels to English using a multi-stage AI pipeline. All translation happens on your machine — no data leaves your computer.

**Current version:** v2.0.0
**Focus:** literary translation with a yuri light novel slant (the pipeline is genre-tunable via prompts and glossaries).

## Features

- **4-stage translation pipeline** — 4 models draft in parallel + a deterministic lexicon anchor, then merge → polish → reader-panel review
- **15-persona Reader Panel** — small models read the final output as virtual beta-readers and flag issues, with a two-path retry loop (light fix-pass / full retry)
- **RAG over previous volumes** — sqlite-vec + bge-m3 embeddings keep terminology, names, and honorifics consistent across a series
- **EPUB import / export** — drag & drop Japanese EPUBs, translate chapter by chapter, export as English EPUB via ebooklib
- **Live streaming** — watch each stage stream tokens in real-time via WebSocket
- **Training monitor** — fine-tune LoRA adapters locally with built-in loss charts, hardware monitoring, and curriculum learning
- **Data registry** — central registry of training data sources, ready for the flywheel loop (reviewed translations → next training run)
- **Offline-first** — EPUB library, translation history, glossary, and RAG store all work without models running

## Architecture

```
Pre-processing
  ├── EPUB extraction
  ├── MeCab segmentation
  └── RAG context query (sqlite-vec + bge-m3)

Stage 1 — Parallel Drafts (4 models + 1 anchor)
  ├── Qwen2.5-32B               (LoRA, anchor model — strongest JP comprehension)
  ├── TranslateGemma-12B        (LoRA, MT-specialized)
  ├── Qwen3.5-9B                (LoRA, fast modern Qwen)
  ├── llm-jp-3-7.2b-instruct3   (JP-first diversity draft, no training)
  └── JMdict / MeCab            (algorithmic dictionary anchor — authoritative for vocabulary)

Stage 2 — Consensus Merger
  └── TranslateGemma-27B        (merges all 5 inputs, vetoes hallucinations against JMdict)

Stage 3 — Polish
  └── Qwen3-30B-A3B MoE         (light editing, style smoothing — zero-shot)

Stage 4 — Reader Panel + Aggregator
  ├── 15× Qwen3.5-2B            (persona-based readers via system prompts)
  └── LFM2-24B-A2B              (aggregator: emits okay / fix_pass / full_retry verdict)

Post-processing
  └── EPUB export via ebooklib
```

All Stage 1 models run on a single GPU with sequential loading and aggressive VRAM management. The pipeline is designed for an RTX 5090 (32 GB VRAM) but will fall back to CPU offloading on smaller cards.

## Prerequisites

- Windows 10/11 (primary target), Linux secondary
- NVIDIA GPU with 24+ GB VRAM recommended (32 GB for parallel Stage 1)
- [Conda](https://docs.conda.io/) with a `hime` environment for training/ML
- [`uv`](https://github.com/astral-sh/uv) for the backend Python environment
- Node.js 22+ and npm
- Rust toolchain (for Tauri)
- (Optional) Ollama, llama.cpp, or vllm for GGUF inference

## Setup

1. **Clone and configure paths:**

```bash
git clone <repo-url> Hime
cd Hime
cp .env.example .env
# Edit .env to set paths for your system (or leave defaults)
```

2. **Backend (FastAPI + uv):**

```bash
cd app/backend
uv sync
uv run python run.py
```

The backend binds to `127.0.0.1` only and never exposes itself to the network.

3. **Frontend (Tauri + React):**

```bash
cd app/frontend
npm install
npm run tauri dev    # or: npm run vite (browser-only dev mode)
```

4. **Training environment (Conda):**

```bash
conda activate hime
# Verify the ML stack:
python -c "import unsloth, transformers, trl, peft; print('OK')"
```

5. **Models** — by default Hime expects model files under `modelle/`. Use `huggingface-cli download` or your preferred method. See `pipeline_v2.md` for the full model list with HuggingFace IDs.

## Path Configuration

All paths are derived from environment variables. Set them in `.env`:

| Variable             | Default                       | Purpose                            |
|----------------------|-------------------------------|------------------------------------|
| `HIME_PROJECT_ROOT`  | Auto-detected                 | Base directory                     |
| `HIME_DATA_DIR`      | `${ROOT}/data`                | EPUBs, training data, RAG store    |
| `HIME_MODELS_DIR`    | `${ROOT}/modelle`             | LoRA adapters, GGUF, Safetensors   |
| `HIME_EMBEDDINGS_DIR`| `${ROOT}/modelle/embeddings`  | bge-m3 embedding model for RAG     |
| `HIME_LOGS_DIR`      | `${ROOT}/app/backend/logs`    | Backend, training, and audit logs  |
| `HIME_DRY_RUN`       | unset                         | Set to `1` to run pipeline without loading real models (test mode) |

## Pipeline Configuration

The translation pipeline is configured via `pipeline_v2.md` and the prompt templates in `app/backend/app/prompts/`. Each stage has its own prompt file that you can edit without restarting the backend — prompts are loaded on-demand.

For training, see `training_config.json`. The Qwen2.5-32B LoRA is the current anchor adapter (best checkpoint at step 12400, eval_loss 0.95). New v2 adapters (TranslateGemma-12B, Qwen3.5-9B) are trained via `scripts/train_generic.py` with model-specific configs under `scripts/training/configs/`.

## Testing

Hime has a full test suite covering both backend and frontend:

```bash
# Backend (pytest + coverage)
cd app/backend
uv run pytest --cov=app

# Frontend (vitest)
cd app/frontend
npm run test

# End-to-end pipeline dry-run (no models loaded)
HIME_DRY_RUN=1 uv run python -m app.pipeline.runner_v2 --book-id 1 --segment-limit 3
```

## Security

- Backend binds **only** to `127.0.0.1` — no network exposure
- Input sanitization with 11+ prompt-injection patterns
- Path-traversal protection on all EPUB import paths
- Append-only JSON-Lines audit log
- Rate-limiting on translation and pipeline endpoints
- No external API calls during translation — everything runs locally
- The OpenAI SDK is used **only** as a client for local inference servers (llama.cpp, vllm, Ollama on `127.0.0.1`), never against external APIs

## Known Limitations

- First-run model downloads are large (~17 GB for Qwen3-30B-A3B + bge-m3, more for the full v2 model set)
- Translating one ~300-page volume takes roughly 20–30 hours on an RTX 5090, depending on retry-loop activity
- The current Qwen2.5-32B LoRA shows mild overfitting tendencies on the eval set; curriculum learning is implemented but may need tuning per dataset
- The reader panel adds ~7 hours to the per-volume runtime; reducing the number of personas or shortening their output is the easiest optimization

## License

[To be determined]
