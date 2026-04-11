# Pipeline v2 Stage 4 — Reader Panel + Aggregator (WS-D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing 6-persona Ollama-based reader panel with a 15-persona local Transformers reader (Qwen3.5-2B NF4) and a new LFM2-24B-A2B aggregator, wired into the pipeline runner with a max-3 retry loop.

**Architecture:** Stage 3 finishes and its external model slot is left as-is (the Stage 3 llama.cpp server at port 8005 is not changed by this workstream). Stage 4 loads Qwen3.5-2B in-process via Unsloth (NF4, Non-Thinking Mode), runs all 15 personas sequentially in a single asyncio event (off the main thread via `run_in_executor`), then unloads it. The LFM2-24B-A2B aggregator is then loaded via Transformers ≥5.0.0, produces a per-sentence verdict, and the runner applies the retry loop (max 3 iterations; iteration 4 always passes okay). Both new modules live in `app/backend/app/pipeline/` alongside the existing `runner.py`.

**Tech Stack:** Python 3.11, PyTorch, Unsloth (Qwen3.5-2B NF4), Transformers ≥5.0.0 (LFM2-24B-A2B), asyncio + `run_in_executor`, pytest + pytest-asyncio (matches existing test suite), pydantic v2.

---

## Assumption: pytest-asyncio (not pytest-anyio)

The spec mentioned `pytest-anyio`, but every existing test in this repo uses `@pytest.mark.asyncio` and `asyncio_mode = "auto"` (see `pyproject.toml`). This plan uses **pytest-asyncio** throughout to stay consistent with the test suite. No new test runner dependency is introduced.

## Assumption: Stage 3 remains an external endpoint

Stage 3 currently calls `stream_completion(settings.hime_qwen14b_url, ...)` against port 8005 (llama.cpp). This workstream does **not** move Stage 3 in-process. The VRAM note in the spec ("Stage 3 calls `model.cpu(); del model; torch.cuda.empty_cache()`") refers to the intended v2 in-process Stage 3 that will be built in a separate workstream. Stage 4 therefore loads freely after Stage 3 returns.

## Assumption: transformers ≥5.0.0

Used as specified. As of plan date (2026-04-10) this is the target version. If the package index only has 4.x, pin `transformers>=4.50.0` and note it in a follow-up.

---

## File Map

| Action  | Path | Responsibility |
|---------|------|----------------|
| Create  | `app/backend/app/pipeline/stage4_reader.py` | Load Qwen3.5-2B NF4, run 15 persona inferences, return per-sentence annotations |
| Create  | `app/backend/app/pipeline/stage4_aggregator.py` | Load LFM2-24B-A2B, synthesise 15 annotations → verdict + retry_instruction |
| Modify  | `app/backend/app/pipeline/runner.py` | Wire Stage 4 after Stage 3 with retry loop (max 3) |
| Modify  | `app/backend/app/config.py` | Add Stage 4 settings (model IDs, VRAM dtype, max retries) |
| Modify  | `app/backend/pyproject.toml` | Add `transformers>=5.0.0` and `unsloth` to core deps |
| Create  | `app/backend/tests/test_stage4_reader.py` | Unit tests for reader (model mocked) |
| Create  | `app/backend/tests/test_stage4_aggregator.py` | Unit tests for aggregator (model mocked) |
| Create  | `app/backend/tests/test_stage4_retry_loop.py` | Integration test for retry loop in runner |
| Keep    | `app/backend/app/services/reader_panel.py` | Unchanged — still used by `/api/v1/review` endpoint (legacy v1 API) |

> **Note on `reader_panel.py`:** The spec says "replace" but the `/api/v1/review` endpoint (`routers/review.py`) imports `ReaderPanel` directly. To avoid breaking the existing API while building v2, `reader_panel.py` is left intact. The new pipeline Stage 4 is a parallel implementation. A future cleanup task can deprecate it.

---

## Task 1: Add dependencies to pyproject.toml

**Files:**
- Modify: `app/backend/pyproject.toml`

- [ ] **Step 1.1: Open the file and locate the `dependencies` list**

Read `app/backend/pyproject.toml`. The `dependencies` array ends around line 28. You will add two entries after `"mcp>=1.0.0"`.

- [ ] **Step 1.2: Add the new deps**

In `app/backend/pyproject.toml`, replace the closing bracket of the `dependencies` list:

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
    "mcp>=1.0.0",
    "transformers>=5.0.0",
    "unsloth",
]
```

- [ ] **Step 1.3: Commit**

```bash
cd app/backend
git add pyproject.toml
git commit -m "chore(deps): add transformers>=5.0.0 and unsloth for Stage 4 pipeline"
```

---

## Task 2: Add Stage 4 settings to config.py

**Files:**
- Modify: `app/backend/app/config.py`

- [ ] **Step 2.1: Write the failing test**

Create `app/backend/tests/test_stage4_config.py`:

```python
"""Tests for Stage 4 settings in config."""


def test_stage4_reader_model_id_has_default():
    from app.config import Settings
    s = Settings()
    assert s.stage4_reader_model_id == "unsloth/Qwen3.5-2B-bnb-4bit"


def test_stage4_aggregator_model_id_has_default():
    from app.config import Settings
    s = Settings()
    assert s.stage4_aggregator_model_id == "LiquidAI/LFM2-24B-A2B"


def test_stage4_max_retries_default_is_3():
    from app.config import Settings
    s = Settings()
    assert s.stage4_max_retries == 3


def test_stage4_reader_dtype_default():
    from app.config import Settings
    s = Settings()
    assert s.stage4_reader_dtype == "nf4"


def test_stage4_aggregator_dtype_default():
    from app.config import Settings
    s = Settings()
    assert s.stage4_aggregator_dtype == "int4"
```

- [ ] **Step 2.2: Run the test to confirm it fails**

```bash
cd app/backend
python -m pytest tests/test_stage4_config.py -v
```

Expected: `AttributeError` or `FAILED` — settings fields don't exist yet.

- [ ] **Step 2.3: Add the settings fields**

In `app/backend/app/config.py`, after the line `hime_allow_downloads: bool = False`, add:

```python
    # Pipeline Stage 4 — Reader Panel + Aggregator (v2)
    stage4_reader_model_id: str = "unsloth/Qwen3.5-2B-bnb-4bit"
    stage4_aggregator_model_id: str = "LiquidAI/LFM2-24B-A2B"
    stage4_reader_dtype: str = "nf4"       # nf4 | fp4 | fp16
    stage4_aggregator_dtype: str = "int4"  # int4 | fp16
    stage4_max_retries: int = 3            # max Stage 3→4 retry cycles before forced okay
```

- [ ] **Step 2.4: Run the test to confirm it passes**

```bash
cd app/backend
python -m pytest tests/test_stage4_config.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 2.5: Commit**

```bash
git add app/config.py tests/test_stage4_config.py
git commit -m "feat(config): add Stage 4 reader/aggregator settings"
```

---

## Task 3: Build stage4_reader.py (model-mocked TDD)

**Files:**
- Create: `app/backend/app/pipeline/stage4_reader.py`
- Create: `app/backend/tests/test_stage4_reader.py`

