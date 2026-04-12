"""Unit tests for runner_v2 module-level helpers."""
from __future__ import annotations

from app.pipeline.runner_v2 import _augment_rag_with_retry


def test_augment_rag_with_retry_empty_instruction_returns_context_unchanged():
    ctx = "prior passage"
    assert _augment_rag_with_retry(ctx, "") == ctx
    assert _augment_rag_with_retry(ctx, "   ") == ctx


def test_augment_rag_with_retry_appends_labelled_section_to_context():
    ctx = "prior passage"
    out = _augment_rag_with_retry(ctx, "Fix the speaker.")
    assert ctx in out
    assert "[Retry instruction from prior review]:" in out
    assert "Fix the speaker." in out
    # Separator: blank line between context and note
    assert "\n\n" in out


def test_augment_rag_with_retry_empty_context_returns_note_only():
    out = _augment_rag_with_retry("", "Rewrite for tone.")
    assert out == "[Retry instruction from prior review]: Rewrite for tone."
    # Also empty-whitespace context
    out2 = _augment_rag_with_retry("   \n  ", "Rewrite for tone.")
    assert out2 == "[Retry instruction from prior review]: Rewrite for tone."
