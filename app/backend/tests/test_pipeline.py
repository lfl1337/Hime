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


class TestPipelineGracefulDegradation:
    """Verify pipeline handles partial Stage 1 failures."""

    def test_pipeline_threshold_is_one(self):
        """The minimum Stage 1 models needed should be 1, not 2."""
        from pathlib import Path
        runner_src = (Path(__file__).resolve().parent.parent / "app" / "pipeline" / "runner.py").read_text(encoding="utf-8")
        # Must not contain the old "< 2" guard; must contain the new "not stage1_outputs" guard
        assert "< 2" not in runner_src
        assert "not stage1_outputs" in runner_src or "== 0" in runner_src