### The 15 Persona System Prompts

Each persona is a `(name, system_prompt)` tuple. The system prompt instructs the model to evaluate a translation and output strict JSON.

The shared output schema each persona must produce per sentence:

```json
{
  "persona": "Purist",
  "sentence_id": 0,
  "rating": 0.85,
  "issues": ["minor word order stiffness"],
  "suggestion": "Consider 'turned away' instead of 'averted her gaze'"
}
```

### Step 3.1: Write the failing tests first

Create `app/backend/tests/test_stage4_reader.py`:

```python
"""
Tests for stage4_reader — 15-persona local Qwen3.5-2B reader panel.

The model is fully mocked: a FakeModel whose generate() returns
pre-baked token IDs and a FakeTokenizer that encodes/decodes trivially.
This lets tests run without VRAM or model files.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared fake infrastructure
# ---------------------------------------------------------------------------

_GOOD_JSON = json.dumps({
    "persona": "Purist",
    "sentence_id": 0,
    "rating": 0.9,
    "issues": [],
    "suggestion": "",
})


def _make_fake_model_and_tokenizer(output_text: str = _GOOD_JSON):
    """Return (model, tokenizer) mocks that produce output_text when generate() is called."""
    tokenizer = MagicMock()
    tokenizer.apply_chat_template.return_value = "ENCODED_PROMPT"
    # __call__ (tokenizer(text)) returns a dict with input_ids tensor-like
    tokenizer.return_value = {"input_ids": [[1, 2, 3]]}
    tokenizer.decode.return_value = output_text
    tokenizer.eos_token_id = 2

    model = MagicMock()
    # model.generate returns [[1, 2, 3, 4]] (token id list)
    model.generate.return_value = [[1, 2, 3, 4]]
    model.device = "cuda"

    return model, tokenizer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_returns_15_annotations_for_one_sentence():
    """review() should return exactly 15 PersonaAnnotation items per sentence."""
    from app.pipeline.stage4_reader import Stage4Reader, PersonaAnnotation

    model, tokenizer = _make_fake_model_and_tokenizer()
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer

    sentences = ["She turned away."]
    annotations = await reader.review(sentences=sentences, source_sentences=["彼女は顔を背けた。"])

    assert len(annotations) == 15
    assert all(isinstance(a, PersonaAnnotation) for a in annotations)


@pytest.mark.asyncio
async def test_each_annotation_has_correct_fields():
    """Every annotation must have all required fields with correct types."""
    from app.pipeline.stage4_reader import Stage4Reader, PersonaAnnotation

    model, tokenizer = _make_fake_model_and_tokenizer()
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer

    annotations = await reader.review(
        sentences=["She turned away."],
        source_sentences=["彼女は顔を背けた。"],
    )
    a = annotations[0]
    assert isinstance(a.persona, str) and len(a.persona) > 0
    assert isinstance(a.sentence_id, int)
    assert 0.0 <= a.rating <= 1.0
    assert isinstance(a.issues, list)
    assert isinstance(a.suggestion, str)


@pytest.mark.asyncio
async def test_malformed_model_output_does_not_crash():
    """If model returns invalid JSON, annotation gets rating=0.5 and issues=['parse_error']."""
    from app.pipeline.stage4_reader import Stage4Reader

    model, tokenizer = _make_fake_model_and_tokenizer("NOT JSON AT ALL")
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer

    annotations = await reader.review(
        sentences=["test"],
        source_sentences=["テスト"],
    )
    # All 15 should be fallback annotations
    assert all(a.rating == 0.5 for a in annotations)
    assert all("parse_error" in a.issues for a in annotations)


@pytest.mark.asyncio
async def test_review_multi_sentence_returns_15_per_sentence():
    """For N sentences, review() returns 15*N annotations."""
    from app.pipeline.stage4_reader import Stage4Reader

    model, tokenizer = _make_fake_model_and_tokenizer()
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer

    sentences = ["Sentence one.", "Sentence two.", "Sentence three."]
    annotations = await reader.review(sentences=sentences, source_sentences=["一。", "二。", "三。"])
    assert len(annotations) == 15 * 3


@pytest.mark.asyncio
async def test_all_15_persona_names_appear():
    """Verify all 15 persona names are present in a single-sentence review."""
    from app.pipeline.stage4_reader import Stage4Reader, PERSONAS

    model, tokenizer = _make_fake_model_and_tokenizer()
    reader = Stage4Reader.__new__(Stage4Reader)
    reader._model = model
    reader._tokenizer = tokenizer

    annotations = await reader.review(sentences=["x"], source_sentences=["x"])
    found_personas = {a.persona for a in annotations}
    expected_personas = {p[0] for p in PERSONAS}
    assert found_personas == expected_personas


def test_load_model_calls_unsloth(monkeypatch):
    """Stage4Reader.load() calls unsloth FastLanguageModel.from_pretrained with nf4."""
    import sys

    # Stub the unsloth module before import
    fake_unsloth = MagicMock()
    fake_model = MagicMock()
    fake_tokenizer = MagicMock()
    fake_unsloth.FastLanguageModel.from_pretrained.return_value = (fake_model, fake_tokenizer)
    monkeypatch.setitem(sys.modules, "unsloth", fake_unsloth)

    # Re-import to pick up stub
    import importlib
    import app.pipeline.stage4_reader as m
    importlib.reload(m)

    from app.config import Settings
    s = Settings()
    reader = m.Stage4Reader()
    reader.load(settings=s)

    fake_unsloth.FastLanguageModel.from_pretrained.assert_called_once()
    call_kwargs = fake_unsloth.FastLanguageModel.from_pretrained.call_args
    assert call_kwargs.kwargs.get("load_in_4bit") is True or call_kwargs[1].get("load_in_4bit") is True
```

- [ ] **Step 3.2: Run to confirm all tests fail**

```bash
cd app/backend
python -m pytest tests/test_stage4_reader.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.pipeline.stage4_reader'`

- [ ] **Step 3.3: Create stage4_reader.py**

Create `app/backend/app/pipeline/stage4_reader.py`:

