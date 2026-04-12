# Pipeline v2 WS-B — Stage 1 Local Inference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Stage 1 of the Hime translation pipeline with a 5-adapter ensemble (4 local Transformers/Unsloth models + 1 existing Ollama endpoint) wrapped in a clean `stage1/` package, with graceful VRAM-constrained fallback.

**Architecture:** A new `app/backend/app/pipeline/stage1/` package exposes a single async entry point `run_stage1(segment, rag_context, glossary_context) -> Stage1Drafts`. Adapters 1A (Qwen2.5-32B) talks to the existing Ollama endpoint via `inference.complete()`; adapters 1B–1D load models locally via Unsloth; adapter 1E wraps the existing `LexiconService`. All five run concurrently via `asyncio.gather(return_exceptions=True)`; on CUDA OOM, local adapters 1B–1D are retried sequentially while 1A stays parallel. The existing `pipeline/runner.py` is updated last to call `run_stage1()` instead of the old three-model Ollama fan-out.

**Tech Stack:** Python 3.11+, FastAPI backend, `unsloth` (PyPI + extras), `transformers>=5.0.0`, `torch` (CUDA), pytest + pytest-asyncio (asyncio_mode = "auto"), `unittest.mock.patch`.

---

## Scope Note

This plan covers **WS-B Stage 1 only**: the five-adapter ensemble package and its wiring into the existing runner. Consensus, Stage 2, and Stage 3 are unchanged. The new `settings` fields added here are the only config changes.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `app/backend/pyproject.toml` | Add `transformers>=5.0.0` and `unsloth` deps |
| Modify | `app/backend/app/config.py` | Add 3 new local model path settings (1B/1C/1D) |
| Create | `app/backend/app/pipeline/stage1/__init__.py` | Public API: exports `run_stage1`, `Stage1Drafts` |
| Create | `app/backend/app/pipeline/stage1/_types.py` | `Stage1Drafts` dataclass |
| Create | `app/backend/app/pipeline/stage1/adapter_qwen32b.py` | 1A — Ollama passthrough via `inference.complete()` |
| Create | `app/backend/app/pipeline/stage1/adapter_translategemma.py` | 1B — TranslateGemma-12B via Unsloth |
| Create | `app/backend/app/pipeline/stage1/adapter_qwen35_9b.py` | 1C — Qwen3.5-9B via Unsloth, non-thinking |
| Create | `app/backend/app/pipeline/stage1/adapter_gemma4.py` | 1D — Gemma4 E4B GGUF via Unsloth |
| Create | `app/backend/app/pipeline/stage1/adapter_jmdict.py` | 1E — thin wrapper around `LexiconService` |
| Create | `app/backend/app/pipeline/stage1/runner.py` | `run_stage1()` orchestrator with OOM fallback |
| Create | `app/backend/tests/test_stage1_v2.py` | All unit + integration + degradation tests |
| Modify | `app/backend/app/pipeline/runner.py` | Replace old 3-model gather with `run_stage1()` call |

---

## Task 1: Add Dependencies to pyproject.toml

**Files:**
- Modify: `app/backend/pyproject.toml`

> **Note on unsloth:** `unsloth` must be installed separately with the right CUDA extras. Add it to pyproject.toml for declaration purposes, but document the manual install command. pip/uv will install a CPU-only placeholder; real GPU inference needs:
> ```
> pip install "unsloth[cu124-torch260]" --find-links https://download.pytorch.org/whl/torch_stable.html
> ```
> The exact extra tag depends on your CUDA version — see https://github.com/unslothai/unsloth.

- [ ] **Step 1.1: Add transformers and unsloth to `[project.dependencies]`**

Open `app/backend/pyproject.toml`. In the `dependencies` list, add these two lines after `"sentence-transformers>=3.0.0"`:

```toml
[project]
name = "hime-backend"
version = "0.1.0"
description = "Hime – local-first Japanese-to-English light novel translation backend"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.20.0",
    "python-dotenv>=1.0.0",
    "slowapi>=0.1.9",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.2.0",
    "openai>=1.30.0",
    "ebooklib>=0.20",
    "beautifulsoup4>=4.14.3",
    "lxml>=6.0.2",
    "psutil>=7.2.2",
    "nvidia-ml-py>=11.5.0",
    "mecab-python3>=1.0.9",
    "unidic-lite>=1.0.8",
    "jamdict>=0.1a11",
    "jamdict-data>=1.5",
    "sqlite-vec>=0.1.6",
    "sentence-transformers>=3.0.0",
    "transformers>=5.0.0",
    "unsloth",
    "mcp>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
    "ruff>=0.4.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[dependency-groups]
dev = [
    "pyinstaller>=6.19.0",
    "pytest>=9.0.2",
    "pytest-asyncio>=1.3.0",
]
```

- [ ] **Step 1.2: Commit**

```bash
git add app/backend/pyproject.toml
git commit -m "chore(deps): add transformers>=5.0.0 and unsloth to pyproject.toml"
```

---

## Task 2: Add Local Model Path Settings to config.py

**Files:**
- Modify: `app/backend/app/config.py`

The three local adapters (1B, 1C, 1D) need configurable model paths. We express them as `str` settings (matching existing convention) and resolve them relative to `MODELS_DIR` at default.

- [ ] **Step 2.1: Add three new settings fields**

In `app/backend/app/config.py`, add the following block immediately after the `hime_qwen32b_model` line (inside the `Settings` class):

```python
    # Pipeline Stage 1 v2 — local Unsloth model paths (relative to MODELS_DIR by default)
    # Override via .env: HIME_TRANSLATEGEMMA_PATH=/absolute/path/to/model
    hime_translategemma_path: str = ""   # resolved at runtime → MODELS_DIR/translategemma-12b
    hime_qwen35_9b_path: str = ""        # resolved at runtime → MODELS_DIR/qwen3.5-9b
    hime_gemma4_path: str = ""           # resolved at runtime → MODELS_DIR/gemma4-e4b
```

The full updated `Settings` class (show only the Stage 1 section for brevity — full file remains intact):

```python
    # Pipeline Stage 1 — three parallel translators (v1 Ollama)
    hime_gemma_url: str = "http://127.0.0.1:8001/v1"
    hime_gemma_model: str = "hime-gemma"
    hime_deepseek_url: str = "http://127.0.0.1:8002/v1"
    hime_deepseek_model: str = "hime-deepseek"
    hime_qwen32b_url: str = "http://127.0.0.1:8003/v1"
    hime_qwen32b_model: str = "hime-qwen32b"

    # Pipeline Stage 1 v2 — local Unsloth model paths (relative to MODELS_DIR by default)
    # Override via .env: HIME_TRANSLATEGEMMA_PATH=/absolute/path/to/model
    hime_translategemma_path: str = ""   # resolved at runtime → MODELS_DIR/translategemma-12b
    hime_qwen35_9b_path: str = ""        # resolved at runtime → MODELS_DIR/qwen3.5-9b
    hime_gemma4_path: str = ""           # resolved at runtime → MODELS_DIR/gemma4-e4b
```

- [ ] **Step 2.2: Commit**

```bash
git add app/backend/app/config.py
git commit -m "feat(config): add local model path settings for Stage 1 v2 adapters"
```

---

## Task 3: Create `_types.py` — Stage1Drafts Dataclass

**Files:**
- Create: `app/backend/app/pipeline/stage1/_types.py`
- Test: `app/backend/tests/test_stage1_v2.py`

- [ ] **Step 3.1: Write the failing test**

Create `app/backend/tests/test_stage1_v2.py`:

