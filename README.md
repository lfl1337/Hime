# Hime — Japanese-to-English Light Novel Translation Suite

> **[日本語 README はこちら → README.ja.md](README.ja.md)**

Hime is a local-first desktop application for translating Japanese light novels to English using a multi-stage AI pipeline. All translation happens on your machine — no data leaves your computer.

**Current version:** v2.0.0  
**Focus:** literary translation with a yuri light novel slant (the pipeline is genre-tunable via prompts and glossaries).

---

> **Alpha Software — Pre-Production Disclaimer**
>
> Hime is personal tooling under active development. It is **not** production-hardened:
>
> - The FastAPI backend has **no authentication** between the Tauri frontend and the API server. This is intentional — the backend binds exclusively to `127.0.0.1` and is never exposed to the network. Do **not** expose port 18420 externally.
> - Training scripts (`scripts/`) spawn subprocesses and have broad filesystem access. Run them only in trusted environments.
> - No independent security audit has been performed.
> - The codebase is evolving quickly; APIs and config formats may change without notice.
>
> Use at your own risk.

---

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

### 1. Clone and configure

```bash
git clone https://github.com/lfl1337/Hime.git Hime
cd Hime
cp .env.example .env
# Edit .env to set paths for your system (or leave all commented out for auto-detection)
```

### 2. Backend (FastAPI + uv)

```bash
cd app/backend
uv sync
uv run python run.py
```

The backend binds to `127.0.0.1:18420` only and never exposes itself to the network.

### 3. Frontend (Tauri + React)

```bash
cd app/frontend
npm install
npm run tauri dev    # or: npm run vite (browser-only dev mode)
```

### 4. Training environment (Conda)

```bash
conda activate hime
# Verify the ML stack:
python -c "import unsloth, transformers, trl, peft; print('OK')"
```

### 5. Models

By default Hime expects model files under `modelle/`. Download them via `huggingface-cli`:

```bash
# Example — bge-m3 embedding model (required for RAG)
huggingface-cli download BAAI/bge-m3 --local-dir modelle/embeddings/bge-m3

# Stage 1 base models (large — see pipeline_v2.md for the full list)
huggingface-cli download Qwen/Qwen2.5-32B-Instruct --local-dir modelle/qwen2.5-32b
```

See `app/backend/app/config/pipeline_v2.py` for all model IDs and expected paths.

## First-Run: RAG Setup

The RAG vector store is **not included in the repository** — it is generated locally from your EPUB library and is specific to your translation series. On a fresh clone the store is empty; follow these steps:

**Step 1 — Import your EPUBs**

Open the app, navigate to the **Library** tab, and drag & drop your Japanese EPUB files. Hime will parse and store all chapters in the local SQLite database.

**Step 2 — Index for RAG**

Go to **Settings → RAG** and click **Re-index library**. This runs the bge-m3 embedding model over every imported paragraph and writes the results to `data/rag/` as a sqlite-vec store.

Indexing time depends on library size and GPU speed. A 10-volume series (~3000 paragraphs) takes roughly 5–10 minutes on an RTX 3080.

**Step 3 — Verify**

Once indexing completes, translate a paragraph. The pipeline log should show `[RAG] found N context chunks` at the pre-processing stage. If it shows `0 chunks`, check that `HIME_EMBEDDINGS_DIR` points to the bge-m3 model and that `HIME_RAG_DIR` is writable.

> The Hime Vault (`Hime-vault/`) is an Obsidian-based overlay on the same RAG content for human browsing. It is rebuilt by the same indexer and is also gitignored — you do not need Obsidian for the pipeline to work.

## Path Configuration

All paths are derived from environment variables. Set them in `.env`:

| Variable              | Default                       | Purpose                            |
|-----------------------|-------------------------------|------------------------------------|
| `HIME_PROJECT_ROOT`   | Auto-detected                 | Base directory                     |
| `HIME_DATA_DIR`       | `${ROOT}/data`                | EPUBs, training data, RAG store    |
| `HIME_MODELS_DIR`     | `${ROOT}/modelle`             | LoRA adapters, GGUF, Safetensors   |
| `HIME_EMBEDDINGS_DIR` | `${ROOT}/modelle/embeddings`  | bge-m3 embedding model for RAG     |
| `HIME_LOGS_DIR`       | `${ROOT}/app/backend/logs`    | Backend, training, and audit logs  |
| `HIME_DRY_RUN`        | unset                         | Set to `1` to run pipeline without loading real models (test mode) |

## Pipeline Configuration

The translation pipeline is configured via `app/backend/app/config/pipeline_v2.py` and the prompt templates in `app/backend/app/prompts/`. Each stage has its own prompt file that you can edit without restarting the backend — prompts are loaded on-demand.

For training, see `scripts/training/configs/`. The Qwen2.5-32B LoRA is the current anchor adapter. New adapters are trained via `scripts/train_generic.py` with model-specific config files.

## Testing

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
- Append-only JSON-Lines audit log (`logs/audit.log`)
- Rate-limiting on translation and pipeline endpoints
- No external API calls during translation — everything runs locally
- The OpenAI SDK is used **only** as a client for local inference servers (llama.cpp, vllm, Ollama on `127.0.0.1`), never against external APIs

> **Note on API authentication:** There is deliberately no auth token between the Tauri shell and the FastAPI backend. Both run on the same machine, and the backend refuses connections from any non-loopback address. If you run the backend standalone (without Tauri), be aware that any process on your machine can reach it.

## Contributing

This is personal tooling, but issues and PRs are welcome. A few notes:

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) — `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`
- Branch directly to `main` for small fixes; use a feature branch for anything touching the pipeline or training stack
- Run `uv run pytest` and `npm run test` before opening a PR
- Do not commit `.env`, model weights, or database files — the `.gitignore` covers these, but double-check before pushing

## Known Limitations

- First-run model downloads are large (~17 GB for Qwen3-30B-A3B + bge-m3, more for the full v2 model set)
- Translating one ~300-page volume takes roughly 20–30 hours on an RTX 5090, depending on retry-loop activity
- The current Qwen2.5-32B LoRA shows mild overfitting tendencies on the eval set; curriculum learning is implemented but may need tuning per dataset
- The reader panel adds ~7 hours to the per-volume runtime; reducing the number of personas or shortening their output is the easiest optimization

## License

[To be determined]
