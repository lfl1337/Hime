"""
Input sanitization utilities.

Strips whitespace, enforces maximum length, rejects null bytes,
environment variable syntax, and prompt-injection patterns.
"""
import re

from fastapi import HTTPException, status

MAX_TEXT_LENGTH = 50_000

# Prompt-injection patterns
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

# Environment variable interpolation patterns
_ENV_VAR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\$\{[^}]+\}"),       # ${VAR_NAME}
    re.compile(r"%[A-Za-z_]\w*%"),    # %VAR_NAME%
]


def sanitize_text(text: str, field_name: str = "text") -> str:
    """
    Sanitize a user-supplied string:

    1. Strip leading/trailing whitespace.
    2. Reject if empty after stripping.
    3. Reject if contains null bytes.
    4. Reject if longer than MAX_TEXT_LENGTH.
    5. Reject if contains environment variable syntax.
    6. Reject if any prompt-injection pattern matches.

    Returns the sanitized string, or raises HTTPException 422.
    """
    text = text.strip()

    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{field_name}' must not be empty.",
        )

    if "\x00" in text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'{field_name}' contains disallowed characters (null byte).",
        )

    if len(text) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"'{field_name}' exceeds the maximum allowed length "
                f"of {MAX_TEXT_LENGTH:,} characters."
            ),
        )

    for pattern in _ENV_VAR_PATTERNS:
        if pattern.search(text):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{field_name}' contains disallowed content (environment variable syntax).",
            )

    for pattern in _COMPILED:
        if pattern.search(text):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"'{field_name}' contains disallowed content.",
            )

    return text


def coerce_numeric_string(value: str) -> str:
    """Replace German-locale comma with dot for numeric inputs."""
    return value.replace(",", ".")