```python
"""Tests for Stage 1 v2 — local Unsloth inference package."""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Task 3: _types.py
# ---------------------------------------------------------------------------

class TestStage1Drafts:
    def test_dataclass_fields_exist(self):
        from app.pipeline.stage1._types import Stage1Drafts
        d = Stage1Drafts(
            source_jp="猫が走る。",
            qwen32b="The cat runs.",
            translategemma12b="A cat is running.",
            qwen35_9b="Cats run.",
            gemma4_e4b="The cat ran.",
            jmdict="cat run .",
        )
        assert d.source_jp == "猫が走る。"
        assert d.qwen32b == "The cat runs."
        assert d.translategemma12b == "A cat is running."
        assert d.qwen35_9b == "Cats run."
        assert d.gemma4_e4b == "The cat ran."
        assert d.jmdict == "cat run ."

    def test_optional_fields_default_none(self):
        from app.pipeline.stage1._types import Stage1Drafts
        d = Stage1Drafts(source_jp="テスト", jmdict="test")
        assert d.qwen32b is None
        assert d.translategemma12b is None
        assert d.qwen35_9b is None
        assert d.gemma4_e4b is None

    def test_jmdict_is_always_str(self):
        from app.pipeline.stage1._types import Stage1Drafts
        d = Stage1Drafts(source_jp="x", jmdict="")
        assert isinstance(d.jmdict, str)
```

- [ ] **Step 3.2: Run test to verify it fails**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestStage1Drafts -v
```

Expected: `ModuleNotFoundError: No module named 'app.pipeline.stage1'`

- [ ] **Step 3.3: Create the package skeleton and `_types.py`**

Create directory `app/backend/app/pipeline/stage1/` (it does not exist yet).

Create `app/backend/app/pipeline/stage1/__init__.py` (empty for now — filled in Task 8):

```python
# stage1 package — public API defined in runner.py, exported here in Task 8
```

Create `app/backend/app/pipeline/stage1/_types.py`:

```python
"""
Shared dataclass for Stage 1 v2 pipeline outputs.

All adapter fields are Optional — an adapter that fails or is unavailable
sets its field to None. `jmdict` is the exception: LexiconService always
succeeds (it may return an empty string for unknown input, but never raises).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Stage1Drafts:
    source_jp: str
    jmdict: str
    qwen32b: str | None = field(default=None)           # 1A — Ollama Qwen2.5-32B LoRA
    translategemma12b: str | None = field(default=None) # 1B — TranslateGemma-12B (Unsloth)
    qwen35_9b: str | None = field(default=None)         # 1C — Qwen3.5-9B non-thinking (Unsloth)
    gemma4_e4b: str | None = field(default=None)        # 1D — Gemma4 E4B GGUF (Unsloth)
```

- [ ] **Step 3.4: Run test to verify it passes**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestStage1Drafts -v
```

Expected: 3 PASSED

- [ ] **Step 3.5: Commit**

```bash
git add app/backend/app/pipeline/stage1/__init__.py \
        app/backend/app/pipeline/stage1/_types.py \
        app/backend/tests/test_stage1_v2.py
git commit -m "feat(stage1): add Stage1Drafts dataclass and package skeleton"
```

---

## Task 4: Adapter 1A — `adapter_qwen32b.py` (Ollama passthrough)

**Files:**
- Create: `app/backend/app/pipeline/stage1/adapter_qwen32b.py`
- Modify: `app/backend/tests/test_stage1_v2.py`

The Qwen2.5-32B LoRA runs via Ollama on port 8003 — the existing infrastructure. This adapter reuses `app.inference.complete()` with the settings already defined in `config.py`.

- [ ] **Step 4.1: Write the failing test**

Append to `app/backend/tests/test_stage1_v2.py`:

```python
# ---------------------------------------------------------------------------
# Task 4: adapter_qwen32b.py
# ---------------------------------------------------------------------------

class TestAdapterQwen32b:
    @pytest.mark.asyncio
    async def test_returns_translation_string(self, monkeypatch):
        """Adapter calls inference.complete() and returns its result."""
        from app.pipeline.stage1 import adapter_qwen32b

        async def fake_complete(url, model, messages, **kwargs):
            return "The cat runs quickly."

        monkeypatch.setattr("app.pipeline.stage1.adapter_qwen32b.complete", fake_complete)

        result = await adapter_qwen32b.translate("猫が速く走る。", rag_context="", glossary_context="")
        assert result == "The cat runs quickly."

    @pytest.mark.asyncio
    async def test_passes_source_as_user_message(self, monkeypatch):
        """The source JP text must appear as the user message."""
        from app.pipeline.stage1 import adapter_qwen32b

        captured: list[dict] = []

        async def capturing_complete(url, model, messages, **kwargs):
            captured.extend(messages)
            return "ok"

        monkeypatch.setattr("app.pipeline.stage1.adapter_qwen32b.complete", capturing_complete)
        await adapter_qwen32b.translate("テスト文章", rag_context="", glossary_context="")

        user_msg = next(m for m in captured if m["role"] == "user")
        assert "テスト文章" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_string(self, monkeypatch):
        from app.pipeline.stage1 import adapter_qwen32b

        async def fake_complete(url, model, messages, **kwargs):
            return ""

        monkeypatch.setattr("app.pipeline.stage1.adapter_qwen32b.complete", fake_complete)
        result = await adapter_qwen32b.translate("x", rag_context="", glossary_context="")
        assert result == ""
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterQwen32b -v
```

Expected: `ImportError` or `AttributeError` — `adapter_qwen32b` doesn't exist yet.

- [ ] **Step 4.3: Implement `adapter_qwen32b.py`**

Create `app/backend/app/pipeline/stage1/adapter_qwen32b.py`:

```python
"""
Stage 1A — Qwen2.5-32B LoRA via Ollama (existing infrastructure).

Reuses app.inference.complete() against the hime_qwen32b endpoint already
configured in settings. This is identical to what pipeline/runner.py did for
"qwen32b" in the old 3-model gather, but extracted as a standalone function
so the stage1 package can call it independently.
"""
from __future__ import annotations

from ...config import settings
from ...inference import complete
from ...pipeline.prompts import stage1_messages


async def translate(
    source_jp: str,
    *,
    rag_context: str = "",
    glossary_context: str = "",
    notes: str = "",
) -> str:
    """
    Call the Qwen2.5-32B LoRA endpoint via Ollama and return the translation.

    Raises on network/inference error — caller uses return_exceptions=True.
    """
    messages = stage1_messages(
        source_jp,
        notes=notes,
        glossary=glossary_context,
        rag_context=rag_context,
    )
    return await complete(
        settings.hime_qwen32b_url,
        settings.hime_qwen32b_model,
        messages,
    )
```

- [ ] **Step 4.4: Run test to verify it passes**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterQwen32b -v
```

Expected: 3 PASSED

- [ ] **Step 4.5: Commit**

```bash
git add app/backend/app/pipeline/stage1/adapter_qwen32b.py \
        app/backend/tests/test_stage1_v2.py
git commit -m "feat(stage1): add adapter_qwen32b (1A — Ollama passthrough)"
```

---

## Task 5: Adapter 1B — `adapter_translategemma.py` (Unsloth local)

**Files:**
- Create: `app/backend/app/pipeline/stage1/adapter_translategemma.py`
- Modify: `app/backend/tests/test_stage1_v2.py`

TranslateGemma-12B is a fine-tuned model with its own chat template. We load it lazily (once, on first call) via a module-level cached instance. Model path resolves `settings.hime_translategemma_path` → `MODELS_DIR/translategemma-12b` as default.

- [ ] **Step 5.1: Write the failing test**

Append to `app/backend/tests/test_stage1_v2.py`:

```python
# ---------------------------------------------------------------------------
# Task 5: adapter_translategemma.py
# ---------------------------------------------------------------------------

class TestAdapterTranslateGemma:
    @pytest.mark.asyncio
    async def test_returns_string(self, monkeypatch):
        """Adapter returns a non-empty string when model generates output."""
        from app.pipeline.stage1 import adapter_translategemma
        from unittest.mock import MagicMock, patch

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()

        # Tokenizer encode → tensor-like object
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.apply_chat_template.return_value = "formatted prompt"
        fake_tokenizer.return_value = fake_inputs
        fake_tokenizer.decode.return_value = "The cat runs."

        # model.generate → token ids
        fake_model.generate.return_value = [[1, 2, 3]]

        with patch(
            "app.pipeline.stage1.adapter_translategemma.FastLanguageModel.from_pretrained",
            return_value=(fake_model, fake_tokenizer),
        ):
            # Reset cached instance so patch takes effect
            adapter_translategemma._MODEL_CACHE.clear()
            result = await adapter_translategemma.translate(
                "猫が走る。", rag_context="", glossary_context=""
            )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_model_loaded_once(self, monkeypatch):
        """from_pretrained is called only once across multiple translate() calls."""
        from app.pipeline.stage1 import adapter_translategemma
        from unittest.mock import MagicMock, patch, AsyncMock

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "translation"
        fake_model.generate.return_value = [[1, 2, 3]]

        call_count = 0

        def counting_from_pretrained(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return fake_model, fake_tokenizer

        adapter_translategemma._MODEL_CACHE.clear()

        with patch(
            "app.pipeline.stage1.adapter_translategemma.FastLanguageModel.from_pretrained",
            side_effect=counting_from_pretrained,
        ):
            await adapter_translategemma.translate("A", rag_context="", glossary_context="")
            await adapter_translategemma.translate("B", rag_context="", glossary_context="")

        assert call_count == 1
```

- [ ] **Step 5.2: Run test to verify it fails**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterTranslateGemma -v
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 5.3: Implement `adapter_translategemma.py`**

Create `app/backend/app/pipeline/stage1/adapter_translategemma.py`:

```python
"""
Stage 1B — TranslateGemma-12B via Unsloth local inference.

