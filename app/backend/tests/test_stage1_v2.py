"""Tests for Stage 1 v2 — local Unsloth inference package.

Run from: N:/Projekte/NiN/Hime/.worktrees/pipeline-v2/app/backend/
Command:  uv run pytest tests/test_stage1_v2.py -v
"""
from __future__ import annotations

import sys
import types

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Task 3: _types.py
# ---------------------------------------------------------------------------

class TestStage1Drafts:
    def test_dataclass_fields_exist(self):
        from app.pipeline.stage1._types import Stage1Drafts
        d = Stage1Drafts(
            source_jp="猫が走る。",
            qwen32b="The cat runs.",
            translategemma12b="A cat is running.",
            qwen35_9b="Cats run.",
            gemma4_e4b="The cat ran.",
            jmdict="cat run .",
        )
        assert d.source_jp == "猫が走る。"
        assert d.qwen32b == "The cat runs."
        assert d.translategemma12b == "A cat is running."
        assert d.qwen35_9b == "Cats run."
        assert d.gemma4_e4b == "The cat ran."
        assert d.jmdict == "cat run ."

    def test_optional_fields_default_none(self):
        from app.pipeline.stage1._types import Stage1Drafts
        d = Stage1Drafts(source_jp="テスト", jmdict="test")
        assert d.qwen32b is None
        assert d.translategemma12b is None
        assert d.qwen35_9b is None
        assert d.gemma4_e4b is None

    def test_jmdict_is_always_str(self):
        from app.pipeline.stage1._types import Stage1Drafts
        d = Stage1Drafts(source_jp="x", jmdict="")
        assert isinstance(d.jmdict, str)


# ---------------------------------------------------------------------------
# Task 4: adapter_qwen32b.py
# ---------------------------------------------------------------------------

class TestAdapterQwen32b:
    @pytest.mark.asyncio
    async def test_returns_translation_string(self, monkeypatch):
        """Adapter calls inference.complete() and returns its result."""
        from app.pipeline.stage1 import adapter_qwen32b

        async def fake_complete(url, model, messages, **kwargs):
            return "The cat runs quickly."

        monkeypatch.setattr("app.pipeline.stage1.adapter_qwen32b.complete", fake_complete)

        result = await adapter_qwen32b.translate("猫が速く走る。", rag_context="", glossary_context="")
        assert result == "The cat runs quickly."

    @pytest.mark.asyncio
    async def test_passes_source_as_user_message(self, monkeypatch):
        """The source JP text must appear as the user message."""
        from app.pipeline.stage1 import adapter_qwen32b

        captured: list[dict] = []

        async def capturing_complete(url, model, messages, **kwargs):
            captured.extend(messages)
            return "ok"

        monkeypatch.setattr("app.pipeline.stage1.adapter_qwen32b.complete", capturing_complete)
        await adapter_qwen32b.translate("テスト文章", rag_context="", glossary_context="")

        user_msg = next(m for m in captured if m["role"] == "user")
        assert "テスト文章" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_string(self, monkeypatch):
        from app.pipeline.stage1 import adapter_qwen32b

        async def fake_complete(url, model, messages, **kwargs):
            return ""

        monkeypatch.setattr("app.pipeline.stage1.adapter_qwen32b.complete", fake_complete)
        result = await adapter_qwen32b.translate("x", rag_context="", glossary_context="")
        assert result == ""


# ---------------------------------------------------------------------------
# Task 5: adapter_translategemma.py
# ---------------------------------------------------------------------------