```python
"""
Stage 4 — Reader Panel (v2 pipeline).

Loads Qwen3.5-2B via Unsloth (NF4, Non-Thinking Mode) once and runs
15 persona system-prompt inferences sequentially per sentence.

The model is intentionally NOT unloaded after this stage so that the
caller can inspect results; the caller must call reader.unload() before
loading the Stage 4 aggregator.

Usage::

    reader = Stage4Reader()
    reader.load(settings)
    annotations = await reader.review(sentences=[...], source_sentences=[...])
    reader.unload()
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import BaseModel

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persona definitions: (name, focus_description)
# ---------------------------------------------------------------------------
PERSONAS: list[tuple[str, str]] = [
    (
        "Purist",
        "You evaluate translation fidelity to the Japanese original. "
        "Flag any meaning shifts, omissions, or additions.",
    ),
    (
        "Stilist",
        "You evaluate natural English writing flow. "
        "Flag awkward phrasing, unnatural word order, or stilted prose.",
    ),
    (
        "Charakter-Tracker",
        "You evaluate consistency of character voices across the passage. "
        "Flag any character speaking out of their established register.",
    ),
    (
        "Yuri-Leser",
        "You evaluate emotional nuance in relationships between female characters. "
        "Flag undertones that are muted, lost, or mistranslated.",
    ),
    (
        "Casual-Reader",
        "You evaluate overall readability for a general English light-novel reader. "
        "Flag anything that pulls you out of immersion.",
    ),
    (
        "Grammatik-Checker",
        "You evaluate sentence structure and punctuation. "
        "Flag run-ons, fragments, comma splices, and punctuation errors.",
    ),
    (
        "Pacing-Leser",
        "You evaluate scene rhythm and paragraph flow. "
        "Flag pacing that feels rushed, padded, or inconsistent with the source.",
    ),
    (
        "Dialog-Checker",
        "You evaluate naturalness of spoken dialogue. "
        "Flag stilted, unnatural, or un-idiomatic lines of dialogue.",
    ),
    (
        "Atmosphären-Leser",
        "You evaluate mood and world-building description. "
        "Flag losses of atmosphere, setting detail, or sensory language.",
    ),
    (
        "Subtext-Leser",
        "You evaluate implied meaning and unspoken subtext. "
        "Flag implication that is made too explicit or is lost.",
    ),
    (
        "Kultureller-Kontext",
        "You evaluate correct transfer of Japanese cultural elements. "
        "Flag cultural references that are mistranslated or inadequately adapted.",
    ),
    (
        "Honorific-Checker",
        "You evaluate consistency of Japanese honorifics (-san, -chan, -kun, -senpai, -sama). "
        "Flag any dropped, added, or inconsistently rendered honorifics.",
    ),
    (
        "Namen-Tracker",
        "You evaluate consistency of character and place names. "
        "Flag any name variation, romanisation mismatch, or spelling inconsistency.",
    ),
    (
        "Emotionaler-Ton",
        "You evaluate the emotional register of the scene. "
        "Flag translations that shift the emotional tone up or down from the original.",
    ),
    (
        "Light-Novel-Leser",
        "You evaluate genre-appropriate conventions for English light novels. "
        "Flag anything that violates genre norms or expectations.",
    ),
]

_PERSONA_NAMES = [p[0] for p in PERSONAS]

_OUTPUT_SCHEMA = """\
Respond ONLY with a single JSON object (no markdown fences, no explanation):
{
  "persona": "<your persona name>",
  "sentence_id": <integer>,
  "rating": <float 0.0–1.0, where 1.0 = perfect>,
  "issues": [<short issue string>, ...],
  "suggestion": "<one concrete rewrite suggestion, or empty string if none>"
}"""


def _build_system_prompt(persona_name: str, focus: str) -> str:
    return (
        f"You are the {persona_name} reader-critic for a JP→EN light novel translation review.\n"
        f"{focus}\n\n"
        f"{_OUTPUT_SCHEMA}"
    )


def _build_user_prompt(sentence_id: int, translation: str, source: str) -> str:
    return (
        f"sentence_id: {sentence_id}\n"
        f"Japanese source: {source}\n"
        f"English translation: {translation}\n\n"
        "Evaluate the translation from your persona's perspective."
    )


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class PersonaAnnotation(BaseModel):
    persona: str
    sentence_id: int
    rating: float
    issues: list[str]
    suggestion: str


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

class Stage4Reader:
    """15-persona reader panel using Qwen3.5-2B (NF4) loaded via Unsloth."""

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None

    def load(self, settings: Any) -> None:
        """Load Qwen3.5-2B in NF4 via Unsloth. Call once before review()."""
        try:
            from unsloth import FastLanguageModel  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "unsloth is required for Stage4Reader. "
                "Install it with: pip install unsloth"
            ) from exc

        _log.info("[Stage4Reader] Loading %s (NF4) via Unsloth...", settings.stage4_reader_model_id)
        self._model, self._tokenizer = FastLanguageModel.from_pretrained(
            model_name=settings.stage4_reader_model_id,
            max_seq_length=2048,
            dtype=None,          # auto-detect
            load_in_4bit=True,   # NF4 quantisation
        )
        # Non-Thinking Mode: disable chain-of-thought generation
        # Qwen3.5 uses enable_thinking=False in the chat template call
        _log.info("[Stage4Reader] Model loaded.")

    def unload(self) -> None:
        """Move model to CPU and release VRAM. Call before loading the aggregator."""
        import torch  # type: ignore[import]
        if self._model is not None:
            self._model.cpu()
            del self._model
            self._model = None
        self._tokenizer = None
        torch.cuda.empty_cache()
        _log.info("[Stage4Reader] VRAM released.")

    def _infer_one(self, system_prompt: str, user_prompt: str) -> str:
        """Synchronous single inference call. Runs inside run_in_executor."""
        import torch  # type: ignore[import]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        # Non-Thinking Mode: pass enable_thinking=False to apply_chat_template
        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = self._tokenizer(text, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.2,
                do_sample=True,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        # Decode only the newly generated tokens (skip the input prompt)
        input_len = inputs["input_ids"].shape[1]
        new_tokens = output_ids[0][input_len:]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True)

    def _parse_annotation(self, raw: str, persona_name: str, sentence_id: int) -> PersonaAnnotation:
        """Parse JSON output from a persona run, returning a safe fallback on error."""
        text = raw.strip()
        # Strip markdown fences if the model adds them despite instructions
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            text = text.strip()
        try:
            data = json.loads(text)
            return PersonaAnnotation(
                persona=data.get("persona", persona_name),
                sentence_id=data.get("sentence_id", sentence_id),
                rating=float(data.get("rating", 0.5)),
                issues=list(data.get("issues", [])),
                suggestion=str(data.get("suggestion", "")),
            )
        except Exception:  # noqa: BLE001
            _log.warning("[Stage4Reader] %s parse error for sentence %d", persona_name, sentence_id)
            return PersonaAnnotation(
                persona=persona_name,
                sentence_id=sentence_id,
                rating=0.5,
                issues=["parse_error"],
                suggestion="",
            )

    async def review(
        self,
        *,
        sentences: list[str],
        source_sentences: list[str],
    ) -> list[PersonaAnnotation]:
        """
        Run all 15 personas over every sentence.

        Inferences are synchronous (PyTorch is not async-safe) but are
        offloaded to a thread executor so the event loop is not blocked.

        Returns a flat list: 15 annotations × len(sentences), ordered as
        [sentence_0_persona_0, sentence_0_persona_1, ..., sentence_N_persona_14].
        """
        loop = asyncio.get_event_loop()
        results: list[PersonaAnnotation] = []

        for sid, (translation, source) in enumerate(zip(sentences, source_sentences)):
            for persona_name, focus in PERSONAS:
                system_prompt = _build_system_prompt(persona_name, focus)
                user_prompt = _build_user_prompt(sid, translation, source)

                raw = await loop.run_in_executor(
                    None, self._infer_one, system_prompt, user_prompt
                )
                annotation = self._parse_annotation(raw, persona_name, sid)
                results.append(annotation)

        return results
```

- [ ] **Step 3.4: Run tests to confirm they pass**

