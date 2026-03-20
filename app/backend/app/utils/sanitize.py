"""
Input sanitization utilities.

Strips whitespace, enforces maximum length, and rejects text that contains
common prompt-injection patterns before it reaches the Claude API.
"""
import re

from fastapi import HTTPException, status

MAX_TEXT_LENGTH = 50_000

# Patterns that indicate an attempt to override the system prompt or hijack
# the model's behavior. This is not an exhaustive list — it covers the most
# common jailbreak / injection vectors seen in the wild.
_INJECTION_PATTERNS: list[str] = [
    r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"(?i)disregard\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"(?i)forget\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"(?i)you\s+are\s+now\s+a?\s*(different|new)\s+(ai|model|assistant|gpt|llm)",
    r"(?i)act\s+as\s+(if\s+you\s+are\s+)?(a\s+)?(different|new|unrestricted)\s+(ai|model|assistant)",
    r"(?i)\bsystem\s*prompt\b",
    r"(?i)<\|im_start\|>",
    r"(?i)<\|im_end\|>",
    r"(?i)\[INST\]",
    r"(?i)###\s*(Human|Assistant|System)\s*:",
    r"(?i)<\s*/?\s*system\s*>",
]

_COMPILED: list[re.Pattern[str]] = [re.compile(p) for p in _INJECTION_PATTERNS]


def sanitize_text(text: str, field_name: str = "text") -> str:
    """
    Sanitize a user-supplied string:

    1. Strip leading/trailing whitespace.
    2. Reject if empty after stripping.
    3. Reject if longer than MAX_TEXT_LENGTH.
    4. Reject if any prompt-injection pattern matches.

    Returns the sanitized string, or raises HTTPException 422.
    """
    text = text.strip()

    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{field_name}' must not be empty.",
        )

    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{field_name}' exceeds the maximum allowed length "
                f"of {MAX_TEXT_LENGTH:,} characters."
            ),
        )

    for pattern in _COMPILED:
        if pattern.search(text):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{field_name}' contains disallowed content.",
            )

    return text
