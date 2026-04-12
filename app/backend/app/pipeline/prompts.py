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
  or explanatory footnotes unless the source text itself contains them.

{glossary}

{rag_context}

{lexicon_anchor}"""

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


def stage1_messages(
    source_text: str,
    notes: str = "",
    glossary: str = "",
    rag_context: str = "",
    lexicon_anchor: str = "",
) -> list[dict[str, str]]:
    """Messages for each Stage 1 translator model."""
    system = _STAGE1_SYSTEM
    system = system.replace("{glossary}", glossary)
    system = system.replace("{rag_context}", rag_context)
    system = system.replace("{lexicon_anchor}", lexicon_anchor)
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


def stage3_messages(stage2_text: str, retry_notes: str = "") -> list[dict[str, str]]:
    """Messages for the Stage 3 (14B final polish) model.

    Args:
        stage2_text: The Stage 2 output to polish.
        retry_notes: Optional reader-panel retry instructions injected when
                     Stage 4 requests a re-run (e.g. "[s0] Preserve wistful tone.").
    """
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


# ---------------------------------------------------------------------------
# Pipeline v2 — Stage 2 Merger + Stage 3 Polish (WS-C)
# ---------------------------------------------------------------------------

_MERGER_FALLBACK = """\
You are a master Japanese-to-English translation editor. You will receive five
independent English draft translations of the same Japanese source passage,
each produced by a different specialist model. Your task is to merge them into
one superior translation that:

- Selects the most accurate and natural phrasing from each draft.
- Resolves contradictions by preferring the reading most faithful to idiomatic
  English while preserving the Japanese nuance.
- Maintains consistent character voice, honorifics, and proper nouns.
- Incorporates glossary-specified term translations exactly as given.
- Does NOT add commentary, footnotes, or explanatory brackets.

Output only the single merged English translation."""

_POLISH_FALLBACK = """\
You are a literary copy-editor specializing in Japanese light novels translated
into English. You will receive a merged English translation draft. Your tasks:

1. Convert Japanese punctuation to English equivalents:
   「」 → double quotation marks, 『』 → single quotation marks,
   … → ..., 。at end of sentence → remove (English period already present),
   、 → comma, ！ → !, ？ → ?
2. Smooth any awkward phrasing for natural English flow.
3. Preserve the light-novel literary style: vivid imagery, character voice,
   emotional register.
4. Keep all honorifics (-san, -kun, -chan, -sama, -sensei, etc.) attached and
   consistent with the glossary.
5. Do NOT add or remove content — only refine and correct.

Output only the final polished English translation."""

_MERGER_SYSTEM = _load_template("merger_merge.txt", _MERGER_FALLBACK)
_POLISH_SYSTEM = _load_template("polish_stage3.txt", _POLISH_FALLBACK)

_DRAFT_LABELS: dict[str, str] = {
    "qwen32b":        "Draft 1 — Qwen2.5-32B",
    "translategemma": "Draft 2 — TranslateGemma-12B",
    "qwen35_9b":      "Draft 3 — Qwen3-9B",
    "gemma4_e4b":     "Draft 4 — Gemma4 E4B",
    "jmdict":         "Draft 5 — JMdict",
}


def merger_messages(
    drafts: dict[str, str],
    rag_context: str,
    glossary_context: str,
) -> list[dict[str, str]]:
    """Build the message list for the Stage 2 TranslateGemma-27B merger model.

    Args:
        drafts: Mapping of draft-key → translated text.  Missing keys are
                rendered as "[unavailable]" so the merger knows the slot was
                empty rather than inferring it from silence.
        rag_context: Retrieved passage context from the RAG store.
        glossary_context: Book-specific glossary formatted for injection.
    """
    lines: list[str] = []
    for key, label in _DRAFT_LABELS.items():
        text = drafts.get(key, "").strip()
        lines.append(f"[{label}]: {text if text else '[unavailable]'}")

    user_parts: list[str] = []
    if rag_context.strip():
        user_parts.append(f"[Context from previous passages]:\n{rag_context.strip()}")
    if glossary_context.strip():
        user_parts.append(f"[Glossary]:\n{glossary_context.strip()}")
    user_parts.append("\n".join(lines))

    return [
        {"role": "system", "content": _MERGER_SYSTEM},
        {"role": "user",   "content": "\n\n".join(user_parts)},
    ]


def polish_messages(
    merged: str,
    glossary_context: str,
    retry_instruction: str = "",
) -> list[dict[str, str]]:
    """Build the message list for the Stage 3 Qwen3-30B-A3B polish model.

    Args:
        merged: The merged English translation from Stage 2.
        glossary_context: Book-specific glossary for honorific consistency.
        retry_instruction: Optional additional instruction injected on retry
                           (e.g. "Focus on fixing dialogue formatting.").
                           When non-empty, appended to the user message.
    """
    user_parts: list[str] = []
    if glossary_context.strip():
        user_parts.append(f"[Glossary]:\n{glossary_context.strip()}")
    user_parts.append(f"[Merged translation to polish]:\n{merged}")
    if retry_instruction.strip():
        user_parts.append(f"Additional instruction: {retry_instruction.strip()}")

    return [
        {"role": "system", "content": _POLISH_SYSTEM},
        {"role": "user",   "content": "\n\n".join(user_parts)},
    ]