Model is loaded lazily on first call and cached for the process lifetime.
TranslateGemma has its own chat template; we use apply_chat_template() as
the model card recommends rather than building messages manually.

VRAM footprint: ~8GB at 4-bit quantization.

Model path resolution (in priority order):
  1. settings.hime_translategemma_path  (if non-empty)
  2. MODELS_DIR / "translategemma-12b"  (default)
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from ...config import settings
from ...core.paths import MODELS_DIR

_log = logging.getLogger(__name__)

# Module-level cache — keys: "model", "tokenizer"
# Using a dict so tests can call .clear() to reset state between test runs.
_MODEL_CACHE: dict[str, object] = {}


def _model_path() -> str:
    if settings.hime_translategemma_path:
        return settings.hime_translategemma_path
    return str(MODELS_DIR / "translategemma-12b")


def _load_model():
    """Load TranslateGemma-12B into _MODEL_CACHE (idempotent)."""
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]

    from unsloth import FastLanguageModel  # noqa: PLC0415 — deferred import (heavy)

    path = _model_path()
    _log.info("Loading TranslateGemma-12B from %s", path)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=path,
        max_seq_length=4096,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    _MODEL_CACHE["model"] = model
    _MODEL_CACHE["tokenizer"] = tokenizer
    _log.info("TranslateGemma-12B loaded.")
    return model, tokenizer


def _run_inference(source_jp: str, rag_context: str, glossary_context: str) -> str:
    """Blocking inference call — run in executor to avoid blocking the event loop."""
    model, tokenizer = _load_model()

    # Build the conversation in the format TranslateGemma expects.
    system_content = (
        "You are an expert Japanese-to-English light novel translator. "
        "Translate the text accurately, preserving style, tone, and honorifics."
    )
    if glossary_context:
        system_content += f"\n\nGlossary:\n{glossary_context}"
    if rag_context:
        system_content += f"\n\nContext from previous passages:\n{rag_context}"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": source_jp},
    ]

    # TranslateGemma uses its own template — do NOT build raw prompt manually.
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    output_ids = model.generate(
        **inputs,
        max_new_tokens=1024,
        temperature=0.3,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
    )
    # Decode only newly generated tokens (skip the prompt)
    new_tokens = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


async def translate(
    source_jp: str,
    *,
    rag_context: str = "",
    glossary_context: str = "",
) -> str:
    """
    Translate source_jp with TranslateGemma-12B.

    Runs blocking model inference in a thread executor so FastAPI's async
    event loop is not blocked. Raises on model load failure or CUDA OOM —
    caller uses return_exceptions=True.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _run_inference, source_jp, rag_context, glossary_context
    )
```

- [ ] **Step 5.4: Run test to verify it passes**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterTranslateGemma -v
```

Expected: 2 PASSED

- [ ] **Step 5.5: Commit**

```bash
git add app/backend/app/pipeline/stage1/adapter_translategemma.py \
        app/backend/tests/test_stage1_v2.py
git commit -m "feat(stage1): add adapter_translategemma (1B — Unsloth local inference)"
```

---

## Task 6: Adapter 1C — `adapter_qwen35_9b.py` (Unsloth, non-thinking)

**Files:**
- Create: `app/backend/app/pipeline/stage1/adapter_qwen35_9b.py`
- Modify: `app/backend/tests/test_stage1_v2.py`

Qwen3.5-9B supports a "thinking" mode that adds `<think>...</think>` blocks. We explicitly disable it via `enable_thinking=False` in the generation config to get clean output without reasoning traces.

- [ ] **Step 6.1: Write the failing test**

Append to `app/backend/tests/test_stage1_v2.py`:

```python
# ---------------------------------------------------------------------------
# Task 6: adapter_qwen35_9b.py
# ---------------------------------------------------------------------------

class TestAdapterQwen35_9b:
    @pytest.mark.asyncio
    async def test_returns_string(self, monkeypatch):
        from app.pipeline.stage1 import adapter_qwen35_9b
        from unittest.mock import MagicMock, patch

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "She walked home."
        fake_model.generate.return_value = [[1, 2, 3]]
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.return_value = fake_inputs

        with patch(
            "app.pipeline.stage1.adapter_qwen35_9b.FastLanguageModel.from_pretrained",
            return_value=(fake_model, fake_tokenizer),
        ):
            adapter_qwen35_9b._MODEL_CACHE.clear()
            result = await adapter_qwen35_9b.translate(
                "彼女は家に帰った。", rag_context="", glossary_context=""
            )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_non_thinking_flag_passed(self, monkeypatch):
        """generate() must be called with enable_thinking=False."""
        from app.pipeline.stage1 import adapter_qwen35_9b
        from unittest.mock import MagicMock, patch

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "result"
        fake_model.generate.return_value = [[1, 2, 3]]
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.return_value = fake_inputs

        with patch(
            "app.pipeline.stage1.adapter_qwen35_9b.FastLanguageModel.from_pretrained",
            return_value=(fake_model, fake_tokenizer),
        ):
            adapter_qwen35_9b._MODEL_CACHE.clear()
            await adapter_qwen35_9b.translate("x", rag_context="", glossary_context="")

        call_kwargs = fake_model.generate.call_args.kwargs
        assert call_kwargs.get("enable_thinking") is False
```

- [ ] **Step 6.2: Run test to verify it fails**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterQwen35_9b -v
```

Expected: `ImportError`

- [ ] **Step 6.3: Implement `adapter_qwen35_9b.py`**

Create `app/backend/app/pipeline/stage1/adapter_qwen35_9b.py`:

```python
"""
Stage 1C — Qwen3.5-9B via Unsloth, Non-Thinking mode.

Non-Thinking mode is engaged by passing enable_thinking=False to generate().
This suppresses the <think>...</think> reasoning trace and returns a clean
translation directly. Without this flag, output would include long reasoning
blocks that would contaminate the consensus merger.

VRAM footprint: ~6GB at 4-bit quantization.

Model path resolution (in priority order):
  1. settings.hime_qwen35_9b_path  (if non-empty)
  2. MODELS_DIR / "qwen3.5-9b"     (default)
