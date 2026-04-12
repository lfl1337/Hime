"""Unit tests for the prompt template system (Phase 3)."""
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_build_glossary_section_with_entries():
    from app.pipeline.prompts import build_glossary_section
    entries = [
        {"jp": "千夏", "en": "Chinatsu", "note": "protagonist (female)"},
        {"jp": "奏",   "en": "Kanade",   "note": "main character (female)"},
    ]
    out = build_glossary_section(entries)
    assert "千夏" in out and "Chinatsu" in out
    assert "奏" in out and "Kanade" in out
    assert "protagonist (female)" in out


def test_build_glossary_section_empty():
    from app.pipeline.prompts import build_glossary_section
    assert build_glossary_section([]) == ""


def test_build_character_list_with_chars():
    from app.pipeline.prompts import build_character_list
    chars = [
        {"jp": "千夏", "en": "Chinatsu", "role": "protagonist (female)"},
        {"jp": "藍",   "en": "Ai",       "role": "senpai (female)"},
    ]
    out = build_character_list(chars)
    assert "千夏" in out and "Chinatsu" in out
    assert "藍" in out and "Ai" in out


def test_build_character_list_empty():
    from app.pipeline.prompts import build_character_list
    assert build_character_list([]) == ""


def test_build_rag_context_section_with_chunks():
    from app.pipeline.prompts import build_rag_context_section
    out = build_rag_context_section(["chunk A", "chunk B"])
    assert "chunk A" in out and "chunk B" in out


def test_build_rag_context_section_empty():
    from app.pipeline.prompts import build_rag_context_section
    assert build_rag_context_section([]) == ""


def test_render_prompt_injects_source_text():
    # Use an inline template with {source_text} to verify render_prompt substitutes it.
    # Note: stage1 system templates use source_text in the USER message, not here.
    from app.pipeline.prompts import render_prompt
    tmpl = "Translate the following: {source_text}"
    out = render_prompt(tmpl, source_text="こんにちは")
    assert "こんにちは" in out


def test_render_prompt_strips_empty_sections():
    from app.pipeline.prompts import render_prompt, _QWEN32B_STAGE1
    out = render_prompt(
        _QWEN32B_STAGE1,
        source_text="テスト",
        glossary="",
        character_list="",
        rag_context="",
    )
    assert "\n\n\n" not in out


# ---------------------------------------------------------------------------
# Per-model template content checks (yuri regression tests)
# ---------------------------------------------------------------------------

def test_qwen32b_template_has_pronoun_rule():
    from app.pipeline.prompts import _QWEN32B_STAGE1
    assert "female pronouns" in _QWEN32B_STAGE1.lower()


def test_qwen32b_template_has_name_examples():
    """T1/T2/T6 prevention: name examples must be in the Qwen32B prompt."""
    from app.pipeline.prompts import _QWEN32B_STAGE1
    assert "Chinatsu" in _QWEN32B_STAGE1
    assert "Kanade" in _QWEN32B_STAGE1
    assert "Ai" in _QWEN32B_STAGE1


def test_qwen32b_template_has_no_hallucination_rule():
    from app.pipeline.prompts import _QWEN32B_STAGE1
    assert "hallucination" in _QWEN32B_STAGE1.lower() or \
           "do not add" in _QWEN32B_STAGE1.lower()


def test_sarashina2_template_has_pronoun_rule():
    from app.pipeline.prompts import _SARASHINA2_STAGE1
    assert "female pronouns" in _SARASHINA2_STAGE1.lower()


def test_sarashina2_template_enforces_english_output():
    from app.pipeline.prompts import _SARASHINA2_STAGE1
    assert "english only" in _SARASHINA2_STAGE1.lower() or \
           "must be english" in _SARASHINA2_STAGE1.lower()


def test_translategemma_template_is_shorter_than_qwen():
    from app.pipeline.prompts import _QWEN32B_STAGE1, _TRANSLATEGEMMA_STAGE1
    assert len(_TRANSLATEGEMMA_STAGE1) < len(_QWEN32B_STAGE1) / 2, (
        "TranslateGemma prompt must be much shorter than Qwen32B prompt"
    )


def test_merger_template_has_pronoun_veto():
    from app.pipeline.prompts import _MERGER_SYSTEM
    assert "PRONOUN VETO" in _MERGER_SYSTEM


def test_merger_template_has_jmdict_authoritative():
    from app.pipeline.prompts import _MERGER_SYSTEM
    assert "JMDICT IS AUTHORITATIVE" in _MERGER_SYSTEM


def test_merger_draft_labels_include_sarashina2():
    from app.pipeline.prompts import _DRAFT_LABELS
    assert "sarashina2" in _DRAFT_LABELS
    assert "gemma4_e4b" not in _DRAFT_LABELS


def test_polish_template_has_do_not_retranslate():
    from app.pipeline.prompts import _POLISH_SYSTEM
    assert "DO NOT" in _POLISH_SYSTEM
    assert "re-translate" in _POLISH_SYSTEM.lower()


# ---------------------------------------------------------------------------
# stage1_messages_for_model integration
# ---------------------------------------------------------------------------

def test_stage1_messages_for_qwen32b():
    from app.pipeline.prompts import stage1_messages_for_model
    msgs = stage1_messages_for_model("qwen32b", source_text="彼女は泣いていた。")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "彼女は泣いていた。" in msgs[1]["content"]


def test_stage1_messages_injects_glossary():
    from app.pipeline.prompts import stage1_messages_for_model
    entries = [{"jp": "千夏", "en": "Chinatsu", "note": "protagonist"}]
    msgs = stage1_messages_for_model(
        "qwen32b",
        source_text="千夏は笑った。",
        glossary_entries=entries,
    )
    # Glossary must appear in system message
    assert "Chinatsu" in msgs[0]["content"]


def test_stage1_messages_unknown_model_falls_back():
    from app.pipeline.prompts import stage1_messages_for_model
    msgs = stage1_messages_for_model("unknown_model", source_text="テスト")
    assert len(msgs) == 2  # Should not crash
