"""
Prompt templates and message-builder functions for the multi-stage pipeline.

All builders return a list of {"role": ..., "content": ...} dicts compatible
with the OpenAI chat-completions API.
"""

_STAGE1_SYSTEM = """\
You are an expert Japanese-to-English light novel translator.

Rules:
- Preserve the author's style, tone, narrative voice, and sentence rhythm.
- Translate honorifics literally and keep them attached (e.g. -san, -kun, -chan, -sama).
- Render onomatopoeia naturally in English; do not transliterate romaji sounds.
- Keep Japanese proper nouns (names, places) unless a canonical English form exists.
- Output only the English translation. Do not include the original Japanese, commentary,
  or explanatory footnotes unless the source text itself contains them.\
"""

_CONSENSUS_SYSTEM = """\
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
numbering.\
"""

_STAGE2_SYSTEM = """\
You are a professional Japanese-to-English literary editor specializing in light
novels. You will receive a consensus English translation draft. Your task is to
refine it into polished, publication-ready prose:

- Improve sentence flow, rhythm, and readability without altering meaning.
- Replace awkward or literal phrasings with natural English equivalents.
- Ensure consistent style, tense, and point of view throughout.
- Preserve all character names, honorifics, and proper nouns exactly as given.
- Do not add or remove content — only refine the existing translation.

Output only the refined English translation.\
"""

_STAGE3_SYSTEM = """\
You are a meticulous copy-editor. You will receive a refined English translation
of a Japanese light novel passage. Perform a final polish pass:

- Correct any remaining grammar, punctuation, or typographical errors.
- Ensure paragraph breaks and dialogue formatting follow standard English
  light-novel conventions.
- Do not change word choices or sentence structures unless they contain a clear
  grammatical error.
- Output only the final polished text.\
"""


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
    """
    Messages for the consensus/merger model.

    ``translations`` is a mapping of label → translation text, e.g.
    {"gemma": "...", "deepseek": "...", "qwen32b": "..."}.
    """
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
