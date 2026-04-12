# Stage 4 Retry Mechanism — Two-Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Do NOT execute any phase without explicit "Proceed with Phase X" confirmation from the user.**

**Goal:** Replace the single-path Stage 4 retry loop in `runner_v2.py` with a two-path retry system where the LFM2-24B-A2B Aggregator classifies reader-panel feedback into one of three severities — `ok` / `fix_pass` / `full_retry` — and drives either a Stage 3-only re-polish or a full Stage 1→2→3 re-translation, with per-segment retry budgets and an exhaustion flag.

**Architecture:**
- Segment = `Paragraph` row (canonical segment table in pipeline v2).
- Aggregator condenses all 15×N persona annotations into ONE `SegmentVerdict` per segment (not per sentence).
- The condensed instruction is passed as additional context: into `polish(retry_instruction=...)` for fix-pass, and appended to `rag_context` for full-retry so all five Stage 1 adapters receive it without any adapter-internal changes.
- Retry budgets (`max_fix_pass=2`, `max_full_retry=1`) and counters live in new `paragraphs` columns. When a budget is exhausted the segment is still emitted but `retry_flag=True` is set for manual review.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async (SQLite), Pydantic v2, pytest-asyncio. No frontend or Tauri changes in this plan.

**Scope boundaries (non-negotiable):**
- Do NOT modify Stage 1 adapters (`app/backend/app/pipeline/stage1/adapter_*.py`).
- Do NOT modify Stage 2 merger (`stage2_merger.py`) or Stage 3 polish (`stage3_polish.py`) inference logic.
- Do NOT modify the legacy `runner.py` retry loop or its `AggregatorVerdict` consumers.
- Do NOT touch training scripts, frontend, or any unrelated pipeline code.
- The existing `Stage4Aggregator.aggregate()` method and `AggregatorVerdict` class STAY intact for `runner.py` backward compatibility. We ADD a new segment-level method and model; we do not rename the old ones.

---

## Phase 1 — Current State Audit (READ-ONLY)

This phase contains no code changes. It records what already exists so later phases build on verified facts, not assumptions. The implementer should read each referenced section before starting Phase 2.

### Existing Stage 4 components

**`app/backend/app/pipeline/stage4_reader.py` (173 lines)**
- 15-persona list: `PERSONAS` constant (Purist, Stilist, Charakter-Tracker, Yuri-Leser, Casual-Reader, Grammatik-Checker, Pacing-Leser, Dialog-Checker, Atmosphären-Leser, Subtext-Leser, Kultureller-Kontext, Honorific-Checker, Namen-Tracker, Emotionaler-Ton, Light-Novel-Leser).
- `PersonaAnnotation` Pydantic model: `persona`, `sentence_id`, `rating` (float 0–1), `issues: list[str]`, `suggestion: str`.
- `Stage4Reader.review(sentences, source_sentences)` iterates every sentence × every persona sequentially; returns `list[PersonaAnnotation]` of length `N_sentences × 15`.
- Model load: Qwen3.5-2B via Unsloth NF4 (`load_in_4bit=True`, `enable_thinking=False`).
- **No retry logic lives here.**

**`app/backend/app/pipeline/stage4_aggregator.py` (148 lines)**
- `AggregatorVerdict` Pydantic model (lines 47–51): `sentence_id: int`, `verdict: Literal["okay", "retry"]`, `retry_instruction: str | None`, `confidence: float`.
- System prompt (`_AGGREGATOR_SYSTEM`, lines 12–31) uses a numeric heuristic (`mean rating >= 0.70 → okay, else retry`) — NOT the severity taxonomy.
- `aggregate(annotations)` (lines 140–147) takes annotations for ONE sentence, returns ONE `AggregatorVerdict`.
- Model load: LFM2-24B-A2B via transformers bnb int4 with `trust_remote_code=True`.

**`app/backend/app/pipeline/runner_v2.py` (300 lines)**
- Single retry loop (lines 194–278).
- `MAX_STAGE4_RETRIES = 3` constant (line 47).
- Per-sentence aggregation: groupby sentence_id, `aggregator.aggregate(group)` per sentence (lines 219–224).
- Any `verdict == "retry"` triggers a Stage-3-only re-polish via `_stage3.polish(merged, glossary_context, retry_instruction=retry_instruction)` where `retry_instruction = " | ".join([s{sid}] v.retry_instruction for v in retry_verdicts)`.
- **No severity branching, no full-pipeline retry, no per-segment counters persisted.**
- `_checkpoint_segment(paragraph_id, final_text, confidence_log)` (lines 50–121) writes `Paragraph.translated_text / is_translated / translated_at` and a synthetic `SourceText` + `Translation` row for confidence logging.

**WebSocket event contract (runner_v2.py lines 10–20):**
```
preprocess_complete, segment_start, stage1_complete, stage2_complete,
stage3_complete, stage4_verdict{verdict, retry_count}, segment_complete,
pipeline_complete, pipeline_error, None-sentinel
```
This docstring WILL be updated in Phase 4/5/6 as new event shapes land.

**`app/backend/app/pipeline/dry_run.py` (156 lines)**
- `DryRunStage4Aggregator.aggregate()` always returns `verdict="okay"`. Needs a new `aggregate_segment()` method that mirrors the production API for HIME_DRY_RUN=1 runs.

### Database

**`app/backend/app/models.py`**
- `Paragraph` (lines 90–104) has `is_translated`, `translated_text`, `verification_result`, `is_reviewed`, `reviewer_notes` — no retry/verdict fields.
- `Translation` (lines 27–55) has `confidence_log`, `current_stage` — no retry fields.

**`app/backend/app/database.py`**
- `init_db()` applies inline ALTER TABLE ADD COLUMN migrations via lists like `_V121_PARAGRAPH_COLS` (lines 42–47). New migrations follow the same pattern.

### Pre-existing stage-3 retry plumbing we will reuse as-is

- `stage3_polish.polish(merged, glossary_context, retry_instruction: str = "")` (lines 117–195) already accepts and injects a retry instruction via `polish_messages(..., retry_instruction=...)` in `app/backend/app/pipeline/prompts.py:244–268`. **No Stage 3 changes required for fix-pass.**
- Stage 3 loads AND unloads its model internally (lines 150–195). Do not add redundant external unload calls around it.

### Pre-existing stage-1 plumbing and the extension point

- `stage1/runner.py` `run_stage1(segment, rag_context, glossary_context, notes="")` — feeds all five adapters.
- Every adapter injects `rag_context` verbatim into its system prompt. **Therefore: appending the condensed retry instruction to `rag_context` is the minimal-invasive way to propagate it through Stage 1.** We will NOT touch the adapters.

### Decision log (lock in before Phase 2)

1. **Column location = `paragraphs` table.** The task wording "or equivalent segment table" permits this. Paragraph is the canonical per-segment record in runner_v2; the synthetic per-segment Translation row is only a logging artifact. All five new columns live on Paragraph.

2. **New class `SegmentVerdict`** (alongside the existing `AggregatorVerdict`). Fields: `verdict: Literal["ok", "fix_pass", "full_retry"]`, `instruction: str` (empty string when `verdict == "ok"`). No `sentence_id`, no `confidence` — the spec only names `verdict` and `instruction`.

3. **New method `aggregate_segment(annotations)`** on `Stage4Aggregator`, taking the full list of `N_sentences × 15` persona annotations for ONE segment and returning ONE `SegmentVerdict`. The old per-sentence `aggregate()` stays untouched for `runner.py`.

4. **Old `AggregatorVerdict.retry_instruction` field name stays.** Do not rename it. Only the new `SegmentVerdict.instruction` matches the spec.

5. **Full-retry rag-context injection.** The condensed instruction is appended to `rag_context` inside a clearly labelled section `[Retry instruction from prior review]: ...` before calling `run_stage1()`. No adapter-internal changes.

6. **Budgets.** `MAX_FIX_PASS = 2`, `MAX_FULL_RETRY = 1` per segment, as module-level constants in `runner_v2.py`. The counters are independent: a full_retry that is then judged to need a fix_pass uses the fix_pass budget, not the full_retry budget. This natural independence falls out of the while-loop design.