```bash
cd app/backend
python -m pytest tests/test_stage4_reader.py -v
```

Expected: all 6 tests PASS. The `test_load_model_calls_unsloth` test may require unsloth to be importable at module level; if unsloth is not installed in the dev venv, mock the import using the monkeypatch already in the test.

- [ ] **Step 3.5: Commit**

```bash
git add app/pipeline/stage4_reader.py tests/test_stage4_reader.py
git commit -m "feat(pipeline): add Stage4Reader with 15 persona Qwen3.5-2B NF4 panel"
```

---

## Task 4: Build stage4_aggregator.py (model-mocked TDD)

**Files:**
- Create: `app/backend/app/pipeline/stage4_aggregator.py`
- Create: `app/backend/tests/test_stage4_aggregator.py`

### Aggregator contract

Input: list of `PersonaAnnotation` for **one sentence** (15 items).
Output: `AggregatorVerdict` with fields:
- `sentence_id: int`
- `verdict: Literal["okay", "retry"]`
- `retry_instruction: str | None` — set only when verdict=="retry"
- `confidence: float` — 0.0–1.0

Decision logic inside the model: LFM2-24B-A2B receives a structured summary of the 15 annotations and outputs JSON. The threshold for `retry` is a mean rating below 0.7 **or** any annotation with rating < 0.4 (these are hard-coded as hints in the prompt; the model makes the final call).

- [ ] **Step 4.1: Write the failing tests**

Create `app/backend/tests/test_stage4_aggregator.py`:

```python
"""
Tests for stage4_aggregator — LFM2-24B-A2B synthesis of 15 reader annotations.

The model is fully mocked.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def _make_annotations(rating: float = 0.85) -> list:
    """Build 15 PersonaAnnotation instances with the given rating."""
    from app.pipeline.stage4_reader import PERSONAS, PersonaAnnotation

    return [
        PersonaAnnotation(
            persona=name,
            sentence_id=0,
            rating=rating,
            issues=[],
            suggestion="",
        )
        for name, _ in PERSONAS
    ]


def _make_aggregator_with_output(output_text: str):
    """Return a Stage4Aggregator whose model returns output_text."""
    from app.pipeline.stage4_aggregator import Stage4Aggregator

    agg = Stage4Aggregator.__new__(Stage4Aggregator)

    tokenizer = MagicMock()
    tokenizer.apply_chat_template.return_value = "ENCODED"
    tokenizer.return_value = {"input_ids": [[1, 2, 3]]}
    tokenizer.decode.return_value = output_text
    tokenizer.eos_token_id = 2

    model = MagicMock()
    model.generate.return_value = [[1, 2, 3, 4]]
    model.device = "cuda"

    agg._model = model
    agg._tokenizer = tokenizer
    return agg


@pytest.mark.asyncio
async def test_verdict_okay_when_rating_high():
    """When all ratings are 0.85, aggregator should output okay."""
    from app.pipeline.stage4_aggregator import Stage4Aggregator, AggregatorVerdict

    okay_json = json.dumps({
        "sentence_id": 0,
        "verdict": "okay",
        "retry_instruction": None,
        "confidence": 0.92,
    })
    agg = _make_aggregator_with_output(okay_json)

    annotations = _make_annotations(rating=0.85)
    verdict = await agg.aggregate(annotations)

    assert isinstance(verdict, AggregatorVerdict)
    assert verdict.verdict == "okay"
    assert verdict.retry_instruction is None
    assert 0.0 <= verdict.confidence <= 1.0


@pytest.mark.asyncio
async def test_verdict_retry_when_rating_low():
    """When ratings are low (0.3), aggregator should output retry with instruction."""
    from app.pipeline.stage4_aggregator import AggregatorVerdict

    retry_json = json.dumps({
        "sentence_id": 0,
        "verdict": "retry",
        "retry_instruction": "Rewrite to preserve the melancholic undertone.",
        "confidence": 0.78,
    })
    agg = _make_aggregator_with_output(retry_json)

    annotations = _make_annotations(rating=0.3)
    verdict = await agg.aggregate(annotations)

    assert verdict.verdict == "retry"
    assert verdict.retry_instruction is not None
    assert len(verdict.retry_instruction) > 0


@pytest.mark.asyncio
async def test_malformed_output_falls_back_to_okay():
    """Malformed JSON from model → safe fallback of okay with confidence 0.0."""
    from app.pipeline.stage4_aggregator import AggregatorVerdict

    agg = _make_aggregator_with_output("THIS IS NOT JSON")
    annotations = _make_annotations(rating=0.5)
    verdict = await agg.aggregate(annotations)

    assert isinstance(verdict, AggregatorVerdict)
    assert verdict.verdict == "okay"
    assert verdict.confidence == 0.0


@pytest.mark.asyncio
async def test_aggregate_receives_all_15_personas_in_prompt():
    """The prompt sent to the model must reference all 15 persona names."""
    from app.pipeline.stage4_aggregator import Stage4Aggregator
    from app.pipeline.stage4_reader import PERSONAS

    calls: list[str] = []

    okay_json = json.dumps({
        "sentence_id": 0,
        "verdict": "okay",
        "retry_instruction": None,
        "confidence": 0.9,
    })
    agg = _make_aggregator_with_output(okay_json)

    # Intercept the chat template call to capture the messages
    original_apply = agg._tokenizer.apply_chat_template
    def capture(messages, **kw):
        calls.extend(messages)
        return original_apply(messages, **kw)
    agg._tokenizer.apply_chat_template = capture

    annotations = _make_annotations(rating=0.8)
    await agg.aggregate(annotations)

    combined = " ".join(str(c) for c in calls)
    for name, _ in PERSONAS:
        assert name in combined, f"Persona '{name}' missing from aggregator prompt"


def test_load_model_calls_transformers(monkeypatch):
    """Stage4Aggregator.load() calls AutoModelForCausalLM.from_pretrained."""
    import sys
    from unittest.mock import MagicMock

    fake_transformers = MagicMock()
    fake_model = MagicMock()
    fake_tokenizer = MagicMock()
    fake_transformers.AutoModelForCausalLM.from_pretrained.return_value = fake_model
    fake_transformers.AutoTokenizer.from_pretrained.return_value = fake_tokenizer
    fake_transformers.BitsAndBytesConfig.return_value = MagicMock()

    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    import importlib
    import app.pipeline.stage4_aggregator as m
    importlib.reload(m)

    from app.config import Settings
    s = Settings()
    agg = m.Stage4Aggregator()
    agg.load(settings=s)

    fake_transformers.AutoModelForCausalLM.from_pretrained.assert_called_once()
```

- [ ] **Step 4.2: Run to confirm all tests fail**

```bash
cd app/backend
python -m pytest tests/test_stage4_aggregator.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.pipeline.stage4_aggregator'`

- [ ] **Step 4.3: Create stage4_aggregator.py**

Create `app/backend/app/pipeline/stage4_aggregator.py`:

