"""Stage 4 — Aggregator (v2 pipeline). LiquidAI/LFM2-24B-A2B via Transformers int4."""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Any, Literal
from pydantic import BaseModel
from .stage4_reader import PersonaAnnotation

_log = logging.getLogger(__name__)

_AGGREGATOR_SYSTEM = """\
You are the final quality aggregator for a JP->EN light novel translation review system.
You will receive structured feedback from 15 specialist reader-critic personas about a
single translated sentence.

Your task: synthesise their feedback into a verdict.

Decision guidance (apply your judgment, not just arithmetic):
- If mean rating >= 0.70 and no individual rating < 0.40 -> lean toward "okay"
- If mean rating < 0.70 or any individual rating < 0.40 -> lean toward "retry"
- On "retry", produce a single concise retry_instruction (<=40 words) that tells
  Stage 3 exactly what to fix.

Respond ONLY with a single JSON object (no markdown, no explanation):
{
  "sentence_id": <integer>,
  "verdict": "okay" or "retry",
  "retry_instruction": "<instruction string or null>",
  "confidence": <float 0.0-1.0>
}"""

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


def _build_user_prompt(annotations: list[PersonaAnnotation]) -> str:
    if not annotations:
        return "No annotations provided."
    sid = annotations[0].sentence_id
    lines = [f"sentence_id: {sid}", ""]
    for a in annotations:
        issues_str = "; ".join(a.issues) if a.issues else "none"
        lines.append(f"[{a.persona}] rating={a.rating:.2f} issues=[{issues_str}] suggestion={a.suggestion!r}")
    mean = sum(a.rating for a in annotations) / len(annotations)
    lines.append(f"\nMean rating: {mean:.3f}")
    return "\n".join(lines)


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


class AggregatorVerdict(BaseModel):
    sentence_id: int
    verdict: Literal["okay", "retry"]
    retry_instruction: str | None
    confidence: float


class SegmentVerdict(BaseModel):
    """Segment-level verdict from the Stage 4 aggregator.

    Produced once per segment by aggregate_segment(). Drives the two-path retry
    system in runner_v2.
    """
    verdict: Literal["ok", "fix_pass", "full_retry"]
    instruction: str


class Stage4Aggregator:
    """LFM2-24B-A2B aggregator for 15-persona reader output."""

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None

    def load(self, settings: Any) -> None:
        try:
            import transformers  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("transformers>=5.0.0 is required for Stage4Aggregator.") from exc

        _log.info("[Stage4Aggregator] Loading %s (int4)...", settings.stage4_aggregator_model_id)
        bnb_config = transformers.BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype="bfloat16",
            bnb_4bit_use_double_quant=True,
        )
        # trust_remote_code=True is required for LFM2 (LiquidAI custom architecture).
        # The model_id at runtime should be a local path (resolved from MODELS_DIR/lfm2-24b).
        self._tokenizer = transformers.AutoTokenizer.from_pretrained(
            settings.stage4_aggregator_model_id, trust_remote_code=True,
        )
        self._model = transformers.AutoModelForCausalLM.from_pretrained(
            settings.stage4_aggregator_model_id,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True,
        )
        _log.info("[Stage4Aggregator] Model loaded.")

    def unload(self) -> None:
        import torch  # type: ignore[import]
        if self._model is not None:
            self._model.cpu()
            del self._model
            self._model = None
        self._tokenizer = None
        torch.cuda.empty_cache()
        _log.info("[Stage4Aggregator] VRAM released.")

    def _infer_one(self, user_prompt: str) -> str:
        import contextlib
        import torch  # type: ignore[import]
        messages = [
            {"role": "system", "content": _AGGREGATOR_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        text = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        raw_inputs = self._tokenizer(text, return_tensors="pt")
        inputs = raw_inputs.to(self._model.device) if hasattr(raw_inputs, "to") else raw_inputs
        _no_grad = torch.no_grad if hasattr(torch, "no_grad") else contextlib.nullcontext
        with _no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=128,
                temperature=0.1,
                do_sample=True,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        input_ids = inputs["input_ids"]
        input_len = input_ids.shape[1] if hasattr(input_ids, "shape") else len(input_ids[0])
        new_tokens = output_ids[0][input_len:]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True)

    def _parse_verdict(self, raw: str, sentence_id: int) -> AggregatorVerdict:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
        try:
            data = json.loads(text)
            return AggregatorVerdict(
                sentence_id=data.get("sentence_id", sentence_id),
                verdict=data.get("verdict", "okay"),
                retry_instruction=data.get("retry_instruction") or None,
                confidence=float(data.get("confidence", 0.5)),
            )
        except Exception:  # noqa: BLE001
            _log.warning("[Stage4Aggregator] Parse error for sentence %d — defaulting to okay", sentence_id)
            return AggregatorVerdict(
                sentence_id=sentence_id, verdict="okay", retry_instruction=None, confidence=0.0,
            )

    async def aggregate(self, annotations: list[PersonaAnnotation]) -> AggregatorVerdict:
        if not annotations:
            return AggregatorVerdict(sentence_id=0, verdict="okay", retry_instruction=None, confidence=0.0)
        sentence_id = annotations[0].sentence_id
        user_prompt = _build_user_prompt(annotations)
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, self._infer_one, user_prompt)
        return self._parse_verdict(raw, sentence_id)

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
