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


class AggregatorVerdict(BaseModel):
    sentence_id: int
    verdict: Literal["okay", "retry"]
    retry_instruction: str | None
    confidence: float


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