"""
from __future__ import annotations

import asyncio
import logging

from ...config import settings
from ...core.paths import MODELS_DIR
from ...pipeline.prompts import stage1_messages

_log = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, object] = {}


def _model_path() -> str:
    if settings.hime_qwen35_9b_path:
        return settings.hime_qwen35_9b_path
    return str(MODELS_DIR / "qwen3.5-9b")


def _load_model():
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]

    from unsloth import FastLanguageModel  # noqa: PLC0415

    path = _model_path()
    _log.info("Loading Qwen3.5-9B from %s", path)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=path,
        max_seq_length=4096,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    _MODEL_CACHE["model"] = model
    _MODEL_CACHE["tokenizer"] = tokenizer
    _log.info("Qwen3.5-9B loaded.")
    return model, tokenizer


def _run_inference(source_jp: str, rag_context: str, glossary_context: str) -> str:
    model, tokenizer = _load_model()

    messages = stage1_messages(source_jp, rag_context=rag_context, glossary=glossary_context)
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    output_ids = model.generate(
        **inputs,
        max_new_tokens=1024,
        temperature=0.3,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
        enable_thinking=False,  # suppress <think>...</think> blocks
    )
    new_tokens = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


async def translate(
    source_jp: str,
    *,
    rag_context: str = "",
    glossary_context: str = "",
) -> str:
    """
    Translate source_jp with Qwen3.5-9B (Non-Thinking mode).

    Raises on CUDA OOM or model load failure — caller uses return_exceptions=True.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _run_inference, source_jp, rag_context, glossary_context
    )
```

- [ ] **Step 6.4: Run test to verify it passes**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterQwen35_9b -v
```

Expected: 2 PASSED

- [ ] **Step 6.5: Commit**

```bash
git add app/backend/app/pipeline/stage1/adapter_qwen35_9b.py \
        app/backend/tests/test_stage1_v2.py
git commit -m "feat(stage1): add adapter_qwen35_9b (1C — Unsloth non-thinking)"
```

---

## Task 7: Adapter 1D — `adapter_gemma4.py` (Unsloth GGUF)

**Files:**
- Create: `app/backend/app/pipeline/stage1/adapter_gemma4.py`
- Modify: `app/backend/tests/test_stage1_v2.py`

Gemma4 E4B is loaded as a GGUF file via Unsloth's GGUF inference path. The GGUF loader uses `from_pretrained` with the `.gguf` file path directly. Non-thinking is not applicable to Gemma4 (it does not have a thinking mode); the `enable_thinking` flag must NOT be passed here.

- [ ] **Step 7.1: Write the failing test**

Append to `app/backend/tests/test_stage1_v2.py`:

```python
# ---------------------------------------------------------------------------
# Task 7: adapter_gemma4.py
# ---------------------------------------------------------------------------

class TestAdapterGemma4:
    @pytest.mark.asyncio
    async def test_returns_string(self, monkeypatch):
        from app.pipeline.stage1 import adapter_gemma4
        from unittest.mock import MagicMock, patch

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "The wind blew."
        fake_model.generate.return_value = [[1, 2, 3]]
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.return_value = fake_inputs

        with patch(
            "app.pipeline.stage1.adapter_gemma4.FastLanguageModel.from_pretrained",
            return_value=(fake_model, fake_tokenizer),
        ):
            adapter_gemma4._MODEL_CACHE.clear()
            result = await adapter_gemma4.translate("風が吹いた。", rag_context="", glossary_context="")

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_enable_thinking_not_passed(self, monkeypatch):
        """Gemma4 does not support enable_thinking — must not appear in generate() kwargs."""
        from app.pipeline.stage1 import adapter_gemma4
        from unittest.mock import MagicMock, patch

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "result"
        fake_model.generate.return_value = [[1, 2, 3]]
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.return_value = fake_inputs

        with patch(
            "app.pipeline.stage1.adapter_gemma4.FastLanguageModel.from_pretrained",
            return_value=(fake_model, fake_tokenizer),
        ):
            adapter_gemma4._MODEL_CACHE.clear()
            await adapter_gemma4.translate("x", rag_context="", glossary_context="")

        call_kwargs = fake_model.generate.call_args.kwargs
        assert "enable_thinking" not in call_kwargs
```

- [ ] **Step 7.2: Run test to verify it fails**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterGemma4 -v
```

Expected: `ImportError`

- [ ] **Step 7.3: Implement `adapter_gemma4.py`**

Create `app/backend/app/pipeline/stage1/adapter_gemma4.py`:

```python
"""
Stage 1D — Gemma4 E4B GGUF via Unsloth GGUF inference.

Gemma4 is loaded from a .gguf file. Unsloth's FastLanguageModel.from_pretrained
accepts GGUF paths directly — pass the full path to the .gguf file.

Gemma4 does NOT support the enable_thinking parameter — do not pass it.

VRAM footprint: ~4GB at E4B quantization (4-bit).

Model path resolution (in priority order):
  1. settings.hime_gemma4_path      (if non-empty; should point to the .gguf file)
  2. MODELS_DIR / "gemma4-e4b"      (directory — Unsloth auto-finds the .gguf inside)
"""
from __future__ import annotations

import asyncio
import logging

from ...config import settings
from ...core.paths import MODELS_DIR
from ...pipeline.prompts import stage1_messages

_log = logging.getLogger(__name__)

_MODEL_CACHE: dict[str, object] = {}


def _model_path() -> str:
    if settings.hime_gemma4_path:
        return settings.hime_gemma4_path
    return str(MODELS_DIR / "gemma4-e4b")


def _load_model():
    if "model" in _MODEL_CACHE:
        return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]

    from unsloth import FastLanguageModel  # noqa: PLC0415

    path = _model_path()
    _log.info("Loading Gemma4 E4B GGUF from %s", path)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=path,
        max_seq_length=4096,
        load_in_4bit=True,
    )
    FastLanguageModel.for_inference(model)
    _MODEL_CACHE["model"] = model
    _MODEL_CACHE["tokenizer"] = tokenizer
    _log.info("Gemma4 E4B loaded.")
    return model, tokenizer