```python
"""
Stage 4 — Aggregator (v2 pipeline).

Loads LiquidAI/LFM2-24B-A2B via Transformers (int4 via BitsAndBytesConfig).
Receives 15 PersonaAnnotation items for one sentence and produces a single
AggregatorVerdict: okay | retry.

LFM2 is a hybrid SSM/Attention architecture. Do NOT use Unsloth for it —
use stock Transformers ≥5.0.0.

Usage::

    agg = Stage4Aggregator()
    agg.load(settings)
    verdict = await agg.aggregate(annotations)  # list[PersonaAnnotation] for one sentence
    agg.unload()
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

from pydantic import BaseModel

from .stage4_reader import PersonaAnnotation

_log = logging.getLogger(__name__)

_AGGREGATOR_SYSTEM = """\
You are the final quality aggregator for a JP→EN light novel translation review system.
You will receive structured feedback from 15 specialist reader-critic personas about a
single translated sentence.

Your task: synthesise their feedback into a verdict.

Decision guidance (apply your judgment, not just arithmetic):
- If mean rating ≥ 0.70 and no individual rating < 0.40 → lean toward "okay"
- If mean rating < 0.70 or any individual rating < 0.40 → lean toward "retry"
- On "retry", produce a single concise retry_instruction (≤40 words) that tells
  Stage 3 exactly what to fix.

Respond ONLY with a single JSON object (no markdown, no explanation):
{
  "sentence_id": <integer>,
  "verdict": "okay" or "retry",
  "retry_instruction": "<instruction string or null>",
  "confidence": <float 0.0–1.0>
}"""


def _build_user_prompt(annotations: list[PersonaAnnotation]) -> str:
    if not annotations:
        return "No annotations provided."
    sid = annotations[0].sentence_id
    lines = [f"sentence_id: {sid}", ""]
    for a in annotations:
        issues_str = "; ".join(a.issues) if a.issues else "none"
        lines.append(
            f"[{a.persona}] rating={a.rating:.2f} issues=[{issues_str}] "
            f"suggestion={a.suggestion!r}"
        )
    mean = sum(a.rating for a in annotations) / len(annotations)
    lines.append(f"\nMean rating: {mean:.3f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class AggregatorVerdict(BaseModel):
    sentence_id: int
    verdict: Literal["okay", "retry"]
    retry_instruction: str | None
    confidence: float


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------

class Stage4Aggregator:
    """LFM2-24B-A2B aggregator for 15-persona reader output."""

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None

    def load(self, settings: Any) -> None:
        """Load LFM2-24B-A2B in int4 via stock Transformers BitsAndBytesConfig."""
        try:
            import transformers  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "transformers>=5.0.0 is required for Stage4Aggregator. "
                "Install with: pip install 'transformers>=5.0.0'"
            ) from exc

        _log.info(
            "[Stage4Aggregator] Loading %s (int4) via Transformers...",
            settings.stage4_aggregator_model_id,
        )
        bnb_config = transformers.BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype="bfloat16",
            bnb_4bit_use_double_quant=True,
        )
        self._tokenizer = transformers.AutoTokenizer.from_pretrained(
            settings.stage4_aggregator_model_id,
            trust_remote_code=True,
        )
        self._model = transformers.AutoModelForCausalLM.from_pretrained(
            settings.stage4_aggregator_model_id,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )
        _log.info("[Stage4Aggregator] Model loaded.")

    def unload(self) -> None:
        """Release VRAM. Call after aggregate() is done for this sentence."""
        import torch  # type: ignore[import]
        if self._model is not None:
            self._model.cpu()
            del self._model
            self._model = None
        self._tokenizer = None
        torch.cuda.empty_cache()
        _log.info("[Stage4Aggregator] VRAM released.")

    def _infer_one(self, user_prompt: str) -> str:
        """Synchronous inference. Runs inside run_in_executor."""
        import torch  # type: ignore[import]

        messages = [
            {"role": "system", "content": _AGGREGATOR_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        text = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self._tokenizer(text, return_tensors="pt").to(self._model.device)
        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=128,
                temperature=0.1,
                do_sample=True,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        input_len = inputs["input_ids"].shape[1]
        new_tokens = output_ids[0][input_len:]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True)

    def _parse_verdict(
        self,
        raw: str,
        sentence_id: int,
    ) -> AggregatorVerdict:
        """Parse model output to AggregatorVerdict; safe fallback on error."""
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            text = text.strip()
        try:
            data = json.loads(text)
            return AggregatorVerdict(
                sentence_id=data.get("sentence_id", sentence_id),
                verdict=data.get("verdict", "okay"),
                retry_instruction=data.get("retry_instruction") or None,
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception:  # noqa: BLE001
            _log.warning(
                "[Stage4Aggregator] Parse error for sentence %d — defaulting to okay",
                sentence_id,
            )
            return AggregatorVerdict(
                sentence_id=sentence_id,
                verdict="okay",
                retry_instruction=None,
                confidence=0.0,
            )

    async def aggregate(
        self,
        annotations: list[PersonaAnnotation],
    ) -> AggregatorVerdict:
        """
        Synthesise 15 PersonaAnnotation items into one AggregatorVerdict.

        ``annotations`` must all share the same sentence_id.
        """
        if not annotations:
            return AggregatorVerdict(
                sentence_id=0,
                verdict="okay",
                retry_instruction=None,
                confidence=0.0,
            )

        sentence_id = annotations[0].sentence_id
        user_prompt = _build_user_prompt(annotations)

        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(None, self._infer_one, user_prompt)
        return self._parse_verdict(raw, sentence_id)
```

- [ ] **Step 4.4: Run tests to confirm they pass**

```bash
cd app/backend
python -m pytest tests/test_stage4_aggregator.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 4.5: Commit**

```bash
git add app/pipeline/stage4_aggregator.py tests/test_stage4_aggregator.py
git commit -m "feat(pipeline): add Stage4Aggregator with LFM2-24B-A2B verdict synthesis"
```

---

## Task 5: Wire Stage 4 into runner.py with retry loop

**Files:**
- Modify: `app/backend/app/pipeline/runner.py`
- Create: `app/backend/tests/test_stage4_retry_loop.py`

### Retry loop semantics

```
attempt = 1
while attempt <= settings.stage4_max_retries:
    run Stage 4 reader + aggregator
    if ALL sentences verdict == "okay":
        break
    if attempt == settings.stage4_max_retries:
        # forced pass — do not retry again
        break
    # build retry_notes from retry_instructions
    re-run Stage 3 with retry_notes appended
    attempt += 1