7. **VRAM dance on every cycle.** Reader and Aggregator are both loaded/unloaded inside every loop iteration (not once per segment). This is simpler and strictly VRAM-safer than the current runner_v2 layout. Stage 3 and Stage 1 remain responsible for their own load/unload.

---

## Phase 2 — Database schema + migration + checkpoint extension

**Files:**
- Modify: `app/backend/app/models.py:90-104`
- Modify: `app/backend/app/database.py:42-100`
- Modify: `app/backend/app/pipeline/runner_v2.py:50-121` (extend `_checkpoint_segment` signature only — do not use the new args yet)
- Create: `app/backend/tests/test_paragraph_retry_columns.py`

### Task 2.1: Add five new columns to the Paragraph ORM

- [ ] **Step 1: Write the failing test**

Create `app/backend/tests/test_paragraph_retry_columns.py`:

```python
"""Phase 2 — verify new retry-tracking columns on the paragraphs table."""
from __future__ import annotations

import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_paragraph_model_has_retry_fields():
    from app.models import Paragraph
    for col in (
        "retry_count_fix_pass",
        "retry_count_full_pipeline",
        "retry_flag",
        "aggregator_verdict",
        "aggregator_instruction",
    ):
        assert hasattr(Paragraph, col), f"Paragraph is missing column {col}"


@pytest.mark.asyncio
async def test_paragraph_retry_defaults(db_session):
    from app.models import Book, Chapter, Paragraph

    book = Book(title="t", file_path="t.epub")
    db_session.add(book)
    await db_session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=0, title="c")
    db_session.add(chapter)
    await db_session.flush()
    para = Paragraph(chapter_id=chapter.id, paragraph_index=0, source_text="x")
    db_session.add(para)
    await db_session.flush()
    await db_session.refresh(para)

    assert para.retry_count_fix_pass == 0
    assert para.retry_count_full_pipeline == 0
    assert para.retry_flag is False
    assert para.aggregator_verdict is None
    assert para.aggregator_instruction is None


@pytest.mark.asyncio
async def test_migration_adds_retry_columns_to_existing_db(db_session):
    rows = (await db_session.execute(text("PRAGMA table_info(paragraphs)"))).fetchall()
    existing = {r[1] for r in rows}
    for col in (
        "retry_count_fix_pass",
        "retry_count_full_pipeline",
        "retry_flag",
        "aggregator_verdict",
        "aggregator_instruction",
    ):
        assert col in existing, f"paragraphs table is missing column {col} after migration"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app/backend && uv run pytest tests/test_paragraph_retry_columns.py -v`
Expected: FAIL — attribute errors because columns do not yet exist.

- [ ] **Step 3: Add the columns to `models.py`**

In `app/backend/app/models.py` inside the `Paragraph` class, after `reviewer_notes` (line 103) and before the `chapter` relationship (line 104), add:

