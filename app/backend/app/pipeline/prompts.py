"""
Prompt templates and message-builder functions for the multi-stage pipeline.

Templates are loaded from disk (app/backend/app/prompts/*.txt) at import time.
If a file is missing, the inline fallback is used. This allows editing prompts
without code changes.
"""
import logging
from pathlib import Path

_log = logging.getLogger(__name__)
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_template(filename: str, fallback: str) -> str:
    """Load a prompt template from disk, falling back to inline string."""
    path = _PROMPTS_DIR / filename
    if path.exists():
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                _log.debug("Loaded prompt template: %s", filename)
                return content
        except Exception as e:
            _log.warning("Failed to load %s: %s — using fallback", filename, e)
    return fallback


# Inline fallbacks (identical to the disk versions for bootstrapping)
_STAGE1_FALLBACK = """\
You are an expert Japanese-to-English light novel translator.

Rules:
- Preserve the author's style, tone, narrative voice, and sentence rhythm.
- Translate honorifics literally and keep them attached (e.g. -san, -kun, -chan, -sama).
- Render onomatopoeia naturally in English; do not transliterate romaji sounds.
- Keep Japanese proper nouns (names, places) unless a canonical English form exists.
- Output only the English translation. Do not include the original Japanese, commentary,
  or explanatory footnotes unless the source text itself contains them."""

_CONSENSUS_FALLBACK = """\
You are a senior Japanese-to-English translation editor. You will be given three
independent English translations of the same Japanese source text, produced by
different AI translators. Your task is to synthesize a single consensus translation
that:

- Captures the most accurate rendering of each passage across all three drafts.
- Resolves conflicting word choices by preferring the most natural and idiomatic
  English that still faithfully reflects the Japanese original.
- Preserves consistency of character voice, honorifics, and proper nouns across
  the entire output.
- Corrects any clear mistranslations present in one or more drafts.

Output only the consensus English translation. No commentary, no headers, no
numbering."""

_STAGE2_FALLBACK = """\
You are a professional Japanese-to-English literary editor specializing in light
novels. You will receive a consensus English translation draft. Your task is to
refine it into polished, publication-ready prose:

- Improve sentence flow, rhythm, and readability without altering meaning.
- Replace awkward or literal phrasings with natural English equivalents.
- Ensure consistent style, tense, and point of view throughout.
- Preserve all character names, honorifics, and proper nouns exactly as given.
- Do not add or remove content — only refine the existing translation.

Output only the refined English translation."""

_STAGE3_FALLBACK = """\
You are a meticulous copy-editor. You will receive a refined English translation
of a Japanese light novel passage. Perform a final polish pass:

- Correct any remaining grammar, punctuation, or typographical errors.
- Ensure paragraph breaks and dialogue formatting follow standard English
  light-novel conventions.
- Do not change word choices or sentence structures unless they contain a clear
  grammatical error.
- Output only the final polished text."""

# Load templates (disk → fallback)
_STAGE1_SYSTEM = _load_template("stage1_translate.txt", _STAGE1_FALLBACK)
_CONSENSUS_SYSTEM = _load_template("consensus_merge.txt", _CONSENSUS_FALLBACK)
_STAGE2_SYSTEM = _load_template("stage2_refine.txt", _STAGE2_FALLBACK)
_STAGE3_SYSTEM = _load_template("stage3_polish.txt", _STAGE3_FALLBACK)


def stage1_messages(source_text: str, notes: str = "") -> list[dict[str, str]]:
    """Messages for each Stage 1 translator model."""
    system = _STAGE1_SYSTEM
    if notes:
        system += f"\n\nAdditional translator notes: {notes}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": source_text},
    ]


def consensus_messages(
    source_text: str,
    translations: dict[str, str],
) -> list[dict[str, str]]:
    """Messages for the consensus/merger model."""
    drafts = "\n\n".join(
        f"--- Translation {i + 1} ({label}) ---\n{text}"
        for i, (label, text) in enumerate(translations.items())
    )
    user_content = (
        f"Japanese source text:\n{source_text}\n\n"
        f"Three draft translations:\n\n{drafts}"
    )
    return [
        {"role": "system", "content": _CONSENSUS_SYSTEM},
        {"role": "user", "content": user_content},
    ]


def stage2_messages(consensus_text: str) -> list[dict[str, str]]:
    """Messages for the Stage 2 (72B refinement) model."""
    return [
        {"role": "system", "content": _STAGE2_SYSTEM},
        {"role": "user", "content": consensus_text},
    ]


def stage3_messages(stage2_text: str) -> list[dict[str, str]]:
    """Messages for the Stage 3 (14B final polish) model."""
    return [
        {"role": "system", "content": _STAGE3_SYSTEM},
        {"role": "user", "content": stage2_text},
    ]