```

After the loop, `final_text` is whatever Stage 3 last produced.

### WebSocket events emitted by Stage 4

| Event | Payload |
|-------|---------|
| `stage4_start` | `{attempt: int}` |
| `stage4_reader_complete` | `{attempt: int, annotation_count: int}` |
| `stage4_verdict` | `{attempt: int, sentence_id: int, verdict: str, retry_instruction: str\|null}` |
| `stage4_retry` | `{attempt: int, retry_notes: str}` |
| `stage4_complete` | `{attempts: int, final_output: str}` |

- [ ] **Step 5.1: Write the failing integration test**

Create `app/backend/tests/test_stage4_retry_loop.py`:

```python
"""
Integration tests for the Stage 4 retry loop inside run_pipeline.

We do NOT load real models. Instead we monkey-patch the Stage4Reader and
Stage4Aggregator classes to return canned responses, and stub out inference
calls for Stages 1–3 so run_pipeline runs end-to-end in <1 second.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.stage4_reader import PersonaAnnotation, PERSONAS
from app.pipeline.stage4_aggregator import AggregatorVerdict


def _okay_annotations(sentence_id: int = 0) -> list[PersonaAnnotation]:
    return [
        PersonaAnnotation(persona=name, sentence_id=sentence_id, rating=0.9, issues=[], suggestion="")
        for name, _ in PERSONAS
    ]


def _retry_annotations(sentence_id: int = 0) -> list[PersonaAnnotation]:
    return [
        PersonaAnnotation(persona=name, sentence_id=sentence_id, rating=0.3, issues=["bad"], suggestion="fix it")
        for name, _ in PERSONAS
    ]


def _okay_verdict(sentence_id: int = 0) -> AggregatorVerdict:
    return AggregatorVerdict(sentence_id=sentence_id, verdict="okay", retry_instruction=None, confidence=0.95)


def _retry_verdict(sentence_id: int = 0) -> AggregatorVerdict:
    return AggregatorVerdict(
        sentence_id=sentence_id,
        verdict="retry",
        retry_instruction="Preserve the wistful tone.",
        confidence=0.80,
    )


async def _collect_events(ws_queue: asyncio.Queue) -> list[dict]:
    """Drain the ws_queue until None sentinel."""
    events = []
    while True:
        item = await ws_queue.get()
        if item is None:
            break
        events.append(item)
    return events


# ---------------------------------------------------------------------------
# Helper: build a fully-stubbed run_pipeline coroutine
# ---------------------------------------------------------------------------

def _patch_pipeline(
    reader_review_return,
    aggregator_aggregate_return,
    stage3_output: str = "Stage3 output.",
):
    """
    Returns a context manager that patches out all model calls in runner.py.

    reader_review_return: what Stage4Reader.review() returns (list[PersonaAnnotation])
    aggregator_aggregate_return: what Stage4Aggregator.aggregate() returns (AggregatorVerdict)
                                 OR a list of AggregatorVerdict to return in sequence.
    """
    import contextlib

    @contextlib.asynccontextmanager
    async def _ctx():
        # Stub Stage 1-3 inference
        fake_token_stream = AsyncMock()
        fake_token_stream.__aiter__ = lambda s: aiter_tokens(["hello"])

        async def aiter_tokens(tokens):
            for t in tokens:
                yield t

        fake_stream = MagicMock()
        fake_stream.__aiter__ = MagicMock(return_value=aiter_tokens(["Stage1 output."]))

        # Stub database checkpoint
        async def fake_checkpoint(*a, **kw):
            pass

        # Stub Stage4Reader
        fake_reader = MagicMock()
        fake_reader.load = MagicMock()
        fake_reader.unload = MagicMock()
        if asyncio.iscoroutine(reader_review_return) or callable(reader_review_return):
            fake_reader.review = AsyncMock(return_value=reader_review_return)
        else:
            fake_reader.review = AsyncMock(return_value=reader_review_return)

        # Stub Stage4Aggregator — may return different verdicts per call
        fake_aggregator = MagicMock()
        fake_aggregator.load = MagicMock()
        fake_aggregator.unload = MagicMock()
        if isinstance(aggregator_aggregate_return, list):
            fake_aggregator.aggregate = AsyncMock(side_effect=aggregator_aggregate_return)
        else:
            fake_aggregator.aggregate = AsyncMock(return_value=aggregator_aggregate_return)

        with (
            patch("app.pipeline.runner.stream_completion", return_value=aiter_tokens(["out"])),
            patch("app.pipeline.runner._checkpoint", side_effect=fake_checkpoint),
            patch("app.pipeline.runner.Stage4Reader", return_value=fake_reader),
            patch("app.pipeline.runner.Stage4Aggregator", return_value=fake_aggregator),
        ):
            yield fake_reader, fake_aggregator

    return _ctx()


@pytest.mark.asyncio
async def test_stage4_okay_on_first_attempt_no_retry():
    """When aggregator says okay immediately, Stage 3 runs only once."""
    from app.pipeline.runner import run_pipeline

    async with _patch_pipeline(
        reader_review_return=_okay_annotations(),
        aggregator_aggregate_return=_okay_verdict(),
    ) as (reader, aggregator):
        ws_queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline(
            job_id=1,
            source_text="彼女は顔を背けた。",
            notes="",
            ws_queue=ws_queue,
        )
        events = await _collect_events(ws_queue)

    event_names = [e["event"] for e in events]
    assert "stage4_start" in event_names
    assert "stage4_complete" in event_names

    # Stage 3 should have run exactly once (no retry)
    stage3_completes = [e for e in events if e["event"] == "stage3_complete"]
    assert len(stage3_completes) == 1


@pytest.mark.asyncio
async def test_stage4_retry_triggers_stage3_rerun():
    """When aggregator returns retry, Stage 3 runs a second time."""
    from app.pipeline.runner import run_pipeline

    # First call → retry, second call → okay
    verdicts = [_retry_verdict(), _okay_verdict()]

    async with _patch_pipeline(
        reader_review_return=_okay_annotations(),
        aggregator_aggregate_return=verdicts,
    ) as (reader, aggregator):
        ws_queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline(
            job_id=1,
            source_text="彼女は顔を背けた。",
            notes="",
            ws_queue=ws_queue,
        )
        events = await _collect_events(ws_queue)

    event_names = [e["event"] for e in events]
    assert event_names.count("stage3_complete") == 2
    assert "stage4_retry" in event_names


@pytest.mark.asyncio
async def test_stage4_max_retries_forces_okay():
    """After max_retries attempts, pipeline always proceeds regardless of verdict."""
    from app.pipeline.runner import run_pipeline
    from app.config import settings

    # Always return retry — should still complete after max_retries
    always_retry = [_retry_verdict()] * (settings.stage4_max_retries + 2)

    async with _patch_pipeline(
        reader_review_return=_retry_annotations(),
        aggregator_aggregate_return=always_retry,
    ) as (reader, aggregator):
        ws_queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline(
            job_id=1,
            source_text="彼女は顔を背けた。",
            notes="",
            ws_queue=ws_queue,
        )
        events = await _collect_events(ws_queue)

    event_names = [e["event"] for e in events]
    # Pipeline must complete, not hang
    assert "pipeline_complete" in event_names
    # Stage 3 ran at most max_retries + 1 times
    stage3_completes = [e for e in events if e["event"] == "stage3_complete"]
    assert len(stage3_completes) <= settings.stage4_max_retries + 1


@pytest.mark.asyncio
async def test_stage4_emits_verdict_events():
    """stage4_verdict event is emitted for each sentence after aggregation."""
    from app.pipeline.runner import run_pipeline

    async with _patch_pipeline(
        reader_review_return=_okay_annotations(sentence_id=0),
        aggregator_aggregate_return=_okay_verdict(sentence_id=0),
    ) as _:
        ws_queue: asyncio.Queue = asyncio.Queue()
        await run_pipeline(
            job_id=1,
            source_text="彼女は顔を背けた。",
            notes="",
            ws_queue=ws_queue,
        )
        events = await _collect_events(ws_queue)

    verdict_events = [e for e in events if e["event"] == "stage4_verdict"]
    assert len(verdict_events) >= 1
    assert "verdict" in verdict_events[0]
```

- [ ] **Step 5.2: Run to confirm tests fail**

```bash
cd app/backend
python -m pytest tests/test_stage4_retry_loop.py -v
```

Expected: tests fail because `runner.py` does not import or call `Stage4Reader`/`Stage4Aggregator` yet.

- [ ] **Step 5.3: Modify runner.py — add imports**

At the top of `app/backend/app/pipeline/runner.py`, after the existing imports block (around line 32), add:

```python
from .stage4_reader import Stage4Reader
from .stage4_aggregator import Stage4Aggregator
```

- [ ] **Step 5.4: Modify runner.py — add Stage 4 block after Stage 3**

Locate the section in `run_pipeline` that ends with:

```python
        await ws_queue.put({
            "event": "pipeline_complete",
            "final_output": final_text,
            "duration_ms": duration_ms,
        })
```

Replace **only** that `ws_queue.put(pipeline_complete …)` call and the lines immediately before it (the `duration_ms` calculation and `_checkpoint` call) with the following block. The new block re-runs Stage 3 inside the retry loop, so `duration_ms` is captured at the end of Stage 4 instead:

```python
        # ------------------------------------------------------------------ #
        # Stage 4 — Reader Panel + Aggregator (retry loop, max N attempts)   #
        # ------------------------------------------------------------------ #
        # Split final_text into sentences for per-sentence verdicts.
        # Simple heuristic: split on sentence-ending punctuation.
        import re as _re
        _SENT_SPLIT = _re.compile(r'(?<=[.!?…」])\s+')
        sentences = _SENT_SPLIT.split(final_text.strip()) or [final_text]
        source_sentences = _SENT_SPLIT.split(source_text.strip()) or [source_text]
        # Pad/truncate source_sentences to match translation sentence count
        if len(source_sentences) < len(sentences):
            source_sentences += [source_sentences[-1]] * (len(sentences) - len(source_sentences))
        source_sentences = source_sentences[: len(sentences)]

        reader = Stage4Reader()
        reader.load(settings)

        aggregator = Stage4Aggregator()

        attempt = 0
        max_attempts = settings.stage4_max_retries + 1  # +1 so last attempt always passes

        while attempt < max_attempts:
            attempt += 1
            await ws_queue.put({"event": "stage4_start", "attempt": attempt})
            await _checkpoint(job_id, current_stage=f"stage4_attempt_{attempt}")

            annotations = await reader.review(
                sentences=sentences,
                source_sentences=source_sentences,
            )
            await ws_queue.put({
                "event": "stage4_reader_complete",
                "attempt": attempt,
                "annotation_count": len(annotations),
            })

            # Unload reader, load aggregator
            reader.unload()
            aggregator.load(settings)

            # Aggregate per sentence
            from itertools import groupby as _groupby
            sorted_ann = sorted(annotations, key=lambda a: a.sentence_id)
            verdicts: list = []
            for sid, group in _groupby(sorted_ann, key=lambda a: a.sentence_id):
                verdict = await aggregator.aggregate(list(group))
                verdicts.append(verdict)
                await ws_queue.put({
                    "event": "stage4_verdict",
                    "attempt": attempt,
                    "sentence_id": sid,
                    "verdict": verdict.verdict,
                    "retry_instruction": verdict.retry_instruction,
                    "confidence": verdict.confidence,
                })

            aggregator.unload()

            # Check if any sentence needs retry
            retry_verdicts = [v for v in verdicts if v.verdict == "retry"]

            if not retry_verdicts or attempt >= max_attempts:
                # All okay, or we've exhausted retries — accept current final_text
                if retry_verdicts and attempt >= max_attempts:
                    await ws_queue.put({
                        "event": "stage4_forced_okay",
                        "attempt": attempt,
                        "detail": "Max retries reached; accepting current translation.",
                    })
                break

            # Build retry instruction for Stage 3
            retry_notes = " | ".join(
                f"[s{v.sentence_id}] {v.retry_instruction}"
                for v in retry_verdicts
                if v.retry_instruction
            )
            await ws_queue.put({"event": "stage4_retry", "attempt": attempt, "retry_notes": retry_notes})

            # Re-run Stage 3 with retry_notes
            await ws_queue.put({"event": "stage3_start"})
            await _checkpoint(job_id, current_stage=f"stage3_retry_{attempt}")

            final_text = await _stream_stage(
                "stage3",
                settings.hime_qwen14b_url,
                settings.hime_qwen14b_model,
                stage3_messages(stage2_text, retry_notes=retry_notes),
                ws_queue,
            )
            await _checkpoint(job_id, final_output=final_text)

            # Update sentences for next reader pass
            sentences = _SENT_SPLIT.split(final_text.strip()) or [final_text]
            if len(source_sentences) < len(sentences):
                source_sentences += [source_sentences[-1]] * (len(sentences) - len(source_sentences))
            source_sentences = source_sentences[: len(sentences)]

            # Reload reader for next attempt
            reader.load(settings)

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
```

> **Important:** The `duration_ms` assignment that was previously just before the `pipeline_complete` put call must be removed from its old location (it is now inside the Stage 4 block above). Verify there is no duplicate `duration_ms = ...` line remaining after Stage 3.

- [ ] **Step 5.5: Update stage3_messages to accept retry_notes**

The Stage 4 retry loop passes `retry_notes` to `stage3_messages`. Open `app/backend/app/pipeline/prompts.py` and update `stage3_messages`:

```python
def stage3_messages(stage2_text: str, retry_notes: str = "") -> list[dict[str, str]]:
    """Messages for the Stage 3 (14B final polish) model."""
    system = _STAGE3_SYSTEM
    if retry_notes:
        system = (
            system
            + "\n\n--- READER PANEL RETRY NOTES ---\n"
            + "A critic panel identified the following issues in the previous pass. "
            + "Address them in your output:\n"
            + retry_notes
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": stage2_text},
    ]
```

- [ ] **Step 5.6: Run all Stage 4 tests**

```bash
cd app/backend
python -m pytest tests/test_stage4_retry_loop.py tests/test_stage4_reader.py tests/test_stage4_aggregator.py -v
```

Expected: all tests PASS.

- [ ] **Step 5.7: Run the full test suite to confirm no regressions**

```bash
cd app/backend
python -m pytest tests/ -v --ignore=tests/test_v121_migrations.py
```

Expected: all previously-passing tests still PASS. The migration test is excluded because it requires a live DB.

- [ ] **Step 5.8: Commit**

```bash
git add app/pipeline/runner.py app/pipeline/prompts.py tests/test_stage4_retry_loop.py
git commit -m "feat(pipeline): wire Stage 4 reader+aggregator into run_pipeline with max-retry loop"
```

---

## Task 6: Smoke-test stage3_messages retry_notes

**Files:**
- Modify: `app/backend/tests/test_pipeline.py`

- [ ] **Step 6.1: Add a test for stage3_messages with retry_notes**

Append to `app/backend/tests/test_pipeline.py`:

```python
    def test_stage3_messages_with_retry_notes(self):
        from app.pipeline.prompts import stage3_messages
        msgs = stage3_messages("Some polished text.", retry_notes="[s0] Preserve wistful tone.")
        system = msgs[0]["content"]
        assert "READER PANEL RETRY NOTES" in system
        assert "wistful tone" in system
        # User message unchanged
        assert msgs[1]["content"] == "Some polished text."

    def test_stage3_messages_without_retry_notes_unchanged(self):
        from app.pipeline.prompts import stage3_messages
        msgs_plain = stage3_messages("Some polished text.")
        msgs_empty = stage3_messages("Some polished text.", retry_notes="")
        assert msgs_plain[0]["content"] == msgs_empty[0]["content"]
```

- [ ] **Step 6.2: Run the new tests**

```bash
cd app/backend
python -m pytest tests/test_pipeline.py -v
```

Expected: all tests in `test_pipeline.py` PASS including the two new ones.

- [ ] **Step 6.3: Commit**

```bash
git add tests/test_pipeline.py
git commit -m "test(pipeline): verify stage3_messages retry_notes injection"
```

---

## Task 7: Final regression check and cleanup

- [ ] **Step 7.1: Run the full test suite**

```bash
cd app/backend
python -m pytest tests/ -v --ignore=tests/test_v121_migrations.py -q
```

Expected output (summary line): `N passed` with zero failures. Note the count of passing tests before this workstream and verify it has only increased.

- [ ] **Step 7.2: Verify the /review endpoint still works (existing API)**

The `/api/v1/review` endpoint imports `ReaderPanel` from `services/reader_panel.py`. Confirm it has not been touched:

```bash
cd app/backend
python -c "from app.services.reader_panel import ReaderPanel; print('OK')"
```

Expected: `OK`

- [ ] **Step 7.3: Verify stage4 modules import cleanly without GPU**

```bash
cd app/backend
python -c "
import sys
from unittest.mock import MagicMock
sys.modules['unsloth'] = MagicMock()
sys.modules['transformers'] = MagicMock()
sys.modules['torch'] = MagicMock()
from app.pipeline.stage4_reader import Stage4Reader, PERSONAS, PersonaAnnotation
from app.pipeline.stage4_aggregator import Stage4Aggregator, AggregatorVerdict
assert len(PERSONAS) == 15
print('All Stage 4 imports OK, 15 personas confirmed')
"
```

Expected: `All Stage 4 imports OK, 15 personas confirmed`

- [ ] **Step 7.4: Final commit**

```bash
git add -u
git commit -m "chore(stage4): final cleanup and import validation for WS-D"
```

---

## Self-Review Checklist

### Spec coverage

| Requirement | Task |
|-------------|------|
| Replace reader_panel.py logic for v2 pipeline | Task 3 (new module, old kept for /review endpoint) |
| Load Qwen3.5-2B via Unsloth NF4 | Task 3, Step 3.3 (`load()`) |
| Non-Thinking Mode | Task 3, Step 3.3 (`enable_thinking=False`) |
| 15 personas, each a system prompt | Task 3, Step 3.3 (`PERSONAS` list) |
| All 15 in parallel via asyncio.gather | Partially: inferences are sequential per sentence (PyTorch is not async-safe). `run_in_executor` offloads to thread but runs one at a time to avoid GPU contention. The spec says "parallel via asyncio.gather" — see note below. |
| Output per persona: persona/sentence_id/rating/issues/suggestion | Task 3 (`PersonaAnnotation` model) |
| Model NOT unloaded after reader (aggregator loads next) | Task 3 reader.unload() is called right before aggregator.load() in runner.py, Task 5 |
| LFM2-24B-A2B via Transformers ≥5.0.0 (NOT Unsloth) | Task 4, Step 4.3 |
| Weighted synthesis → okay/retry | Task 4, aggregator prompt guidance |
| retry_instruction string on retry | Task 4 (`AggregatorVerdict.retry_instruction`) |
| AggregatorVerdict schema | Task 4 |
| transformers>=5.0.0 and unsloth in pyproject.toml | Task 1 |
| Retry loop max 3× | Task 5, `max_attempts = settings.stage4_max_retries + 1` |
| After 3 retries always okay | Task 5, `if attempt >= max_attempts: break` |
| TDD (failing test → implement → green → commit) | All tasks |
| Tests use pytest + pytest-asyncio | All test files |
| Full code, no placeholders | All steps |

### Note on asyncio.gather vs sequential

The spec requests `asyncio.gather` for the 15 personas. However, PyTorch CUDA inference is not safely parallelisable on a single GPU — running 15 concurrent `model.generate()` calls would deadlock or corrupt GPU state. The implementation uses **sequential** inference inside `run_in_executor`, which:
- Does not block the event loop (executor runs in a thread).
- Is safe for single-GPU CUDA.
- Is functionally equivalent from the caller's perspective (all 15 results gathered before returning).

If the spec author intended multi-GPU or CPU parallelism, refactor `review()` to dispatch each persona to a separate executor thread with a separate model copy. Document this decision here so the executor of this plan can confirm the intent.

### Placeholder scan

No TBD, TODO, "similar to", or placeholder strings found in the plan.

### Type consistency

- `PersonaAnnotation` defined in `stage4_reader.py`, imported in `stage4_aggregator.py` and all test files. ✓
- `AggregatorVerdict` defined in `stage4_aggregator.py`, used in `runner.py` and test files. ✓
- `Stage4Reader.review()` signature: `(sentences: list[str], source_sentences: list[str]) -> list[PersonaAnnotation]`. Used consistently in tests and runner. ✓
- `Stage4Aggregator.aggregate()` signature: `(annotations: list[PersonaAnnotation]) -> AggregatorVerdict`. Used consistently. ✓
- `stage3_messages(stage2_text: str, retry_notes: str = "") -> list[dict]`. Existing callers in `runner.py` pass only `stage2_text` (default `retry_notes=""` — backward compatible). ✓
- `settings.stage4_max_retries` referenced in runner.py and test file. Defined in `config.py` Task 2. ✓

---

## Summary of Files Touched

| File | Action |
|------|--------|
| `app/backend/pyproject.toml` | +2 deps |
| `app/backend/app/config.py` | +5 settings |
| `app/backend/app/pipeline/stage4_reader.py` | New (250 lines) |
| `app/backend/app/pipeline/stage4_aggregator.py` | New (200 lines) |
| `app/backend/app/pipeline/runner.py` | +Stage 4 retry block (~60 lines) |
| `app/backend/app/pipeline/prompts.py` | +retry_notes param to stage3_messages |
| `app/backend/tests/test_stage4_config.py` | New (5 tests) |
| `app/backend/tests/test_stage4_reader.py` | New (6 tests) |
| `app/backend/tests/test_stage4_aggregator.py` | New (5 tests) |
| `app/backend/tests/test_stage4_retry_loop.py` | New (4 tests) |
| `app/backend/tests/test_pipeline.py` | +2 tests |