```python
    # v2.0.0 — Stage 4 retry mechanism
    retry_count_fix_pass: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    retry_count_full_pipeline: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    retry_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    aggregator_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    aggregator_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Add the inline migration to `database.py`**

In `app/backend/app/database.py` after the `_V121_TRANSLATION_COLS` list (around line 56), add:

```python
_V200_PARAGRAPH_RETRY_COLS = [
    ("retry_count_fix_pass",      "INTEGER NOT NULL DEFAULT 0"),
    ("retry_count_full_pipeline", "INTEGER NOT NULL DEFAULT 0"),
    ("retry_flag",                "BOOLEAN NOT NULL DEFAULT 0"),
    ("aggregator_verdict",        "TEXT"),
    ("aggregator_instruction",    "TEXT"),
]
```

Then inside `init_db()` after the existing `_V121_PARAGRAPH_COLS` loop (around line 88), add:

```python
        # v2.0.0: paragraph retry-tracking columns (Stage 4 two-path retry)
        rows_par2 = (await conn.execute(text("PRAGMA table_info(paragraphs)"))).fetchall()
        existing_par2 = {r[1] for r in rows_par2}
        for col, dtype in _V200_PARAGRAPH_RETRY_COLS:
            if col not in existing_par2:
                await conn.execute(text(f"ALTER TABLE paragraphs ADD COLUMN {col} {dtype}"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app/backend && uv run pytest tests/test_paragraph_retry_columns.py -v`
Expected: PASS — 3 tests green.

- [ ] **Step 6: Commit**

```bash
git add app/backend/app/models.py app/backend/app/database.py app/backend/tests/test_paragraph_retry_columns.py
git commit -m "feat(db): add Stage 4 retry-tracking columns to paragraphs"
```

### Task 2.2: Extend `_checkpoint_segment` signature (keyword-only, all defaulting None)

- [ ] **Step 1: Modify `_checkpoint_segment` in `runner_v2.py`**

Replace the signature at `app/backend/app/pipeline/runner_v2.py:50-54` with:

```python
async def _checkpoint_segment(
    paragraph_id: int,
    final_text: str,
    confidence_log: dict | None,
    *,
    retry_count_fix_pass: int | None = None,
    retry_count_full_pipeline: int | None = None,
    retry_flag: bool | None = None,
    aggregator_verdict: str | None = None,
    aggregator_instruction: str | None = None,
) -> None:
    """Persist a completed segment translation using its own AsyncSessionLocal session."""
```

Inside the function body, after `paragraph.translated_at = datetime.now(UTC)` (around line 65), add:

```python
        if retry_count_fix_pass is not None:
            paragraph.retry_count_fix_pass = retry_count_fix_pass
        if retry_count_full_pipeline is not None:
            paragraph.retry_count_full_pipeline = retry_count_full_pipeline
        if retry_flag is not None:
            paragraph.retry_flag = retry_flag
        if aggregator_verdict is not None:
            paragraph.aggregator_verdict = aggregator_verdict
        if aggregator_instruction is not None:
            paragraph.aggregator_instruction = aggregator_instruction
```

All five keyword args default to `None`, so the existing call site in Phase 2 continues to work unchanged. Phases 4–6 will start passing real values.

- [ ] **Step 2: Verify existing tests still pass**

Run: `cd app/backend && uv run pytest tests/test_runner_v2.py tests/test_runner_v2_stage4_load.py -v`
Expected: PASS — no regressions.

- [ ] **Step 3: Commit**

```bash
git add app/backend/app/pipeline/runner_v2.py
git commit -m "feat(runner_v2): extend _checkpoint_segment with retry-tracking kwargs"
```

---

## Phase 3 — Aggregator segment-level verdict + severity taxonomy system prompt

**Files:**
- Modify: `app/backend/app/pipeline/stage4_aggregator.py`
- Modify: `app/backend/app/pipeline/dry_run.py` (add `aggregate_segment` to dry-run stub)
- Create: `app/backend/tests/test_stage4_aggregator_segment.py`

The existing `aggregate()` / `AggregatorVerdict` / `_AGGREGATOR_SYSTEM` all stay — we only ADD new artifacts.

### Task 3.1: Add `SegmentVerdict` Pydantic model and segment-level system prompt

- [ ] **Step 1: Write the failing test**

Create `app/backend/tests/test_stage4_aggregator_segment.py`:

```python
"""Phase 3 — segment-level Stage 4 aggregator with severity taxonomy."""
from __future__ import annotations
import json
from unittest.mock import MagicMock
import pytest

from app.pipeline.stage4_aggregator import Stage4Aggregator
from app.pipeline.stage4_reader import PERSONAS, PersonaAnnotation


def _annotations_for_sentences(n_sentences: int, *, rating: float, issues: list[str] | None = None) -> list[PersonaAnnotation]:
    out: list[PersonaAnnotation] = []
    for sid in range(n_sentences):
        for persona, _ in PERSONAS:
            out.append(
                PersonaAnnotation(
                    persona=persona,
                    sentence_id=sid,
                    rating=rating,
                    issues=list(issues or []),
                    suggestion="",
                )
            )
    return out


def _aggregator_with_output(output_text: str) -> Stage4Aggregator:
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


def test_segment_verdict_model_has_correct_literal():
    from app.pipeline.stage4_aggregator import SegmentVerdict
    v = SegmentVerdict(verdict="ok", instruction="")
    assert v.verdict == "ok"
    v2 = SegmentVerdict(verdict="fix_pass", instruction="tighten pacing")
    assert v2.verdict == "fix_pass"
    v3 = SegmentVerdict(verdict="full_retry", instruction="rewrite; wrong speaker")
    assert v3.verdict == "full_retry"
    with pytest.raises(Exception):
        SegmentVerdict(verdict="retry", instruction="")  # type: ignore[arg-type]


def test_system_prompt_contains_severity_taxonomy():
    from app.pipeline.stage4_aggregator import _SEGMENT_AGGREGATOR_SYSTEM
    p = _SEGMENT_AGGREGATOR_SYSTEM
    # light-error triggers
    for phrase in ("style", "register", "flow", "punctuation", "honorific"):
        assert phrase in p.lower(), f"light-error trigger '{phrase}' missing from prompt"
    # heavy-error triggers
    for phrase in ("wrong meaning", "missing", "wrong speaker", "hallucinat", "wrong character name"):
        assert phrase in p.lower(), f"heavy-error trigger '{phrase}' missing from prompt"
    # verdict literals
    assert '"ok"' in p
    assert '"fix_pass"' in p
    assert '"full_retry"' in p


@pytest.mark.asyncio
async def test_aggregate_segment_ok_verdict():
    from app.pipeline.stage4_aggregator import SegmentVerdict
    out = json.dumps({"verdict": "ok", "instruction": ""})
    agg = _aggregator_with_output(out)
    verdict = await agg.aggregate_segment(_annotations_for_sentences(2, rating=0.9))
    assert isinstance(verdict, SegmentVerdict)
    assert verdict.verdict == "ok"
    assert verdict.instruction == ""


@pytest.mark.asyncio
async def test_aggregate_segment_fix_pass_verdict():
    out = json.dumps({"verdict": "fix_pass", "instruction": "Tighten the dialogue rhythm and use consistent honorifics."})
    agg = _aggregator_with_output(out)
    verdict = await agg.aggregate_segment(_annotations_for_sentences(3, rating=0.4, issues=["awkward flow", "honorific drift"]))
    assert verdict.verdict == "fix_pass"
    assert "honorific" in verdict.instruction.lower()


@pytest.mark.asyncio
async def test_aggregate_segment_full_retry_verdict():
    out = json.dumps({"verdict": "full_retry", "instruction": "Re-translate: speaker attribution is wrong in sentence 1."})
    agg = _aggregator_with_output(out)
    verdict = await agg.aggregate_segment(_annotations_for_sentences(2, rating=0.2, issues=["wrong speaker", "missing clause"]))
    assert verdict.verdict == "full_retry"
    assert "speaker" in verdict.instruction.lower()


@pytest.mark.asyncio
async def test_aggregate_segment_parse_error_falls_back_to_ok():
    agg = _aggregator_with_output("NOT JSON AT ALL")
    verdict = await agg.aggregate_segment(_annotations_for_sentences(1, rating=0.5))
    assert verdict.verdict == "ok"
    assert verdict.instruction == ""


@pytest.mark.asyncio
async def test_aggregate_segment_user_prompt_contains_all_sentences(monkeypatch):
    captured: list[str] = []
    out = json.dumps({"verdict": "ok", "instruction": ""})
    agg = _aggregator_with_output(out)

    def capture_apply(messages, **kw):
        for m in messages:
            captured.append(m["content"])
        return "ENCODED"

    agg._tokenizer.apply_chat_template = capture_apply
    await agg.aggregate_segment(_annotations_for_sentences(3, rating=0.8))
    joined = "\n".join(captured)
    assert "Sentence 0" in joined
    assert "Sentence 1" in joined
    assert "Sentence 2" in joined


@pytest.mark.asyncio
async def test_aggregate_segment_empty_annotations_returns_ok():
    from app.pipeline.stage4_aggregator import SegmentVerdict
    agg = _aggregator_with_output(json.dumps({"verdict": "ok", "instruction": ""}))
    verdict = await agg.aggregate_segment([])
    assert isinstance(verdict, SegmentVerdict)
    assert verdict.verdict == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app/backend && uv run pytest tests/test_stage4_aggregator_segment.py -v`
Expected: FAIL — `SegmentVerdict`, `_SEGMENT_AGGREGATOR_SYSTEM`, and `aggregate_segment` do not yet exist.

- [ ] **Step 3: Add `SegmentVerdict` and the new system prompt to `stage4_aggregator.py`**

In `app/backend/app/pipeline/stage4_aggregator.py` after the existing `_AGGREGATOR_SYSTEM` constant (after line 31), add:

```python
_SEGMENT_AGGREGATOR_SYSTEM = """\
You are the final quality aggregator for a JP->EN light novel translation review system.
You receive structured feedback from 15 specialist reader-critic personas about ONE
translated segment (a paragraph, possibly containing multiple sentences).

Your task has TWO parts:

1. CONDENSE — synthesise all the reader feedback into ONE coherent, actionable retry
   instruction. ONE sentence, maximum 60 words, in English. Do NOT list raw annotations
   or persona names; do NOT output bullet points. Speak directly to the translator:
   "Rewrite ...", "Fix ...", "Preserve ...". If the segment is acceptable, return an
   empty string for the instruction.

2. CLASSIFY severity using this exact taxonomy:

   "ok"         -> No issue. Translation is acceptable as-is. Emit instruction="".

   "fix_pass"   -> LIGHT error. Triggers a Stage 3 polish re-run only. Use this verdict
                   when the reader feedback reports ONLY surface-level problems that do
                   not change meaning:
                     - style or register inconsistencies
                     - sentence flow or rhythm problems
                     - punctuation or dialogue-formatting mistakes
                     - honorific inconsistency (missing/extra/wrong honorific suffix)
                     - minor phrasing awkwardness

   "full_retry" -> HEAVY error. Triggers a full Stage 1 -> Stage 2 -> Stage 3
                   re-translation. Use this verdict when ANY reader reports:
                     - wrong meaning or mistranslated clause
                     - missing sentence, clause, or paragraph (omission)
                     - added or hallucinated content not present in the Japanese source
                     - wrong speaker attributed to dialogue
                     - wrong character name, place name, or other glossary term

   If both light AND heavy errors are present in the feedback, always classify as
   "full_retry". Heavy errors dominate.

Respond ONLY with a single JSON object (no markdown fences, no explanation, no prose):
{
  "verdict": "ok" | "fix_pass" | "full_retry",
  "instruction": "<one-sentence actionable retry instruction, or empty string if verdict is ok>"
}"""
```

Then add the `SegmentVerdict` model after the existing `AggregatorVerdict` class (after line 51):

```python
class SegmentVerdict(BaseModel):
    """Segment-level verdict from the Stage 4 aggregator.

    Produced once per segment by aggregate_segment(). Drives the two-path retry
    system in runner_v2.
    """
    verdict: Literal["ok", "fix_pass", "full_retry"]
    instruction: str
```

- [ ] **Step 4: Add the `_build_segment_user_prompt` helper and `aggregate_segment` method**

After the existing `_build_user_prompt` function (around line 44), add:

```python
def _build_segment_user_prompt(annotations: list[PersonaAnnotation]) -> str:
    """Render all N_sentences x 15 persona annotations for one segment."""
    if not annotations:
        return "No reader annotations provided."
    from itertools import groupby
    sorted_ann = sorted(annotations, key=lambda a: a.sentence_id)
    lines: list[str] = []
    for sid, group in groupby(sorted_ann, key=lambda a: a.sentence_id):
        group_list = list(group)
        lines.append(f"--- Sentence {sid} ---")
        for a in group_list:
            issues_str = "; ".join(a.issues) if a.issues else "none"
            lines.append(
                f"[{a.persona}] rating={a.rating:.2f} "
                f"issues=[{issues_str}] suggestion={a.suggestion!r}"
            )
        mean = sum(a.rating for a in group_list) / len(group_list)
        lines.append(f"Sentence {sid} mean rating: {mean:.3f}")
        lines.append("")
    overall = sum(a.rating for a in annotations) / len(annotations)
    lines.append(f"Overall segment mean rating: {overall:.3f}")
    return "\n".join(lines)
```

Inside the `Stage4Aggregator` class, after the existing `aggregate()` method (after line 147), add:

```python
    def _parse_segment_verdict(self, raw: str) -> SegmentVerdict:
        text = raw.strip()
        if text.startswith("```"):
            ls = text.splitlines()
            text = "\n".join(ls[1:-1] if ls[-1].strip() == "```" else ls[1:]).strip()
        try:
            data = json.loads(text)
            verdict = data.get("verdict", "ok")
            if verdict not in ("ok", "fix_pass", "full_retry"):
                _log.warning("[Stage4Aggregator] unknown verdict %r, defaulting to ok", verdict)
                verdict = "ok"
            instruction = str(data.get("instruction") or "")
            return SegmentVerdict(verdict=verdict, instruction=instruction)
        except Exception:  # noqa: BLE001
            _log.warning("[Stage4Aggregator] segment parse error — defaulting to ok")
            return SegmentVerdict(verdict="ok", instruction="")

    def _infer_segment(self, user_prompt: str) -> str:
        """Like _infer_one but uses the segment-level system prompt."""
        import contextlib
        import torch  # type: ignore[import]
        messages = [
            {"role": "system", "content": _SEGMENT_AGGREGATOR_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        raw_inputs = self._tokenizer(text, return_tensors="pt")
        inputs = raw_inputs.to(self._model.device) if hasattr(raw_inputs, "to") else raw_inputs
        _no_grad = torch.no_grad if hasattr(torch, "no_grad") else contextlib.nullcontext
        with _no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.1,
                do_sample=True,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        input_ids = inputs["input_ids"]
        input_len = input_ids.shape[1] if hasattr(input_ids, "shape") else len(input_ids[0])
        new_tokens = output_ids[0][input_len:]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True)

    async def aggregate_segment(self, annotations: list[PersonaAnnotation]) -> SegmentVerdict:
        """Condense all N_sentences x 15 persona annotations into ONE SegmentVerdict.

        Unlike aggregate() which runs per-sentence, this method takes the full
        segment's feedback and classifies overall severity using the error taxonomy.
        """
        if not annotations:
            return SegmentVerdict(verdict="ok", instruction="")
        user_prompt = _build_segment_user_prompt(annotations)
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._infer_segment, user_prompt)
        return self._parse_segment_verdict(raw)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app/backend && uv run pytest tests/test_stage4_aggregator_segment.py tests/test_stage4_aggregator.py -v`
Expected: PASS — new tests green AND existing aggregator tests still green (old `aggregate()` and `AggregatorVerdict` untouched).

- [ ] **Step 6: Commit**

```bash
git add app/backend/app/pipeline/stage4_aggregator.py app/backend/tests/test_stage4_aggregator_segment.py
git commit -m "feat(stage4): add segment-level aggregator with severity taxonomy"
```

### Task 3.2: Extend `DryRunStage4Aggregator` with an `aggregate_segment` method

- [ ] **Step 1: Write the failing test**

Append to `app/backend/tests/test_stage4_aggregator_segment.py`:

```python
@pytest.mark.asyncio
async def test_dry_run_aggregate_segment_returns_ok():
    from app.pipeline.dry_run import DryRunStage4Aggregator
    from app.pipeline.stage4_aggregator import SegmentVerdict
    agg = DryRunStage4Aggregator()
    verdict = await agg.aggregate_segment(_annotations_for_sentences(2, rating=0.9))
    assert isinstance(verdict, SegmentVerdict)
    assert verdict.verdict == "ok"
    assert verdict.instruction == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/backend && uv run pytest tests/test_stage4_aggregator_segment.py::test_dry_run_aggregate_segment_returns_ok -v`
Expected: FAIL — `aggregate_segment` not defined on `DryRunStage4Aggregator`.

- [ ] **Step 3: Add `aggregate_segment` to `DryRunStage4Aggregator`**

In `app/backend/app/pipeline/dry_run.py`, at the top of the file update the import (around line 17):

```python
from .stage4_aggregator import AggregatorVerdict, SegmentVerdict
```

Inside `DryRunStage4Aggregator` (after the existing `aggregate()` method around line 147), add:

```python
    async def aggregate_segment(self, annotations: list[PersonaAnnotation]) -> SegmentVerdict:
        await asyncio.sleep(0)
        return SegmentVerdict(verdict="ok", instruction="")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app/backend && uv run pytest tests/test_stage4_aggregator_segment.py tests/test_pipeline_dry_run.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/backend/app/pipeline/dry_run.py app/backend/tests/test_stage4_aggregator_segment.py
git commit -m "feat(dry_run): add aggregate_segment to DryRunStage4Aggregator"
```

---

## Phase 4 — Fix-Pass retry path in runner_v2

**Files:**
- Modify: `app/backend/app/pipeline/runner_v2.py` (rewrite Stage 4 retry loop)
- Create: `app/backend/tests/test_runner_v2_retry_paths.py`

This phase replaces the existing single-path retry loop with a while-loop dispatch that recognises `ok` and `fix_pass` verdicts. The `full_retry` verdict is detected but not yet implemented — it is treated as an early break in this phase, and Phase 5 fills in the Stage 1→2→3 re-run branch. This keeps each phase independently testable.

### Task 4.1: Introduce retry-budget constants and a helper for rag-context augmentation

- [ ] **Step 1: Add module-level constants and helper**

In `app/backend/app/pipeline/runner_v2.py`, replace `MAX_STAGE4_RETRIES = 3` (line 47) with:

```python
# Stage 4 retry budgets (per segment, independent)
MAX_FIX_PASS_RETRIES = 2
MAX_FULL_PIPELINE_RETRIES = 1


def _augment_rag_with_retry(rag_context: str, instruction: str) -> str:
    """Append a retry instruction to rag_context as a clearly-labelled section.

    This is how the condensed segment instruction reaches Stage 1 on a full
    pipeline retry — without touching any adapter code.
    """
    if not instruction.strip():
        return rag_context
    note = f"[Retry instruction from prior review]: {instruction.strip()}"
    if rag_context.strip():
        return f"{rag_context}\n\n{note}"
    return note
```

### Task 4.2: Rewrite the Stage 4 retry loop to dispatch on the segment verdict

- [ ] **Step 1: Write the failing test (fix-pass path)**

Create `app/backend/tests/test_runner_v2_retry_paths.py`:

```python
"""Phase 4/5/6 — two-path Stage 4 retry integration tests for runner_v2."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.pipeline.stage4_aggregator import SegmentVerdict
from app.pipeline.stage4_reader import PERSONAS, PersonaAnnotation


@dataclass
class FakeSegment:
    paragraph_id: int
    source_jp: str
    mecab_tokens: list
    glossary_context: str
    rag_context: str


def _ok_annotations(n_sentences: int = 1) -> list[PersonaAnnotation]:
    out: list[PersonaAnnotation] = []
    for sid in range(n_sentences):
        for name, _ in PERSONAS:
            out.append(PersonaAnnotation(persona=name, sentence_id=sid, rating=0.9, issues=[], suggestion=""))
    return out


async def _drain(q: asyncio.Queue) -> list[dict]:
    events: list[dict] = []
    while True:
        item = await q.get()
        if item is None:
            break
        events.append(item)
    return events


def _make_fake_drafts(tag: str = "v1"):
    drafts = MagicMock()
    drafts.qwen32b = f"[{tag}] draft"
    drafts.translategemma12b = None
    drafts.qwen35_9b = None
    drafts.gemma4_e4b = None
    drafts.jmdict = ""
    return drafts


@pytest.fixture
def fake_segment():
    return FakeSegment(
        paragraph_id=42,
        source_jp="彼女は静かに微笑んだ。",
        mecab_tokens=[],
        glossary_context="",
        rag_context="[prior passage] she was smiling",
    )


@pytest.fixture
def patched_pipeline(fake_segment):
    """Patch preprocessor + all stage entrypoints + checkpoint inside runner_v2."""
    import contextlib

    @contextlib.contextmanager
    def _ctx(
        *,
        verdict_sequence: list[SegmentVerdict],
        stage3_outputs: list[str] | None = None,
        stage2_outputs: list[str] | None = None,
        stage1_outputs: list | None = None,
    ):
        stage3_outputs = stage3_outputs or ["polished v1", "polished v2", "polished v3"]
        stage2_outputs = stage2_outputs or ["merged v1", "merged v2"]
        stage1_outputs = stage1_outputs or [_make_fake_drafts("v1"), _make_fake_drafts("v2")]

        stage1_mock = AsyncMock(side_effect=stage1_outputs)
        stage2_mock = AsyncMock(side_effect=stage2_outputs)
        stage3_mock = AsyncMock(side_effect=stage3_outputs)

        reader_mock = MagicMock()
        reader_mock.load = MagicMock()
        reader_mock.unload = MagicMock()
        reader_mock.review = AsyncMock(return_value=_ok_annotations())

        aggregator_mock = MagicMock()
        aggregator_mock.load = MagicMock()
        aggregator_mock.unload = MagicMock()
        aggregator_mock.aggregate_segment = AsyncMock(side_effect=verdict_sequence)

        checkpoint_calls: list[dict] = []
        async def fake_checkpoint(paragraph_id, final_text, confidence_log, **kwargs):
            checkpoint_calls.append({
                "paragraph_id": paragraph_id,
                "final_text": final_text,
                "confidence_log": confidence_log,
                **kwargs,
            })

        async def fake_preprocess(book_id, session):
            return [fake_segment]

        export_mock = AsyncMock(return_value="/tmp/fake.epub")

        with (
            patch("app.pipeline.runner_v2._preprocessor.preprocess_book", fake_preprocess),
            patch("app.pipeline.runner_v2._stage1.run_stage1", stage1_mock),
            patch("app.pipeline.runner_v2._stage2.merge", stage2_mock),
            patch("app.pipeline.runner_v2._stage3.polish", stage3_mock),
            patch("app.pipeline.runner_v2.Stage4Reader", return_value=reader_mock),
            patch("app.pipeline.runner_v2.Stage4Aggregator", return_value=aggregator_mock),
            patch("app.pipeline.runner_v2._checkpoint_segment", side_effect=fake_checkpoint),
            patch("app.pipeline.runner_v2.export_book", export_mock),
        ):
            yield {
                "stage1": stage1_mock,
                "stage2": stage2_mock,
                "stage3": stage3_mock,
                "reader": reader_mock,
                "aggregator": aggregator_mock,
                "checkpoints": checkpoint_calls,
            }

    return _ctx


@pytest.mark.asyncio
async def test_fix_pass_triggers_single_stage3_rerun(patched_pipeline):
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="Tighten dialogue rhythm."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        events = await _drain(q)

    # stage3 is called twice: once initial, once for the fix-pass retry
    assert ctx["stage3"].await_count == 2
    # stage1 and stage2 are called exactly once (no full_retry)
    assert ctx["stage1"].await_count == 1
    assert ctx["stage2"].await_count == 1
    # Stage 3 second call receives the condensed instruction
    second_call = ctx["stage3"].call_args_list[1]
    assert second_call.kwargs.get("retry_instruction") == "Tighten dialogue rhythm."
    # Checkpoint reflects one fix-pass retry
    assert len(ctx["checkpoints"]) == 1
    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 1
    assert cp["retry_count_full_pipeline"] == 0
    assert cp["retry_flag"] is False
    assert cp["aggregator_verdict"] == "ok"
    # WS events include both stage4_verdict transitions
    verdict_events = [e for e in events if e.get("event") == "stage4_verdict"]
    assert len(verdict_events) == 2
    assert verdict_events[0]["verdict"] == "fix_pass"
    assert verdict_events[1]["verdict"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app/backend && uv run pytest tests/test_runner_v2_retry_paths.py::test_fix_pass_triggers_single_stage3_rerun -v`
Expected: FAIL — new retry loop not yet implemented.

- [ ] **Step 3: Rewrite the Stage 4 retry section in `run_pipeline_v2`**

In `app/backend/app/pipeline/runner_v2.py`, replace the entire block from line 194 (`retry_count = 0`) through line 280 (the line before `await ws_queue.put({"event": "segment_complete", ...})`), inclusive, with:

```python
            # Stage 4 — two-path retry dispatch
            fix_pass_count = 0
            full_retry_count = 0
            retry_flag_exhausted = False
            current_polished = polished_str
            current_merged = merged_str
            last_verdict: str = "ok"
            last_instruction: str = ""
            confidence_log: dict = {"cycles": []}

            while True:
                # Load + review + unload (reader)
                if dry_run:
                    reader = DryRunStage4Reader()
                    aggregator = DryRunStage4Aggregator()
                else:
                    reader = Stage4Reader()
                    aggregator = Stage4Aggregator()

                sentences = _SENT_SPLIT.split(current_polished.strip()) or [current_polished]
                source_sentences = _SENT_SPLIT.split(segment.source_jp.strip()) or [segment.source_jp]
                if len(source_sentences) < len(sentences):
                    source_sentences += [source_sentences[-1]] * (len(sentences) - len(source_sentences))
                source_sentences = source_sentences[: len(sentences)]

                reader.load(settings)
                annotations = await reader.review(
                    sentences=sentences, source_sentences=source_sentences,
                )
                reader.unload()

                aggregator.load(settings)
                segment_verdict = await aggregator.aggregate_segment(annotations)
                aggregator.unload()

                last_verdict = segment_verdict.verdict
                last_instruction = segment_verdict.instruction
                confidence_log["cycles"].append({
                    "verdict": segment_verdict.verdict,
                    "instruction": segment_verdict.instruction,
                    "fix_pass_count": fix_pass_count,
                    "full_retry_count": full_retry_count,
                })

                await ws_queue.put({
                    "event": "stage4_verdict",
                    "paragraph_id": paragraph_id,
                    "verdict": segment_verdict.verdict,
                    "instruction": segment_verdict.instruction,
                    "fix_pass_count": fix_pass_count,
                    "full_retry_count": full_retry_count,
                })

                if segment_verdict.verdict == "ok":
                    break

                if segment_verdict.verdict == "fix_pass":
                    if fix_pass_count >= MAX_FIX_PASS_RETRIES:
                        retry_flag_exhausted = True
                        _log.warning(
                            "[runner_v2] paragraph %d exhausted fix_pass budget (%d); "
                            "emitting anyway and setting retry_flag",
                            paragraph_id, MAX_FIX_PASS_RETRIES,
                        )
                        break
                    fix_pass_count += 1
                    # Stage 3 re-run with condensed instruction. Stage 3 manages its
                    # own VRAM (load/unload inside polish()); no external calls needed.
                    if dry_run:
                        current_polished = await dry_run_stage3_polish(
                            current_merged,
                            segment.glossary_context,
                            retry_instruction=segment_verdict.instruction,
                        )
                    else:
                        current_polished = await _stage3.polish(
                            current_merged,
                            segment.glossary_context,
                            retry_instruction=segment_verdict.instruction,
                        )
                    await ws_queue.put({
                        "event": "stage3_complete",
                        "paragraph_id": paragraph_id,
                        "retry_kind": "fix_pass",
                        "fix_pass_count": fix_pass_count,
                    })
                    continue

                if segment_verdict.verdict == "full_retry":
                    # Phase 4 stub: detected but not yet implemented. Phase 5 fills this in.
                    _log.warning(
                        "[runner_v2] paragraph %d received full_retry verdict; "
                        "full-retry branch not yet wired — emitting current output",
                        paragraph_id,
                    )
                    break

                # Defensive: unknown verdict → emit as-is
                _log.warning(
                    "[runner_v2] paragraph %d unknown verdict %r; emitting as-is",
                    paragraph_id, segment_verdict.verdict,
                )
                break

            final_text = current_polished
            await _checkpoint_segment(
                paragraph_id,
                final_text,
                confidence_log,
                retry_count_fix_pass=fix_pass_count,
                retry_count_full_pipeline=full_retry_count,
                retry_flag=retry_flag_exhausted,
                aggregator_verdict=last_verdict,
                aggregator_instruction=last_instruction,
            )
```

Also delete the now-unused `from itertools import groupby` import at the top of the file if it is no longer referenced, and remove the now-unused `MAX_STAGE4_RETRIES` constant if you have not already replaced it in Task 4.1.

- [ ] **Step 4: Update the WS-event contract docstring**

In `app/backend/app/pipeline/runner_v2.py` replace lines 10–20 of the module docstring with:

```
WebSocket event contract:
  {"event": "preprocess_complete", "segment_count": N}
  {"event": "segment_start", "paragraph_id": id, "index": i, "total": N}
  {"event": "stage1_complete", "paragraph_id": id, "retry_kind"?: "full_retry"}
  {"event": "stage2_complete", "paragraph_id": id, "retry_kind"?: "full_retry"}
  {"event": "stage3_complete", "paragraph_id": id, "retry_kind"?: "fix_pass"|"full_retry",
                               "fix_pass_count"?: int, "full_retry_count"?: int}
  {"event": "stage4_verdict", "paragraph_id": id,
                              "verdict": "ok"|"fix_pass"|"full_retry",
                              "instruction": str,
                              "fix_pass_count": int, "full_retry_count": int}
  {"event": "segment_complete", "paragraph_id": id, "translation": text,
                                "retry_flag": bool}
  {"event": "pipeline_complete", "epub_path": str}
  {"event": "pipeline_error", "detail": str}
  None  <- sentinel
```

Then add `"retry_flag": retry_flag_exhausted,` to the existing `segment_complete` emission (currently around the old line 282–286).

- [ ] **Step 5: Run the fix-pass test and verify it passes**

Run: `cd app/backend && uv run pytest tests/test_runner_v2_retry_paths.py::test_fix_pass_triggers_single_stage3_rerun -v`
Expected: PASS.

Also run the existing runner_v2 tests to confirm no regression:

Run: `cd app/backend && uv run pytest tests/test_runner_v2.py tests/test_runner_v2_stage4_load.py tests/test_pipeline_dry_run.py -v`
Expected: PASS — note that `test_runner_v2_stage4_load.py` asserts `aggregator.load(settings)` and `aggregator.unload()` appear in the source; both still do.

- [ ] **Step 6: Commit**

```bash
git add app/backend/app/pipeline/runner_v2.py app/backend/tests/test_runner_v2_retry_paths.py
git commit -m "feat(runner_v2): two-path Stage 4 retry dispatch — fix_pass branch"
```

---

## Phase 5 — Full Pipeline Retry path (Stage 1 → 2 → 3)

**Files:**
- Modify: `app/backend/app/pipeline/runner_v2.py` (replace the Phase 4 `full_retry` stub with the real branch)
- Modify: `app/backend/tests/test_runner_v2_retry_paths.py` (add full-retry test)

### Task 5.1: Implement the full_retry branch in the while-loop

- [ ] **Step 1: Write the failing test (full-retry path)**

Append to `app/backend/tests/test_runner_v2_retry_paths.py`:

```python
@pytest.mark.asyncio
async def test_full_retry_triggers_stage1_to_stage3_rerun(patched_pipeline, fake_segment):
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="full_retry", instruction="Re-translate: speaker wrong in sentence 1."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        events = await _drain(q)

    # Stage 1 and Stage 2 each run TWICE: once originally, once for full-retry
    assert ctx["stage1"].await_count == 2
    assert ctx["stage2"].await_count == 2
    assert ctx["stage3"].await_count == 2

    # Second Stage 1 call receives the augmented rag_context with the instruction
    second_stage1 = ctx["stage1"].call_args_list[1]
    rag_ctx = second_stage1.kwargs.get("rag_context") or second_stage1.args[1] if second_stage1.args else ""
    # pick whichever argument form was used
    if "rag_context" in second_stage1.kwargs:
        rag_ctx = second_stage1.kwargs["rag_context"]
    assert "Retry instruction from prior review" in rag_ctx
    assert "speaker wrong" in rag_ctx
    # Original rag_context is preserved
    assert "prior passage" in rag_ctx

    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 0
    assert cp["retry_count_full_pipeline"] == 1
    assert cp["retry_flag"] is False
    assert cp["aggregator_verdict"] == "ok"

    # WS events include the re-emitted stage events for the second pass
    stage1_completes = [e for e in events if e.get("event") == "stage1_complete"]
    stage2_completes = [e for e in events if e.get("event") == "stage2_complete"]
    stage3_completes = [e for e in events if e.get("event") == "stage3_complete"]
    assert len(stage1_completes) == 2
    assert len(stage2_completes) == 2
    assert len(stage3_completes) == 2
    # The second set of stage events is tagged retry_kind="full_retry"
    assert any(e.get("retry_kind") == "full_retry" for e in stage1_completes)
    assert any(e.get("retry_kind") == "full_retry" for e in stage2_completes)
    assert any(e.get("retry_kind") == "full_retry" for e in stage3_completes)


@pytest.mark.asyncio
async def test_full_retry_then_fix_pass_uses_both_budgets(patched_pipeline):
    """A full_retry that gets re-judged as fix_pass consumes one of each budget."""
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="full_retry", instruction="Re-translate: missing clause."),
        SegmentVerdict(verdict="fix_pass", instruction="Clean up punctuation."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        await _drain(q)

    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 1
    assert cp["retry_count_full_pipeline"] == 1
    assert cp["retry_flag"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app/backend && uv run pytest tests/test_runner_v2_retry_paths.py::test_full_retry_triggers_stage1_to_stage3_rerun tests/test_runner_v2_retry_paths.py::test_full_retry_then_fix_pass_uses_both_budgets -v`
Expected: FAIL — full_retry branch is still the Phase 4 early-break stub.

- [ ] **Step 3: Replace the Phase 4 full_retry stub with the real branch**

In `app/backend/app/pipeline/runner_v2.py`, locate the `if segment_verdict.verdict == "full_retry":` block added in Phase 4 (the one that currently just logs a warning and breaks) and replace it with:

```python
                if segment_verdict.verdict == "full_retry":
                    if full_retry_count >= MAX_FULL_PIPELINE_RETRIES:
                        retry_flag_exhausted = True
                        _log.warning(
                            "[runner_v2] paragraph %d exhausted full_retry budget (%d); "
                            "emitting anyway and setting retry_flag",
                            paragraph_id, MAX_FULL_PIPELINE_RETRIES,
                        )
                        break
                    full_retry_count += 1
                    # Inject the condensed instruction into rag_context; Stage 1
                    # adapters read rag_context verbatim, so this threads through
                    # all five adapters with zero adapter-internal changes.
                    augmented_rag = _augment_rag_with_retry(
                        segment.rag_context, segment_verdict.instruction,
                    )

                    # Stage 1 — full re-run with augmented context
                    if dry_run:
                        new_drafts = await make_dry_run_stage1_drafts(
                            segment=segment.source_jp,
                            rag_context=augmented_rag,
                            glossary_context=segment.glossary_context,
                        )
                    else:
                        new_drafts = await _stage1.run_stage1(
                            segment=segment.source_jp,
                            rag_context=augmented_rag,
                            glossary_context=segment.glossary_context,
                        )
                    await ws_queue.put({
                        "event": "stage1_complete",
                        "paragraph_id": paragraph_id,
                        "retry_kind": "full_retry",
                        "full_retry_count": full_retry_count,
                    })

                    new_drafts_dict: dict[str, str] = {
                        "qwen32b": new_drafts.qwen32b or "",
                        "translategemma": new_drafts.translategemma12b or "",
                        "qwen35_9b": new_drafts.qwen35_9b or "",
                        "gemma4_e4b": new_drafts.gemma4_e4b or "",
                        "jmdict": new_drafts.jmdict,
                    }

                    # Stage 2 — merge with same augmented rag_context
                    if dry_run:
                        current_merged = await dry_run_stage2_merge(
                            new_drafts_dict, augmented_rag, segment.glossary_context,
                        )
                    else:
                        current_merged = await _stage2.merge(
                            new_drafts_dict, augmented_rag, segment.glossary_context,
                        )
                    await ws_queue.put({
                        "event": "stage2_complete",
                        "paragraph_id": paragraph_id,
                        "retry_kind": "full_retry",
                        "full_retry_count": full_retry_count,
                    })

                    # Stage 3 — fresh polish, NO fix_pass retry_instruction because
                    # the instruction has already flowed through Stage 1 via rag_context.
                    if dry_run:
                        current_polished = await dry_run_stage3_polish(
                            current_merged, segment.glossary_context,
                        )
                    else:
                        current_polished = await _stage3.polish(
                            current_merged, segment.glossary_context,
                        )
                    await ws_queue.put({
                        "event": "stage3_complete",
                        "paragraph_id": paragraph_id,
                        "retry_kind": "full_retry",
                        "full_retry_count": full_retry_count,
                    })
                    continue
```

**Note for the implementer:** because the two counters are independent, a `full_retry` followed later by a `fix_pass` verdict naturally consumes one of each budget. Do NOT add any cross-budget guards — the test `test_full_retry_then_fix_pass_uses_both_budgets` locks this behaviour in.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app/backend && uv run pytest tests/test_runner_v2_retry_paths.py -v`
Expected: PASS — fix_pass, full_retry, and mixed-path tests all green.

Also run the full runner_v2 suite:

Run: `cd app/backend && uv run pytest tests/test_runner_v2.py tests/test_runner_v2_stage4_load.py tests/test_pipeline_dry_run.py -v`
Expected: PASS — no regression.

- [ ] **Step 5: Commit**

```bash
git add app/backend/app/pipeline/runner_v2.py app/backend/tests/test_runner_v2_retry_paths.py
git commit -m "feat(runner_v2): wire full_retry branch (Stage 1->2->3 re-run)"
```

---

## Phase 6 — Retry-limit exhaustion flag + manual-review persistence

**Files:**
- Modify: `app/backend/app/pipeline/runner_v2.py` (add reviewer_notes stamping when `retry_flag` is set)
- Modify: `app/backend/tests/test_runner_v2_retry_paths.py` (add exhaustion tests)

Phases 4 and 5 already wire `retry_flag_exhausted` into `_checkpoint_segment`. This phase adds the exhaustion *observability* — a `reviewer_notes` annotation so the UI's manual-review queue can explain why the flag is set — and explicit test coverage for both exhaustion paths.

### Task 6.1: Stamp `reviewer_notes` when the retry budget is exhausted

- [ ] **Step 1: Write the failing tests**

Append to `app/backend/tests/test_runner_v2_retry_paths.py`:

```python
@pytest.mark.asyncio
async def test_fix_pass_exhaustion_sets_retry_flag(patched_pipeline):
    """After 2 failed fix_pass retries the segment emits with retry_flag=True."""
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="Fix A"),
        SegmentVerdict(verdict="fix_pass", instruction="Fix B"),
        SegmentVerdict(verdict="fix_pass", instruction="Fix C"),  # budget exhausted
    ]
    with patched_pipeline(
        verdict_sequence=verdicts,
        stage3_outputs=["polished v1", "polished v2", "polished v3"],
    ) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        events = await _drain(q)

    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 2  # MAX_FIX_PASS_RETRIES
    assert cp["retry_count_full_pipeline"] == 0
    assert cp["retry_flag"] is True
    # Pipeline completes normally — segment is not blocked
    event_names = [e["event"] for e in events]
    assert "segment_complete" in event_names
    assert "pipeline_complete" in event_names
    seg_complete = next(e for e in events if e["event"] == "segment_complete")
    assert seg_complete["retry_flag"] is True


@pytest.mark.asyncio
async def test_full_retry_exhaustion_sets_retry_flag(patched_pipeline):
    """After 1 failed full_retry the segment emits with retry_flag=True."""
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="full_retry", instruction="Fix wrong speaker"),
        SegmentVerdict(verdict="full_retry", instruction="Still wrong"),  # budget exhausted
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        await _drain(q)

    cp = ctx["checkpoints"][0]
    assert cp["retry_count_fix_pass"] == 0
    assert cp["retry_count_full_pipeline"] == 1  # MAX_FULL_PIPELINE_RETRIES
    assert cp["retry_flag"] is True
    # reviewer_notes gets stamped explaining the exhaustion
    assert cp.get("reviewer_notes") is not None
    assert "retry budget exhausted" in cp["reviewer_notes"].lower()
    assert "Still wrong" in cp["reviewer_notes"]


@pytest.mark.asyncio
async def test_retry_flag_not_set_when_budget_not_exhausted(patched_pipeline):
    from app.pipeline.runner_v2 import run_pipeline_v2
    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="small fix"),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with patched_pipeline(verdict_sequence=verdicts) as ctx:
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=1, ws_queue=q, session=MagicMock())
        await _drain(q)

    cp = ctx["checkpoints"][0]
    assert cp["retry_flag"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app/backend && uv run pytest tests/test_runner_v2_retry_paths.py::test_fix_pass_exhaustion_sets_retry_flag tests/test_runner_v2_retry_paths.py::test_full_retry_exhaustion_sets_retry_flag tests/test_runner_v2_retry_paths.py::test_retry_flag_not_set_when_budget_not_exhausted -v`
Expected: FAIL — the exhaustion path already runs correctly from Phases 4/5, but `reviewer_notes` is not yet stamped, and `segment_complete` may not yet include `retry_flag`.

- [ ] **Step 3: Extend `_checkpoint_segment` to accept and persist `reviewer_notes`**

In `app/backend/app/pipeline/runner_v2.py`, add one more keyword-only arg to `_checkpoint_segment`:

```python
    reviewer_notes: str | None = None,
```

And inside the function body, alongside the other kwargs assignments:

```python
        if reviewer_notes is not None:
            paragraph.reviewer_notes = reviewer_notes
```

- [ ] **Step 4: Stamp `reviewer_notes` and pass `retry_flag` through `segment_complete` in `run_pipeline_v2`**

In `app/backend/app/pipeline/runner_v2.py`, replace the `await _checkpoint_segment(...)` block that was introduced in Phase 4 with:

```python
            reviewer_notes_text: str | None = None
            if retry_flag_exhausted:
                reviewer_notes_text = (
                    f"[Stage 4 retry budget exhausted] "
                    f"last_verdict={last_verdict} "
                    f"fix_pass_count={fix_pass_count}/{MAX_FIX_PASS_RETRIES} "
                    f"full_retry_count={full_retry_count}/{MAX_FULL_PIPELINE_RETRIES} "
                    f"last_instruction={last_instruction!r}"
                )

            final_text = current_polished
            await _checkpoint_segment(
                paragraph_id,
                final_text,
                confidence_log,
                retry_count_fix_pass=fix_pass_count,
                retry_count_full_pipeline=full_retry_count,
                retry_flag=retry_flag_exhausted,
                aggregator_verdict=last_verdict,
                aggregator_instruction=last_instruction,
                reviewer_notes=reviewer_notes_text,
            )
```

And update the `segment_complete` ws_queue emission (previously around line 282) so it includes the flag:

```python
            await ws_queue.put({
                "event": "segment_complete",
                "paragraph_id": paragraph_id,
                "translation": final_text,
                "retry_flag": retry_flag_exhausted,
            })
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app/backend && uv run pytest tests/test_runner_v2_retry_paths.py -v`
Expected: PASS — all Phase 4/5/6 integration tests green.

- [ ] **Step 6: Commit**

```bash
git add app/backend/app/pipeline/runner_v2.py app/backend/tests/test_runner_v2_retry_paths.py
git commit -m "feat(runner_v2): stamp reviewer_notes + emit retry_flag on exhaustion"
```

---

## Phase 7 — End-to-end dry-run test with mocked aggregator verdicts

**Files:**
- Create: `app/backend/tests/e2e/test_stage4_retry_e2e.py`

This phase drives the entire v2 pipeline in `HIME_DRY_RUN=1` mode (no models loaded) against a real SQLite database. A fake book with one paragraph is seeded; the `DryRunStage4Aggregator.aggregate_segment` method is monkey-patched to emit a fix_pass sequence, then reseeded and re-run for full_retry, then reseeded and re-run for exhaustion. This catches integration issues that the unit tests with fully mocked stages cannot.

### Task 7.1: E2E test — fix_pass path writes retry_count_fix_pass=1 to SQLite

- [ ] **Step 1: Write the test**

Create `app/backend/tests/e2e/test_stage4_retry_e2e.py`:

```python
"""Phase 7 — end-to-end dry-run test of the Stage 4 two-path retry mechanism.

Uses HIME_DRY_RUN=1 so no models are loaded. DryRunStage4Aggregator.aggregate_segment
is monkey-patched to emit a controlled verdict sequence, and we assert against the
real SQLite paragraphs row after the pipeline completes.
"""
from __future__ import annotations
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.stage4_aggregator import SegmentVerdict


async def _seed_book(session) -> int:
    from app.models import Book, Chapter, Paragraph
    book = Book(title="e2e", file_path="e2e.epub", total_chapters=1, total_paragraphs=1)
    session.add(book)
    await session.flush()
    chapter = Chapter(book_id=book.id, chapter_index=0, title="c1", total_paragraphs=1)
    session.add(chapter)
    await session.flush()
    para = Paragraph(
        chapter_id=chapter.id,
        paragraph_index=0,
        source_text="彼女は静かに微笑んだ。",
    )
    session.add(para)
    await session.flush()
    await session.commit()
    return book.id


async def _get_paragraph(session, book_id: int):
    from sqlalchemy import select
    from app.models import Book, Chapter, Paragraph
    stmt = (
        select(Paragraph)
        .join(Chapter, Paragraph.chapter_id == Chapter.id)
        .where(Chapter.book_id == book_id)
    )
    res = await session.execute(stmt)
    return res.scalars().first()


async def _drain(q: asyncio.Queue) -> list[dict]:
    events: list[dict] = []
    while True:
        item = await q.get()
        if item is None:
            break
        events.append(item)
    return events


@pytest.fixture(autouse=True)
def _enable_dry_run(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "hime_dry_run", True, raising=False)
    yield


def _patched_aggregator(verdicts: list[SegmentVerdict]):
    from app.pipeline.dry_run import DryRunStage4Aggregator
    async def fake_aggregate_segment(self, annotations):
        return verdicts.pop(0) if verdicts else SegmentVerdict(verdict="ok", instruction="")
    return patch.object(DryRunStage4Aggregator, "aggregate_segment", fake_aggregate_segment)


@pytest.mark.asyncio
async def test_e2e_fix_pass_persists_counter_to_sqlite(db_session):
    from app.pipeline.runner_v2 import run_pipeline_v2
    book_id = await _seed_book(db_session)

    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="Tighten pacing."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with (
        _patched_aggregator(verdicts),
        patch("app.pipeline.runner_v2.export_book", AsyncMock(return_value="/tmp/e2e.epub")),
    ):
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=book_id, ws_queue=q, session=db_session)
        await _drain(q)

    await db_session.commit()
    para = await _get_paragraph(db_session, book_id)
    assert para is not None
    assert para.is_translated is True
    assert para.retry_count_fix_pass == 1
    assert para.retry_count_full_pipeline == 0
    assert para.retry_flag is False
    assert para.aggregator_verdict == "ok"


@pytest.mark.asyncio
async def test_e2e_full_retry_persists_counter_to_sqlite(db_session):
    from app.pipeline.runner_v2 import run_pipeline_v2
    book_id = await _seed_book(db_session)

    verdicts = [
        SegmentVerdict(verdict="full_retry", instruction="Speaker attribution wrong."),
        SegmentVerdict(verdict="ok", instruction=""),
    ]
    with (
        _patched_aggregator(verdicts),
        patch("app.pipeline.runner_v2.export_book", AsyncMock(return_value="/tmp/e2e.epub")),
    ):
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=book_id, ws_queue=q, session=db_session)
        await _drain(q)

    await db_session.commit()
    para = await _get_paragraph(db_session, book_id)
    assert para is not None
    assert para.retry_count_fix_pass == 0
    assert para.retry_count_full_pipeline == 1
    assert para.retry_flag is False


@pytest.mark.asyncio
async def test_e2e_exhaustion_persists_retry_flag_and_reviewer_notes(db_session):
    from app.pipeline.runner_v2 import run_pipeline_v2
    book_id = await _seed_book(db_session)

    verdicts = [
        SegmentVerdict(verdict="fix_pass", instruction="A"),
        SegmentVerdict(verdict="fix_pass", instruction="B"),
        SegmentVerdict(verdict="fix_pass", instruction="C"),  # exhausted
    ]
    with (
        _patched_aggregator(verdicts),
        patch("app.pipeline.runner_v2.export_book", AsyncMock(return_value="/tmp/e2e.epub")),
    ):
        q: asyncio.Queue = asyncio.Queue()
        await run_pipeline_v2(book_id=book_id, ws_queue=q, session=db_session)
        await _drain(q)

    await db_session.commit()
    para = await _get_paragraph(db_session, book_id)
    assert para is not None
    assert para.retry_count_fix_pass == 2
    assert para.retry_flag is True
    assert para.reviewer_notes is not None
    assert "retry budget exhausted" in para.reviewer_notes.lower()
    # Segment is still emitted (not blocked)
    assert para.is_translated is True
    assert para.translated_text is not None and para.translated_text.strip() != ""
```

- [ ] **Step 2: Run tests and iterate until green**

Run: `cd app/backend && uv run pytest tests/e2e/test_stage4_retry_e2e.py -v`
Expected: PASS. If the fixture `db_session` does not exist in `tests/e2e/`, add `from tests.conftest import db_session  # noqa: F401` at the top of the test file or copy the fixture from `app/backend/tests/conftest.py`.

- [ ] **Step 3: Run the full backend test suite and confirm no regressions**

Run: `cd app/backend && uv run pytest -q`
Expected: All pre-existing tests still green. The Stage 4 changes are additive or strictly inside `runner_v2`, so `runner.py` tests, Stage 1–3 tests, and glossary/RAG tests should all be unaffected.

- [ ] **Step 4: Commit**

```bash
git add app/backend/tests/e2e/test_stage4_retry_e2e.py
git commit -m "test(e2e): dry-run integration tests for Stage 4 two-path retry"
```

---

## Self-review checklist (implementer should re-read before starting)

1. **Spec coverage:**
   - Severity taxonomy (ok / light → fix_pass / heavy → full_retry) — covered by Task 3.1 system prompt and `SegmentVerdict` literal.
   - Condensed instruction (not raw annotations) — covered by Task 3.1 system prompt wording.
   - Fix-pass = Stage 3 only, max 2 — Phase 4 + Task 6.1 exhaustion test.
   - Full retry = Stage 1→2→3, max 1 — Phase 5 + Task 6.1 exhaustion test.
   - After limits exhausted: emit anyway, set flag, do not block — Phase 6 + `test_fix_pass_exhaustion_sets_retry_flag`.
   - Aggregator system prompt with error taxonomy — Task 3.1 `_SEGMENT_AGGREGATOR_SYSTEM`.
   - JSON output `{verdict, instruction}` — Task 3.1.
   - DB columns (`retry_count_fix_pass`, `retry_count_full_pipeline`, `retry_flag`, `aggregator_verdict`, `aggregator_instruction`) — Phase 2.
   - Per-segment tracking (not per-chapter) — columns live on `Paragraph`, which is the segment row.
   - Instruction passed as additional context, not replacing source — fix_pass via `polish(retry_instruction=)`, full_retry via `_augment_rag_with_retry`.
   - VRAM: Stage 3 load/unload — inherent to `polish()`; Full Retry follows normal load/unload — inherent to Stage 1/2/3 existing behaviour.
   - No Stage 1/2/3 inference changes — confirmed: only call sites are touched.

2. **Naming consistency check:**
   - `SegmentVerdict.verdict` literal: `"ok" | "fix_pass" | "full_retry"` (matches spec, not the legacy `"okay"/"retry"`).
   - `SegmentVerdict.instruction` (not `retry_instruction`) — matches spec.
   - `MAX_FIX_PASS_RETRIES = 2`, `MAX_FULL_PIPELINE_RETRIES = 1` — constants used consistently in Phases 4, 5, 6.
   - Column names are exactly: `retry_count_fix_pass`, `retry_count_full_pipeline`, `retry_flag`, `aggregator_verdict`, `aggregator_instruction`.
   - Function name: `_augment_rag_with_retry` — used in Phase 4 task 4.1 (definition) and Phase 5 task 5.1 (call).

3. **Placeholder scan:** No `TODO`, no "similar to", no "add appropriate error handling". All code blocks are complete.

4. **Known edge case that the plan explicitly handles:**
   - A `full_retry` cycle that produces a subsequent `fix_pass` verdict naturally consumes one of each budget (locked in by `test_full_retry_then_fix_pass_uses_both_budgets`). The while-loop requires no cross-budget guard.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-11-stage4-retry-two-path.md`.** Two execution options:

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session with checkpoints for review.

**Which approach?**

**Before executing any phase, wait for explicit "Proceed with Phase X" confirmation.**