def _run_inference(source_jp: str, rag_context: str, glossary_context: str) -> str:
    model, tokenizer = _load_model()

    messages = stage1_messages(source_jp, rag_context=rag_context, glossary=glossary_context)
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    output_ids = model.generate(
        **inputs,
        max_new_tokens=1024,
        temperature=0.3,
        do_sample=True,
        pad_token_id=tokenizer.eos_token_id,
        # NOTE: enable_thinking is intentionally omitted — Gemma4 does not support it
    )
    new_tokens = output_ids[0][inputs["input_ids"].shape[-1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


async def translate(
    source_jp: str,
    *,
    rag_context: str = "",
    glossary_context: str = "",
) -> str:
    """
    Translate source_jp with Gemma4 E4B (GGUF, non-thinking not applicable).

    Raises on CUDA OOM or model load failure — caller uses return_exceptions=True.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _run_inference, source_jp, rag_context, glossary_context
    )
```

- [ ] **Step 7.4: Run test to verify it passes**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterGemma4 -v
```

Expected: 2 PASSED

- [ ] **Step 7.5: Commit**

```bash
git add app/backend/app/pipeline/stage1/adapter_gemma4.py \
        app/backend/tests/test_stage1_v2.py
git commit -m "feat(stage1): add adapter_gemma4 (1D — Unsloth GGUF)"
```

---

## Task 8: Adapter 1E — `adapter_jmdict.py` (LexiconService wrapper)

**Files:**
- Create: `app/backend/app/pipeline/stage1/adapter_jmdict.py`
- Modify: `app/backend/tests/test_stage1_v2.py`

This adapter wraps the existing `LexiconService` and always returns a non-None string. It is the fallback that must always succeed; even for empty/whitespace input, it returns `""` rather than raising.

- [ ] **Step 8.1: Write the failing test**

Append to `app/backend/tests/test_stage1_v2.py`:

```python
# ---------------------------------------------------------------------------
# Task 8: adapter_jmdict.py
# ---------------------------------------------------------------------------

class TestAdapterJmdict:
    def test_returns_string_for_known_text(self, monkeypatch):
        from app.pipeline.stage1 import adapter_jmdict
        from app.services.lexicon_service import LexiconResult

        fake_result = LexiconResult(
            tokens=[],
            literal_translation="cat run .",
            unknown_tokens=[],
            confidence=0.9,
        )

        monkeypatch.setattr(
            "app.pipeline.stage1.adapter_jmdict.LexiconService.translate",
            lambda self, text: fake_result,
        )

        result = adapter_jmdict.translate("猫が走る。")
        assert result == "cat run ."

    def test_returns_empty_string_for_empty_input(self, monkeypatch):
        from app.pipeline.stage1 import adapter_jmdict
        from app.services.lexicon_service import LexiconResult

        fake_result = LexiconResult(
            tokens=[],
            literal_translation="",
            unknown_tokens=[],
            confidence=0.0,
        )

        monkeypatch.setattr(
            "app.pipeline.stage1.adapter_jmdict.LexiconService.translate",
            lambda self, text: fake_result,
        )

        result = adapter_jmdict.translate("")
        assert result == ""

    def test_never_raises(self, monkeypatch):
        """Even if LexiconService raises internally, adapter must not propagate it."""
        from app.pipeline.stage1 import adapter_jmdict

        def broken_translate(self, text):
            raise RuntimeError("MeCab died")

        monkeypatch.setattr(
            "app.pipeline.stage1.adapter_jmdict.LexiconService.translate",
            broken_translate,
        )

        result = adapter_jmdict.translate("猫")
        assert isinstance(result, str)
        assert result == ""
```

- [ ] **Step 8.2: Run test to verify it fails**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterJmdict -v
```

Expected: `ImportError`

- [ ] **Step 8.3: Implement `adapter_jmdict.py`**

Create `app/backend/app/pipeline/stage1/adapter_jmdict.py`:

```python
"""
Stage 1E — JMdict literal translation via LexiconService.

This adapter is synchronous and always succeeds. It is the completeness anchor
for the consensus merger — providing a word-by-word gloss even when all neural
models fail. Never raises; returns "" on any internal error.
"""
from __future__ import annotations

import logging

from ...services.lexicon_service import LexiconService

_log = logging.getLogger(__name__)


def translate(source_jp: str) -> str:
    """
    Return a space-separated literal English gloss of source_jp via JMdict.

    Always returns a str (may be empty). Never raises.
    """
    try:
        result = LexiconService().translate(source_jp)
        return result.literal_translation
    except Exception as exc:  # noqa: BLE001
        _log.warning("JMdict adapter failed: %s", exc)
        return ""
```

- [ ] **Step 8.4: Run test to verify it passes**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestAdapterJmdict -v
```

Expected: 3 PASSED

- [ ] **Step 8.5: Commit**

```bash
git add app/backend/app/pipeline/stage1/adapter_jmdict.py \
        app/backend/tests/test_stage1_v2.py
git commit -m "feat(stage1): add adapter_jmdict (1E — LexiconService wrapper, never raises)"
```

---

## Task 9: Stage 1 Runner — `runner.py` with OOM Fallback

**Files:**
- Create: `app/backend/app/pipeline/stage1/runner.py`
- Modify: `app/backend/tests/test_stage1_v2.py`

This is the orchestrator that runs all 5 adapters and handles VRAM constraints. Key design decisions:

- **1A (Qwen32B/Ollama) is always parallel** with local models because it runs in a separate Ollama process and uses no local VRAM from our perspective.
- **1B, 1C, 1D (local Unsloth)** are tried in parallel first. If any raises `torch.cuda.OutOfMemoryError` (or `RuntimeError` containing "CUDA out of memory"), the runner falls back to running them sequentially with `gc.collect()` + `torch.cuda.empty_cache()` between each call.
- **1E (JMdict)** is always run synchronously (it's CPU-only and fast) — no need to make it async.
- Adapter failures (non-OOM) leave the corresponding field as `None` without retrying.

- [ ] **Step 9.1: Write the failing tests**

Append to `app/backend/tests/test_stage1_v2.py`:

```python
# ---------------------------------------------------------------------------
# Task 9: stage1/runner.py
# ---------------------------------------------------------------------------

class TestRunStage1Integration:
    """Integration test: run_stage1() with all adapters mocked."""

    @pytest.mark.asyncio
    async def test_all_adapters_succeed_returns_complete_drafts(self, monkeypatch):
        from app.pipeline.stage1 import runner as stage1_runner
        from app.pipeline.stage1._types import Stage1Drafts

        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_qwen32b.translate",
            lambda *a, **kw: _async_return("qwen32b translation"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_translategemma.translate",
            lambda *a, **kw: _async_return("translategemma translation"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_qwen35_9b.translate",
            lambda *a, **kw: _async_return("qwen35 translation"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_gemma4.translate",
            lambda *a, **kw: _async_return("gemma4 translation"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_jmdict.translate",
            lambda text: "jmdict gloss",
        )

        result = await stage1_runner.run_stage1(
            segment="猫が走る。",
            rag_context="",
            glossary_context="",
        )

        assert isinstance(result, Stage1Drafts)
        assert result.source_jp == "猫が走る。"
        assert result.qwen32b == "qwen32b translation"
        assert result.translategemma12b == "translategemma translation"
        assert result.qwen35_9b == "qwen35 translation"
        assert result.gemma4_e4b == "gemma4 translation"
        assert result.jmdict == "jmdict gloss"

    @pytest.mark.asyncio
    async def test_two_adapters_fail_result_still_has_jmdict(self, monkeypatch):
        """Graceful degradation: failed adapters → None; jmdict always present."""
        from app.pipeline.stage1 import runner as stage1_runner
        from app.pipeline.stage1._types import Stage1Drafts

        async def fail(*a, **kw):
            raise RuntimeError("model unavailable")

        monkeypatch.setattr("app.pipeline.stage1.runner.adapter_qwen32b.translate", fail)
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_translategemma.translate",
            lambda *a, **kw: _async_return("gemma translation"),
        )
        monkeypatch.setattr("app.pipeline.stage1.runner.adapter_qwen35_9b.translate", fail)
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_gemma4.translate",
            lambda *a, **kw: _async_return("gemma4 ok"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_jmdict.translate",
            lambda text: "jmdict fallback",
        )

        result = await stage1_runner.run_stage1(
            segment="テスト", rag_context="", glossary_context=""
        )

        assert result.qwen32b is None
        assert result.translategemma12b == "gemma translation"
        assert result.qwen35_9b is None
        assert result.gemma4_e4b == "gemma4 ok"
        assert result.jmdict == "jmdict fallback"

    @pytest.mark.asyncio
    async def test_oom_triggers_sequential_fallback(self, monkeypatch):
        """When a local adapter raises OOM, runner retries all local adapters sequentially."""
        from app.pipeline.stage1 import runner as stage1_runner

        call_log: list[str] = []

        async def oom_first_call_then_ok(name):
            """Returns a coroutine factory that OOMs on parallel call, succeeds sequentially."""
            call_count = {"n": 0}

            async def inner(*a, **kw):
                call_count["n"] += 1
                # Simulate OOM on first (parallel) attempt
                if call_count["n"] == 1:
                    raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
                call_log.append(name)
                return f"{name} sequential result"

            return inner

        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_qwen32b.translate",
            lambda *a, **kw: _async_return("qwen32b ok"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_translategemma.translate",
            await oom_first_call_then_ok("translategemma"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_qwen35_9b.translate",
            await oom_first_call_then_ok("qwen35"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_gemma4.translate",
            await oom_first_call_then_ok("gemma4"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_jmdict.translate",
            lambda text: "jmdict",
        )

        result = await stage1_runner.run_stage1(
            segment="テスト", rag_context="", glossary_context=""
        )

        # All three local adapters should have succeeded in sequential retry
        assert result.translategemma12b == "translategemma sequential result"
        assert result.qwen35_9b == "qwen35 sequential result"
        assert result.gemma4_e4b == "gemma4 sequential result"
        # Qwen32B (Ollama) always runs parallel and is unaffected by local OOM
        assert result.qwen32b == "qwen32b ok"


# Helper coroutine factory used across multiple tests
async def _async_return(value):
    return value
```

- [ ] **Step 9.2: Run test to verify it fails**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestRunStage1Integration -v
```

Expected: `ImportError` — `stage1/runner.py` doesn't exist yet.

- [ ] **Step 9.3: Implement `stage1/runner.py`**

Create `app/backend/app/pipeline/stage1/runner.py`:

```python
"""
Stage 1 v2 orchestrator — runs all 5 adapters and returns Stage1Drafts.

Execution strategy:
  - 1A (Qwen32B/Ollama) always runs in parallel with local models.
    It has no VRAM footprint in our process (Ollama manages its own memory).
  - 1B, 1C, 1D (local Unsloth) are attempted in parallel first.
    If any result is a CUDA OOM error, ALL local adapters are retried
    sequentially with VRAM cleanup between each call.
  - 1E (JMdict) is CPU-only, called synchronously before gather; its result
    is always available.

OOM detection heuristic: RuntimeError with "CUDA out of memory" in the message,
or torch.cuda.OutOfMemoryError (available in PyTorch >= 2.0).
"""
from __future__ import annotations

import asyncio
import gc
import logging
from typing import Any

from ._types import Stage1Drafts
from . import (
    adapter_qwen32b,
    adapter_translategemma,
    adapter_qwen35_9b,
    adapter_gemma4,
    adapter_jmdict,
)

_log = logging.getLogger(__name__)


def _is_oom(exc: BaseException) -> bool:
    """Return True if exc is a CUDA out-of-memory error."""
    msg = str(exc).lower()
    if "cuda out of memory" in msg:
        return True
    # PyTorch >= 2.0 raises a dedicated type
    try:
        import torch
        if isinstance(exc, torch.cuda.OutOfMemoryError):
            return True
    except (ImportError, AttributeError):
        pass
    return False


def _vram_cleanup() -> None:
    """Free cached GPU memory between sequential adapter calls."""
    try:
        import torch
        torch.cuda.empty_cache()
    except (ImportError, AttributeError):
        pass
    gc.collect()


async def _run_local_adapters_parallel(
    source_jp: str,
    rag_context: str,
    glossary_context: str,
) -> tuple[Any, Any, Any]:
    """
    Run adapters 1B, 1C, 1D in parallel.
    Returns a 3-tuple of (result_or_exception, ...) — never raises.
    """
    results = await asyncio.gather(
        adapter_translategemma.translate(source_jp, rag_context=rag_context, glossary_context=glossary_context),
        adapter_qwen35_9b.translate(source_jp, rag_context=rag_context, glossary_context=glossary_context),
        adapter_gemma4.translate(source_jp, rag_context=rag_context, glossary_context=glossary_context),
        return_exceptions=True,
    )
    return results[0], results[1], results[2]


async def _run_local_adapters_sequential(
    source_jp: str,
    rag_context: str,
    glossary_context: str,
) -> tuple[Any, Any, Any]:
    """
    Run adapters 1B, 1C, 1D one at a time with VRAM cleanup between each.
    Returns a 3-tuple of (result_or_exception, ...) — never raises.
    """
    _log.warning(
        "VRAM OOM detected in parallel run — falling back to sequential local inference."
    )

    results: list[Any] = []
    adapters = [
        adapter_translategemma.translate,
        adapter_qwen35_9b.translate,
        adapter_gemma4.translate,
    ]
    adapter_names = ["translategemma", "qwen35_9b", "gemma4"]

    for fn, name in zip(adapters, adapter_names):
        try:
            _vram_cleanup()
            out = await fn(source_jp, rag_context=rag_context, glossary_context=glossary_context)
            results.append(out)
        except Exception as exc:  # noqa: BLE001
            _log.warning("Sequential adapter %s failed: %s", name, exc)
            results.append(exc)

    return results[0], results[1], results[2]


def _extract(result: Any, name: str) -> str | None:
    """Convert a gather result (value or exception) to str or None."""
    if isinstance(result, BaseException):
        _log.warning("Stage 1 adapter '%s' failed: %s", name, result)
        return None
    if isinstance(result, str) and result.strip():
        return result
    if isinstance(result, str) and not result.strip():
        _log.warning("Stage 1 adapter '%s' returned empty string", name)
        return None
    return None


async def run_stage1(
    segment: str,
    rag_context: str,
    glossary_context: str,
) -> Stage1Drafts:
    """
    Run all Stage 1 adapters and return a Stage1Drafts dataclass.

    Never raises. Adapter failures → None fields (except jmdict, always a str).
    """
    # 1E — always run first (fast, CPU-only)
    jmdict_result = adapter_jmdict.translate(segment)

    # 1A + 1B/1C/1D in parallel (Ollama is independent of local VRAM)
    qwen32b_coro = adapter_qwen32b.translate(
        segment, rag_context=rag_context, glossary_context=glossary_context
    )
    local_coro = _run_local_adapters_parallel(segment, rag_context, glossary_context)

    gather_results = await asyncio.gather(qwen32b_coro, local_coro, return_exceptions=True)

    qwen32b_raw = gather_results[0]
    local_raw = gather_results[1]

    # Unwrap 1A
    if isinstance(qwen32b_raw, BaseException):
        _log.warning("Adapter 1A (qwen32b) failed: %s", qwen32b_raw)
        qwen32b_result: str | None = None
    else:
        qwen32b_result = qwen32b_raw if isinstance(qwen32b_raw, str) and qwen32b_raw.strip() else None

    # Unwrap 1B/1C/1D — detect OOM and retry sequentially if needed
    if isinstance(local_raw, BaseException):
        # The whole _run_local_adapters_parallel coroutine raised — treat as OOM
        _log.warning("Local adapter gather raised: %s — retrying sequentially", local_raw)
        tgemma_raw, q35_raw, g4_raw = await _run_local_adapters_sequential(
            segment, rag_context, glossary_context
        )
    else:
        tgemma_raw, q35_raw, g4_raw = local_raw
        # Check if any of the parallel results was an OOM
        if any(_is_oom(r) for r in (tgemma_raw, q35_raw, g4_raw) if isinstance(r, BaseException)):
            tgemma_raw, q35_raw, g4_raw = await _run_local_adapters_sequential(
                segment, rag_context, glossary_context
            )

    return Stage1Drafts(
        source_jp=segment,
        jmdict=jmdict_result,
        qwen32b=qwen32b_result,
        translategemma12b=_extract(tgemma_raw, "translategemma"),
        qwen35_9b=_extract(q35_raw, "qwen35_9b"),
        gemma4_e4b=_extract(g4_raw, "gemma4"),
    )
```

- [ ] **Step 9.4: Run test to verify it passes**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestRunStage1Integration -v
```

Expected: 3 PASSED

- [ ] **Step 9.5: Run full test_stage1_v2.py to confirm no regressions**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py -v
```

Expected: All PASSED

- [ ] **Step 9.6: Commit**

```bash
git add app/backend/app/pipeline/stage1/runner.py \
        app/backend/tests/test_stage1_v2.py
git commit -m "feat(stage1): add Stage 1 runner with parallel/sequential OOM fallback"
```

---

## Task 10: Wire `__init__.py` Public API

**Files:**
- Modify: `app/backend/app/pipeline/stage1/__init__.py`
- Modify: `app/backend/tests/test_stage1_v2.py`

- [ ] **Step 10.1: Write the failing test**

Append to `app/backend/tests/test_stage1_v2.py`:

```python
# ---------------------------------------------------------------------------
# Task 10: __init__.py public API
# ---------------------------------------------------------------------------

class TestPublicAPI:
    def test_run_stage1_importable_from_package(self):
        from app.pipeline.stage1 import run_stage1
        assert callable(run_stage1)

    def test_stage1_drafts_importable_from_package(self):
        from app.pipeline.stage1 import Stage1Drafts
        assert Stage1Drafts is not None

    def test_stage1_drafts_is_correct_type(self):
        from app.pipeline.stage1 import Stage1Drafts
        from app.pipeline.stage1._types import Stage1Drafts as InternalDrafts
        assert Stage1Drafts is InternalDrafts
```

- [ ] **Step 10.2: Run test to verify it fails**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestPublicAPI -v
```

Expected: `ImportError` — `run_stage1` not exported yet.

- [ ] **Step 10.3: Update `__init__.py`**

Replace `app/backend/app/pipeline/stage1/__init__.py` with:

```python
"""
Stage 1 v2 public API.

Usage:
    from app.pipeline.stage1 import run_stage1, Stage1Drafts

    drafts = await run_stage1(
        segment="猫が走る。",
        rag_context="",
        glossary_context="",
    )
    print(drafts.qwen32b)   # "The cat runs."  (or None if adapter failed)
    print(drafts.jmdict)    # "cat run ."      (always a str)
"""
from ._types import Stage1Drafts
from .runner import run_stage1

__all__ = ["run_stage1", "Stage1Drafts"]
```

- [ ] **Step 10.4: Run test to verify it passes**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestPublicAPI -v
```

Expected: 3 PASSED

- [ ] **Step 10.5: Run full suite again**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py -v
```

Expected: All PASSED

- [ ] **Step 10.6: Commit**

```bash
git add app/backend/app/pipeline/stage1/__init__.py \
        app/backend/tests/test_stage1_v2.py
git commit -m "feat(stage1): wire public API in __init__.py (run_stage1, Stage1Drafts)"
```

---

## Task 11: Wire Stage 1 v2 into the Main Pipeline Runner

**Files:**
- Modify: `app/backend/app/pipeline/runner.py`
- Modify: `app/backend/tests/test_stage1_v2.py`

Replace the old three-model Ollama `asyncio.gather()` in `pipeline/runner.py` with a call to `run_stage1()`. The existing lexicon anchor logic is now handled inside `adapter_jmdict.py`, so the `lexicon_anchor_block` assembly can be removed from the main runner. The rest of the pipeline (Consensus, Stage 2, Stage 3) is unchanged.

The `stage1_outputs` dict that feeds into `consensus_messages()` is rebuilt from `Stage1Drafts` — only non-None fields are included.

- [ ] **Step 11.1: Write the failing test**

Append to `app/backend/tests/test_stage1_v2.py`:

```python
# ---------------------------------------------------------------------------
# Task 11: pipeline/runner.py integration
# ---------------------------------------------------------------------------

class TestMainRunnerUsesStage1V2:
    def test_runner_imports_run_stage1(self):
        """The main pipeline runner must import from stage1 package."""
        from pathlib import Path
        runner_src = (
            Path(__file__).resolve().parent.parent / "app" / "pipeline" / "runner.py"
        ).read_text(encoding="utf-8")
        assert "from .stage1 import run_stage1" in runner_src or \
               "from app.pipeline.stage1 import run_stage1" in runner_src

    def test_runner_no_longer_has_old_stream_stage1(self):
        """The old _stream_stage1 helper should be removed (replaced by stage1 package)."""
        from pathlib import Path
        runner_src = (
            Path(__file__).resolve().parent.parent / "app" / "pipeline" / "runner.py"
        ).read_text(encoding="utf-8")
        assert "_stream_stage1" not in runner_src
```

- [ ] **Step 11.2: Run test to verify it fails**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestMainRunnerUsesStage1V2 -v
```

Expected: FAIL — `_stream_stage1` still present, `run_stage1` not imported.

- [ ] **Step 11.3: Rewrite `pipeline/runner.py` to use `run_stage1()`**

Replace `app/backend/app/pipeline/runner.py` with:

```python
"""
Multi-stage translation pipeline orchestrator — v2.

Pipeline stages:
  Stage 1 — 5 independent drafts in parallel (stage1/ package):
              1A  Qwen2.5-32B LoRA (Ollama)
              1B  TranslateGemma-12B (Unsloth local)
              1C  Qwen3.5-9B non-thinking (Unsloth local)
              1D  Gemma4 E4B GGUF (Unsloth local)
              1E  JMdict literal gloss (LexiconService, always succeeds)
  Consensus — merger model synthesises a single best translation
  Stage 2   — 72B model refines the consensus
  Stage 3   — 14B model does a final polish → final_output

Each stage streams tokens to ``ws_queue`` as JSON-serialisable dicts.
DB checkpoints are written after every stage via short-lived AsyncSessionLocal
sessions so the job survives a WebSocket disconnect.
"""
import asyncio
import json
import re
import time

from sqlalchemy import select

import logging as _logging

from ..config import settings
from ..database import AsyncSessionLocal
from ..inference import stream_completion
from ..models import Book, Translation
from .prompts import (
    consensus_messages,
    stage2_messages,
    stage3_messages,
)
from .stage1 import run_stage1, Stage1Drafts


async def _stream_stage(
    event_prefix: str,
    url: str,
    model: str,
    messages: list[dict[str, str]],
    ws_queue: asyncio.Queue,
) -> str:
    """
    Generic streaming helper for consensus / stage2 / stage3.
    Enqueues ``{event_prefix}_token`` and ``{event_prefix}_complete`` events.
    Returns the full output string.
    """
    buf: list[str] = []
    async for token in stream_completion(url, model, messages):
        buf.append(token)
        await ws_queue.put({"event": f"{event_prefix}_token", "token": token})
    full = "".join(buf)
    await ws_queue.put({"event": f"{event_prefix}_complete", "output": full})
    return full


_CONFIDENCE_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _log_safe(msg: str, exc: BaseException) -> None:
    _logging.getLogger(__name__).warning("[pipeline] %s: %s", msg, exc)


def _parse_confidence_log(text: str) -> dict | None:
    """Extract the confidence JSON block from a consensus output."""
    if not text:
        return None
    m = _CONFIDENCE_FENCE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "confidence" not in data:
        return None
    return data


async def _checkpoint(job_id: int, **fields) -> None:
    """Write arbitrary column updates to a Translation row."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Translation).where(Translation.id == job_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return
        for k, v in fields.items():
            setattr(row, k, v)
        await session.commit()


def _drafts_to_stage1_outputs(drafts: Stage1Drafts) -> dict[str, str]:
    """
    Convert Stage1Drafts to the dict format expected by consensus_messages().
    Only non-None, non-empty fields are included. jmdict is always included
    if non-empty (it's the completeness anchor).
    """
    out: dict[str, str] = {}
    if drafts.qwen32b:
        out["qwen32b"] = drafts.qwen32b
    if drafts.translategemma12b:
        out["translategemma12b"] = drafts.translategemma12b
    if drafts.qwen35_9b:
        out["qwen35_9b"] = drafts.qwen35_9b
    if drafts.gemma4_e4b:
        out["gemma4_e4b"] = drafts.gemma4_e4b
    if drafts.jmdict:
        out["jmdict"] = drafts.jmdict
    return out


async def run_pipeline(
    job_id: int,
    source_text: str,
    notes: str,
    ws_queue: asyncio.Queue,
    book_id: int | None = None,
) -> None:
    """
    Full pipeline coroutine.  Designed to run as an asyncio.Task so that a
    WebSocket disconnect does not abort in-flight inference calls.
    """
    started_at = time.monotonic()
    glossary_block = ""
    rag_context_block = ""

    # ------------------------------------------------------------------ #
    # v2 enrichment — glossary, RAG context                               #
    # Lexicon anchor is now handled inside adapter_jmdict.py (Stage 1E). #
    # All fetches are best-effort; failure → empty string (no crash)      #
    # ------------------------------------------------------------------ #
    if book_id is not None:
        try:
            from ..services.glossary_service import GlossaryService
            async with AsyncSessionLocal() as session:
                svc = GlossaryService(session)
                g = await svc.get_or_create_for_book(book_id)
                glossary_block = await svc.format_for_prompt(g.id, source_text)
        except Exception as exc:  # noqa: BLE001
            _log_safe("glossary fetch failed", exc)

        try:
            from ..rag.retriever import format_rag_context, retrieve_top_k
            async with AsyncSessionLocal() as session:
                book = await session.get(Book, book_id)
            if book is not None and book.series_id is not None:
                chunks = await retrieve_top_k(book.series_id, source_text, top_k=5)
                rag_context_block = format_rag_context(chunks)
        except Exception as exc:  # noqa: BLE001
            _log_safe("rag retrieval failed", exc)

    try:
        # ------------------------------------------------------------------ #
        # Stage 1 — 5 adapters (4 neural + 1 lexical)                        #
        # ------------------------------------------------------------------ #
        adapter_names = ["qwen32b", "translategemma12b", "qwen35_9b", "gemma4_e4b", "jmdict"]
        await ws_queue.put({"event": "stage1_start", "models": adapter_names})
        await _checkpoint(job_id, current_stage="stage1")

        drafts = await run_stage1(
            segment=source_text,
            rag_context=rag_context_block,
            glossary_context=glossary_block,
        )

        stage1_outputs = _drafts_to_stage1_outputs(drafts)

        # Emit per-adapter completion events for the frontend
        for label, text in stage1_outputs.items():
            await ws_queue.put({"event": "stage1_complete", "model": label, "output": text})

        # Notify frontend about unavailable adapters
        for label in adapter_names:
            if label not in stage1_outputs:
                await ws_queue.put({
                    "event": "model_unavailable",
                    "model": label,
                    "reason": "Adapter failed or returned empty output",
                })

        if not stage1_outputs:
            await ws_queue.put({
                "event": "pipeline_error",
                "detail": "No Stage 1 adapters succeeded — cannot continue pipeline",
            })
            await _checkpoint(job_id, current_stage="error")
            return

        await _checkpoint(
            job_id,
            stage1_gemma_output=drafts.translategemma12b,
            stage1_deepseek_output=drafts.qwen35_9b,
            stage1_qwen32b_output=drafts.qwen32b,
        )

        # ------------------------------------------------------------------ #
        # Consensus                                                            #
        # ------------------------------------------------------------------ #
        await ws_queue.put({"event": "consensus_start"})
        await _checkpoint(job_id, current_stage="consensus")

        consensus_text = await _stream_stage(
            "consensus",
            settings.hime_merger_url,
            settings.hime_merger_model,
            consensus_messages(source_text, stage1_outputs),
            ws_queue,
        )
        await _checkpoint(job_id, consensus_output=consensus_text)

        # v1.2.1: parse confidence log from consensus output
        confidence_data = _parse_confidence_log(consensus_text)
        if confidence_data is not None:
            await _checkpoint(job_id, confidence_log=json.dumps(confidence_data))
            await ws_queue.put({"event": "confidence_log", "data": confidence_data})

        # ------------------------------------------------------------------ #
        # Stage 2 — 72B refinement                                            #
        # ------------------------------------------------------------------ #
        await ws_queue.put({"event": "stage2_start"})
        await _checkpoint(job_id, current_stage="stage2")

        stage2_text = await _stream_stage(
            "stage2",
            settings.hime_qwen72b_url,
            settings.hime_qwen72b_model,
            stage2_messages(consensus_text),
            ws_queue,
        )
        await _checkpoint(job_id, stage2_output=stage2_text)

        # ------------------------------------------------------------------ #
        # Stage 3 — 14B final polish                                          #
        # ------------------------------------------------------------------ #
        await ws_queue.put({"event": "stage3_start"})
        await _checkpoint(job_id, current_stage="stage3")

        final_text = await _stream_stage(
            "stage3",
            settings.hime_qwen14b_url,
            settings.hime_qwen14b_model,
            stage3_messages(stage2_text),
            ws_queue,
        )

        duration_ms = int((time.monotonic() - started_at) * 1000)
        await _checkpoint(
            job_id,
            final_output=final_text,
            content=final_text,
            current_stage="complete",
            pipeline_duration_ms=duration_ms,
        )

        await ws_queue.put({
            "event": "pipeline_complete",
            "final_output": final_text,
            "duration_ms": duration_ms,
        })

    except Exception as exc:
        await ws_queue.put({"event": "pipeline_error", "detail": str(exc)})
        await _checkpoint(job_id, current_stage="error")

    finally:
        # Sentinel: tells the drain loop that the pipeline is done
        await ws_queue.put(None)
```

- [ ] **Step 11.4: Run test to verify it passes**

```bash
cd app/backend
python -m pytest tests/test_stage1_v2.py::TestMainRunnerUsesStage1V2 -v
```

Expected: 2 PASSED

- [ ] **Step 11.5: Run the existing pipeline tests to verify no regressions**

```bash
cd app/backend
python -m pytest tests/test_pipeline.py -v
```

Expected: All PASSED (the `_stream_stage1` source-scan test is now satisfied by the new structure; verify `TestPipelineGracefulDegradation` still passes).

- [ ] **Step 11.6: Run the full test suite**

```bash
cd app/backend
python -m pytest tests/ -v --ignore=tests/test_v121_migrations.py
```

Expected: All PASSED. (Migrations test requires a live DB — skip in CI if not available.)

- [ ] **Step 11.7: Commit**

```bash
git add app/backend/app/pipeline/runner.py \
        app/backend/tests/test_stage1_v2.py
git commit -m "feat(pipeline): wire Stage 1 v2 package into main run_pipeline() orchestrator"
```

---

## Self-Review Checklist

**Spec coverage:**

| Requirement | Covered in |
|---|---|
| `stage1/` package with `__init__.py` exporting `run_stage1` and `Stage1Drafts` | Tasks 3, 8, 10 |
| `_types.py` with `Stage1Drafts` dataclass (all 5 fields) | Task 3 |
| `adapter_qwen32b.py` reusing existing Ollama via `inference.complete()` | Task 4 |
| `adapter_translategemma.py` via Unsloth `FastLanguageModel.from_pretrained` + `apply_chat_template` | Task 5 |
| `adapter_qwen35_9b.py` with `enable_thinking=False` | Task 6 |
| `adapter_gemma4.py` GGUF, no `enable_thinking` | Task 7 |
| `adapter_jmdict.py` thin wrapper, never raises | Task 8 |
| `stage1/runner.py` with `asyncio.gather(return_exceptions=True)` | Task 9 |
| OOM detection → sequential fallback, VRAM cleanup | Task 9 |
| 1A always parallel with local models | Task 9 |
| Unit tests for each adapter (mocked model) | Tasks 4–8 |
| Integration test: all mocked → complete `Stage1Drafts` | Task 9 |
| Graceful degradation: 2 failures → jmdict + working adapters | Task 9 |
| `pyproject.toml` update with `transformers` + `unsloth` | Task 1 |
| New `config.py` settings for local model paths | Task 2 |
| Wire into main `pipeline/runner.py` | Task 11 |
| TDD throughout (failing test → implement → green → commit) | All tasks |
| Model paths via `MODELS_DIR` from `core/paths.py` | Tasks 5, 6, 7 |

**Placeholder scan:** No TBDs, no "similar to Task N", no vague "add validation" — all code is complete.

**Type consistency:**
- `Stage1Drafts` defined in `_types.py` Task 3, used identically in Tasks 9, 10, 11.
- `translate()` signature is `(source_jp, *, rag_context, glossary_context)` throughout Tasks 4–7; Task 9 calls it consistently.
- `adapter_jmdict.translate()` is `(source_jp)` only (no rag/glossary — JMdict doesn't use them); Task 9 matches.
- `_MODEL_CACHE: dict[str, object]` used identically in Tasks 5, 6, 7 and patched as `.clear()` in tests.

---

## VRAM Budget Reference

| Adapter | Model | Quantization | Est. VRAM |
|---------|-------|-------------|-----------|
| 1A | Qwen2.5-32B LoRA (Ollama) | — (separate process) | 0 GB local |
| 1B | TranslateGemma-12B | 4-bit | ~8 GB |
| 1C | Qwen3.5-9B | 4-bit | ~6 GB |
| 1D | Gemma4 E4B GGUF | 4-bit (E4B) | ~4 GB |
| 1E | JMdict (CPU) | — | ~0 GB |
| **Total local** | | | **~18 GB** (parallel) |

With all three local models in VRAM simultaneously: ~18GB, comfortably within the RTX 5090's 32GB. The sequential fallback path is a safety net for fragmentation or overhead spikes — it kicks in automatically on any OOM and does not need manual configuration.

---

## Installation Note (Unsloth)

After updating `pyproject.toml`, run the standard uv sync:

```bash
cd app/backend
uv sync
```

Then install the CUDA-enabled unsloth wheel separately (uv/pip cannot resolve this automatically because it requires knowing your CUDA and PyTorch versions):

```bash
# Example for CUDA 12.4 + PyTorch 2.6.0 — adjust tag to match your system
pip install "unsloth[cu124-torch260]" \
    --find-links https://download.pytorch.org/whl/torch_stable.html
```

Check the exact extra tag for your system at: https://github.com/unslothai/unsloth#-installation