class TestAdapterTranslateGemma:
    @pytest.mark.asyncio
    async def test_returns_string(self, monkeypatch):
        """Adapter returns a non-empty string when model generates output."""
        from app.pipeline.stage1 import adapter_translategemma

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()

        # Tokenizer encode → tensor-like object
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.apply_chat_template.return_value = "formatted prompt"
        fake_tokenizer.return_value = fake_inputs
        fake_tokenizer.decode.return_value = "The cat runs."

        # model.generate → token ids
        fake_model.generate.return_value = [[1, 2, 3]]

        fake_unsloth = types.ModuleType("unsloth")
        mock_flm = MagicMock()
        mock_flm.from_pretrained.return_value = (fake_model, fake_tokenizer)
        mock_flm.for_inference = MagicMock()
        fake_unsloth.FastLanguageModel = mock_flm
        monkeypatch.setitem(sys.modules, "unsloth", fake_unsloth)

        # Reset cached instance so patch takes effect
        adapter_translategemma._MODEL_CACHE.clear()
        result = await adapter_translategemma.translate(
            "猫が走る。", rag_context="", glossary_context=""
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_model_loaded_once(self, monkeypatch):
        """from_pretrained is called only once across multiple translate() calls."""
        from app.pipeline.stage1 import adapter_translategemma

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "translation"
        fake_model.generate.return_value = [[1, 2, 3]]

        call_count = 0

        def counting_from_pretrained(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return fake_model, fake_tokenizer

        fake_unsloth = types.ModuleType("unsloth")
        mock_flm = MagicMock()
        mock_flm.from_pretrained.side_effect = counting_from_pretrained
        mock_flm.for_inference = MagicMock()
        fake_unsloth.FastLanguageModel = mock_flm
        monkeypatch.setitem(sys.modules, "unsloth", fake_unsloth)

        adapter_translategemma._MODEL_CACHE.clear()
        await adapter_translategemma.translate("A", rag_context="", glossary_context="")
        await adapter_translategemma.translate("B", rag_context="", glossary_context="")

        assert call_count == 1


# ---------------------------------------------------------------------------
# Task 6: adapter_qwen35_9b.py
# ---------------------------------------------------------------------------

class TestAdapterQwen35_9b:
    @pytest.mark.asyncio
    async def test_returns_string(self, monkeypatch):
        from app.pipeline.stage1 import adapter_qwen35_9b

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "She walked home."
        fake_model.generate.return_value = [[1, 2, 3]]
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.return_value = fake_inputs

        fake_unsloth = types.ModuleType("unsloth")
        mock_flm = MagicMock()
        mock_flm.from_pretrained.return_value = (fake_model, fake_tokenizer)
        mock_flm.for_inference = MagicMock()
        fake_unsloth.FastLanguageModel = mock_flm
        monkeypatch.setitem(sys.modules, "unsloth", fake_unsloth)

        adapter_qwen35_9b._MODEL_CACHE.clear()
        result = await adapter_qwen35_9b.translate(
            "彼女は家に帰った。", rag_context="", glossary_context=""
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_non_thinking_flag_passed(self, monkeypatch):
        """generate() must be called with enable_thinking=False."""
        from app.pipeline.stage1 import adapter_qwen35_9b

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "result"
        fake_model.generate.return_value = [[1, 2, 3]]
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.return_value = fake_inputs

        fake_unsloth = types.ModuleType("unsloth")
        mock_flm = MagicMock()
        mock_flm.from_pretrained.return_value = (fake_model, fake_tokenizer)
        mock_flm.for_inference = MagicMock()
        fake_unsloth.FastLanguageModel = mock_flm
        monkeypatch.setitem(sys.modules, "unsloth", fake_unsloth)

        adapter_qwen35_9b._MODEL_CACHE.clear()
        await adapter_qwen35_9b.translate("x", rag_context="", glossary_context="")

        call_kwargs = fake_model.generate.call_args.kwargs
        assert call_kwargs.get("enable_thinking") is False


# ---------------------------------------------------------------------------
# Task 7: adapter_gemma4.py
# ---------------------------------------------------------------------------

class TestAdapterGemma4:
    @pytest.mark.asyncio
    async def test_returns_string(self, monkeypatch):
        from app.pipeline.stage1 import adapter_gemma4

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "The wind blew."
        fake_model.generate.return_value = [[1, 2, 3]]
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.return_value = fake_inputs

        fake_unsloth = types.ModuleType("unsloth")
        mock_flm = MagicMock()
        mock_flm.from_pretrained.return_value = (fake_model, fake_tokenizer)
        mock_flm.for_inference = MagicMock()
        fake_unsloth.FastLanguageModel = mock_flm
        monkeypatch.setitem(sys.modules, "unsloth", fake_unsloth)

        adapter_gemma4._MODEL_CACHE.clear()
        result = await adapter_gemma4.translate("風が吹いた。", rag_context="", glossary_context="")

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_enable_thinking_not_passed(self, monkeypatch):
        """Gemma4 does not support enable_thinking — must not appear in generate() kwargs."""
        from app.pipeline.stage1 import adapter_gemma4

        fake_model = MagicMock()
        fake_tokenizer = MagicMock()
        fake_tokenizer.apply_chat_template.return_value = "formatted"
        fake_tokenizer.decode.return_value = "result"
        fake_model.generate.return_value = [[1, 2, 3]]
        fake_inputs = MagicMock()
        fake_inputs.__getitem__ = MagicMock(return_value=MagicMock())
        fake_tokenizer.return_value = fake_inputs

        fake_unsloth = types.ModuleType("unsloth")
        mock_flm = MagicMock()
        mock_flm.from_pretrained.return_value = (fake_model, fake_tokenizer)
        mock_flm.for_inference = MagicMock()
        fake_unsloth.FastLanguageModel = mock_flm
        monkeypatch.setitem(sys.modules, "unsloth", fake_unsloth)

        adapter_gemma4._MODEL_CACHE.clear()
        await adapter_gemma4.translate("x", rag_context="", glossary_context="")

        call_kwargs = fake_model.generate.call_args.kwargs
        assert "enable_thinking" not in call_kwargs


# ---------------------------------------------------------------------------
# Task 8: adapter_jmdict.py
# ---------------------------------------------------------------------------

class TestAdapterJmdict:
    def test_returns_string_for_known_text(self, monkeypatch):
        from app.pipeline.stage1 import adapter_jmdict
        from app.services.lexicon_service import LexiconResult

        fake_result = LexiconResult(
            tokens=[],
            literal_translation="cat run .",
            unknown_tokens=[],
            confidence=0.9,
        )

        monkeypatch.setattr(
            "app.pipeline.stage1.adapter_jmdict.LexiconService.translate",
            lambda self, text: fake_result,
        )

        result = adapter_jmdict.translate("猫が走る。")
        assert result == "cat run ."

    def test_returns_empty_string_for_empty_input(self, monkeypatch):
        from app.pipeline.stage1 import adapter_jmdict
        from app.services.lexicon_service import LexiconResult

        fake_result = LexiconResult(
            tokens=[],
            literal_translation="",
            unknown_tokens=[],
            confidence=0.0,
        )

        monkeypatch.setattr(
            "app.pipeline.stage1.adapter_jmdict.LexiconService.translate",
            lambda self, text: fake_result,
        )

        result = adapter_jmdict.translate("")
        assert result == ""

    def test_never_raises(self, monkeypatch):
        """Even if LexiconService raises internally, adapter must not propagate it."""
        from app.pipeline.stage1 import adapter_jmdict

        def broken_translate(self, text):
            raise RuntimeError("MeCab died")

        monkeypatch.setattr(
            "app.pipeline.stage1.adapter_jmdict.LexiconService.translate",
            broken_translate,
        )

        result = adapter_jmdict.translate("猫")
        assert isinstance(result, str)
        assert result == ""


# ---------------------------------------------------------------------------
# Task 9: stage1/runner.py
# ---------------------------------------------------------------------------

# Helper coroutine factory used across multiple tests
async def _async_return(value):
    return value


class TestRunStage1Integration:
    """Integration test: run_stage1() with all adapters mocked."""

    @pytest.mark.asyncio
    async def test_all_adapters_succeed_returns_complete_drafts(self, monkeypatch):
        from app.pipeline.stage1 import runner as stage1_runner
        from app.pipeline.stage1._types import Stage1Drafts

        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_qwen32b.translate",
            lambda *a, **kw: _async_return("qwen32b translation"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_translategemma.translate",
            lambda *a, **kw: _async_return("translategemma translation"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_qwen35_9b.translate",
            lambda *a, **kw: _async_return("qwen35 translation"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_gemma4.translate",
            lambda *a, **kw: _async_return("gemma4 translation"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_jmdict.translate",
            lambda text: "jmdict gloss",
        )

        result = await stage1_runner.run_stage1(
            segment="猫が走る。",
            rag_context="",
            glossary_context="",
        )

        assert isinstance(result, Stage1Drafts)
        assert result.source_jp == "猫が走る。"
        assert result.qwen32b == "qwen32b translation"
        assert result.translategemma12b == "translategemma translation"
        assert result.qwen35_9b == "qwen35 translation"
        assert result.gemma4_e4b == "gemma4 translation"
        assert result.jmdict == "jmdict gloss"

    @pytest.mark.asyncio
    async def test_two_adapters_fail_result_still_has_jmdict(self, monkeypatch):
        """Graceful degradation: failed adapters → None; jmdict always present."""
        from app.pipeline.stage1 import runner as stage1_runner
        from app.pipeline.stage1._types import Stage1Drafts

        async def fail(*a, **kw):
            raise RuntimeError("model unavailable")

        monkeypatch.setattr("app.pipeline.stage1.runner.adapter_qwen32b.translate", fail)
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_translategemma.translate",
            lambda *a, **kw: _async_return("gemma translation"),
        )
        monkeypatch.setattr("app.pipeline.stage1.runner.adapter_qwen35_9b.translate", fail)
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_gemma4.translate",
            lambda *a, **kw: _async_return("gemma4 ok"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_jmdict.translate",
            lambda text: "jmdict fallback",
        )

        result = await stage1_runner.run_stage1(
            segment="テスト", rag_context="", glossary_context=""
        )

        assert result.qwen32b is None
        assert result.translategemma12b == "gemma translation"
        assert result.qwen35_9b is None
        assert result.gemma4_e4b == "gemma4 ok"
        assert result.jmdict == "jmdict fallback"

    @pytest.mark.asyncio
    async def test_oom_triggers_sequential_fallback(self, monkeypatch):
        """When a local adapter raises OOM, runner retries all local adapters sequentially."""
        from app.pipeline.stage1 import runner as stage1_runner

        call_log: list[str] = []

        async def oom_first_call_then_ok(name):
            """Returns a coroutine factory that OOMs on parallel call, succeeds sequentially."""
            call_count = {"n": 0}

            async def inner(*a, **kw):
                call_count["n"] += 1
                # Simulate OOM on first (parallel) attempt
                if call_count["n"] == 1:
                    raise RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
                call_log.append(name)
                return f"{name} sequential result"

            return inner

        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_qwen32b.translate",
            lambda *a, **kw: _async_return("qwen32b ok"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_translategemma.translate",
            await oom_first_call_then_ok("translategemma"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_qwen35_9b.translate",
            await oom_first_call_then_ok("qwen35"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_gemma4.translate",
            await oom_first_call_then_ok("gemma4"),
        )
        monkeypatch.setattr(
            "app.pipeline.stage1.runner.adapter_jmdict.translate",
            lambda text: "jmdict",
        )

        result = await stage1_runner.run_stage1(
            segment="テスト", rag_context="", glossary_context=""
        )

        # All three local adapters should have succeeded in sequential retry
        assert result.translategemma12b == "translategemma sequential result"
        assert result.qwen35_9b == "qwen35 sequential result"
        assert result.gemma4_e4b == "gemma4 sequential result"
        # Qwen32B (Ollama) always runs parallel and is unaffected by local OOM
        assert result.qwen32b == "qwen32b ok"


# ---------------------------------------------------------------------------
# Task 10: __init__.py public API
# ---------------------------------------------------------------------------

class TestPublicAPI:
    def test_run_stage1_importable_from_package(self):
        from app.pipeline.stage1 import run_stage1
        assert callable(run_stage1)

    def test_stage1_drafts_importable_from_package(self):
        from app.pipeline.stage1 import Stage1Drafts
        assert Stage1Drafts is not None

    def test_stage1_drafts_is_correct_type(self):
        from app.pipeline.stage1 import Stage1Drafts
        from app.pipeline.stage1._types import Stage1Drafts as InternalDrafts
        assert Stage1Drafts is InternalDrafts


# ---------------------------------------------------------------------------
# Task 11: pipeline/runner.py integration
# ---------------------------------------------------------------------------

class TestMainRunnerUsesStage1V2:
    def test_runner_imports_run_stage1(self):
        """The main pipeline runner must import from stage1 package."""
        from pathlib import Path
        runner_src = (
            Path(__file__).resolve().parent.parent / "app" / "pipeline" / "runner.py"
        ).read_text(encoding="utf-8")
        assert "from .stage1 import run_stage1" in runner_src or \
               "from app.pipeline.stage1 import run_stage1" in runner_src

    def test_runner_no_longer_has_old_stream_stage1(self):
        """The old _stream_stage1 helper should be removed (replaced by stage1 package)."""
        from pathlib import Path
        runner_src = (
            Path(__file__).resolve().parent.parent / "app" / "pipeline" / "runner.py"
        ).read_text(encoding="utf-8")
        assert "_stream_stage1" not in runner_src
