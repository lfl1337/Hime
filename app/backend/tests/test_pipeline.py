from pathlib import Path

import pytest


class TestPromptTemplateLoading:
    """Verify prompt templates load from disk with fallback."""

    def test_stage1_template_loaded(self):
        from app.pipeline.prompts import _STAGE1_SYSTEM
        assert "expert Japanese-to-English" in _STAGE1_SYSTEM
        assert len(_STAGE1_SYSTEM) > 100

    def test_consensus_template_loaded(self):
        from app.pipeline.prompts import _CONSENSUS_SYSTEM
        assert "senior Japanese-to-English translation editor" in _CONSENSUS_SYSTEM

    def test_stage2_template_loaded(self):
        from app.pipeline.prompts import _STAGE2_SYSTEM
        assert "literary editor" in _STAGE2_SYSTEM

    def test_stage3_template_loaded(self):
        from app.pipeline.prompts import _STAGE3_SYSTEM
        assert "copy-editor" in _STAGE3_SYSTEM

    def test_stage1_messages_includes_notes(self):
        from app.pipeline.prompts import stage1_messages
        msgs = stage1_messages("テスト", notes="Use casual tone")
        assert len(msgs) == 2
        assert "Use casual tone" in msgs[0]["content"]

    def test_consensus_messages_formats_drafts(self):
        from app.pipeline.prompts import consensus_messages
        drafts = {"gemma": "Draft A", "deepseek": "Draft B"}
        msgs = consensus_messages("原文", drafts)
        assert "Draft A" in msgs[1]["content"]
        assert "Draft B" in msgs[1]["content"]

    def test_fallback_used_when_file_missing(self, tmp_path, monkeypatch):
        """If template file doesn't exist, fallback string is used."""
        from app.pipeline import prompts
        monkeypatch.setattr(prompts, "_PROMPTS_DIR", tmp_path)
        result = prompts._load_template("nonexistent.txt", "FALLBACK_VALUE")
        assert result == "FALLBACK_VALUE"
