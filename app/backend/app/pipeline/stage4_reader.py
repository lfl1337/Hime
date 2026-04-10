"""
Stage 4 — Reader Panel (v2 pipeline).

Loads Qwen3.5-2B via Unsloth (NF4, Non-Thinking Mode) once and runs
15 persona system-prompt inferences sequentially per sentence.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import BaseModel

_log = logging.getLogger(__name__)

PERSONAS: list[tuple[str, str]] = [
    ("Purist", "You evaluate translation fidelity to the Japanese original. Flag any meaning shifts, omissions, or additions."),
    ("Stilist", "You evaluate natural English writing flow. Flag awkward phrasing, unnatural word order, or stilted prose."),
    ("Charakter-Tracker", "You evaluate consistency of character voices across the passage. Flag any character speaking out of their established register."),
    ("Yuri-Leser", "You evaluate emotional nuance in relationships between female characters. Flag undertones that are muted, lost, or mistranslated."),
    ("Casual-Reader", "You evaluate overall readability for a general English light-novel reader. Flag anything that pulls you out of immersion."),
    ("Grammatik-Checker", "You evaluate sentence structure and punctuation. Flag run-ons, fragments, comma splices, and punctuation errors."),
    ("Pacing-Leser", "You evaluate scene rhythm and paragraph flow. Flag pacing that feels rushed, padded, or inconsistent with the source."),
    ("Dialog-Checker", "You evaluate naturalness of spoken dialogue. Flag stilted, unnatural, or un-idiomatic lines of dialogue."),
    ("Atmosphären-Leser", "You evaluate mood and world-building description. Flag losses of atmosphere, setting detail, or sensory language."),
    ("Subtext-Leser", "You evaluate implied meaning and unspoken subtext. Flag implication that is made too explicit or is lost."),
    ("Kultureller-Kontext", "You evaluate correct transfer of Japanese cultural elements. Flag cultural references that are mistranslated or inadequately adapted."),
    ("Honorific-Checker", "You evaluate consistency of Japanese honorifics (-san, -chan, -kun, -senpai, -sama). Flag any dropped, added, or inconsistently rendered honorifics."),
    ("Namen-Tracker", "You evaluate consistency of character and place names. Flag any name variation, romanisation mismatch, or spelling inconsistency."),
    ("Emotionaler-Ton", "You evaluate the emotional register of the scene. Flag translations that shift the emotional tone up or down from the original."),
    ("Light-Novel-Leser", "You evaluate genre-appropriate conventions for English light novels. Flag anything that violates genre norms or expectations."),
]

_OUTPUT_SCHEMA = """\
Respond ONLY with a single JSON object (no markdown fences, no explanation):
{
  "persona": "<your persona name>",
  "sentence_id": <integer>,
  "rating": <float 0.0-1.0, where 1.0 = perfect>,
  "issues": [<short issue string>, ...],
  "suggestion": "<one concrete rewrite suggestion, or empty string if none>"
}"""


def _build_system_prompt(persona_name: str, focus: str) -> str:
    return (
        f"You are the {persona_name} reader-critic for a JP->EN light novel translation review.\n"
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


class PersonaAnnotation(BaseModel):
    persona: str
    sentence_id: int
    rating: float
    issues: list[str]
    suggestion: str


class Stage4Reader:
    """15-persona reader panel using Qwen3.5-2B (NF4) loaded via Unsloth."""

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None

    def load(self, settings: Any) -> None:
        try:
            from unsloth import FastLanguageModel  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "unsloth is required for Stage4Reader. Install it separately with CUDA support."
            ) from exc

        _log.info("[Stage4Reader] Loading %s (NF4) via Unsloth...", settings.stage4_reader_model_id)
        self._model, self._tokenizer = FastLanguageModel.from_pretrained(
            model_name=settings.stage4_reader_model_id,
            max_seq_length=2048,
            dtype=None,
            load_in_4bit=True,
        )
        _log.info("[Stage4Reader] Model loaded.")

    def unload(self) -> None:
        import torch  # type: ignore[import]
        if self._model is not None:
            self._model.cpu()
            del self._model
            self._model = None
        self._tokenizer = None
        torch.cuda.empty_cache()
        _log.info("[Stage4Reader] VRAM released.")

    def _infer_one(self, system_prompt: str, user_prompt: str) -> str:
        import contextlib
        import torch  # type: ignore[import]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        text = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False,
        )
        raw_inputs = self._tokenizer(text, return_tensors="pt")
        inputs = raw_inputs.to(self._model.device) if hasattr(raw_inputs, "to") else raw_inputs
        _no_grad = torch.no_grad if hasattr(torch, "no_grad") else contextlib.nullcontext
        with _no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.2,
                do_sample=True,
                eos_token_id=self._tokenizer.eos_token_id,
            )
        input_ids = inputs["input_ids"]
        input_len = input_ids.shape[1] if hasattr(input_ids, "shape") else len(input_ids[0])
        new_tokens = output_ids[0][input_len:]
        return self._tokenizer.decode(new_tokens, skip_special_tokens=True)

    def _parse_annotation(self, raw: str, persona_name: str, sentence_id: int) -> PersonaAnnotation:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
        try:
            data = json.loads(text)
            return PersonaAnnotation(
                persona=persona_name,  # always use caller-supplied name for consistency
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
        loop = asyncio.get_event_loop()
        results: list[PersonaAnnotation] = []
        for sid, (translation, source) in enumerate(zip(sentences, source_sentences)):
            for persona_name, focus in PERSONAS:
                system_prompt = _build_system_prompt(persona_name, focus)
                user_prompt = _build_user_prompt(sid, translation, source)
                raw = await loop.run_in_executor(None, self._infer_one, system_prompt, user_prompt)
                annotation = self._parse_annotation(raw, persona_name, sid)
                results.append(annotation)
        return results
