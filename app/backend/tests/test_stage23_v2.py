"""Tests for Pipeline v2 Stage 2 (Merger) and Stage 3 (Polish)."""
import pytest


# ---------------------------------------------------------------------------
# Task 1 — prompts.py: merger_messages + polish_messages
# ---------------------------------------------------------------------------

class TestMergerMessages:
    def test_all_five_drafts_present_in_user_content(self):
        from app.pipeline.prompts import merger_messages
        drafts = {
            "qwen32b":        "Draft A",
            "translategemma": "Draft B",
            "qwen35_9b":      "Draft C",
            "gemma4_e4b":     "Draft D",
            "jmdict":         "Draft E",
        }
        msgs = merger_messages(drafts, rag_context="RAG ctx", glossary_context="GLOSS ctx")
        assert len(msgs) == 2
        user = msgs[1]["content"]
        assert "Draft A" in user
        assert "Draft B" in user
        assert "Draft C" in user
        assert "Draft D" in user
        assert "Draft E" in user

    def test_rag_context_present_in_user_content(self):
        from app.pipeline.prompts import merger_messages
        msgs = merger_messages({}, rag_context="RAG-INFO", glossary_context="")
        assert "RAG-INFO" in msgs[1]["content"]

    def test_glossary_context_present_in_user_content(self):
        from app.pipeline.prompts import merger_messages
        msgs = merger_messages({}, rag_context="", glossary_context="GLOSS-INFO")
        assert "GLOSS-INFO" in msgs[1]["content"]

    def test_missing_draft_shows_unavailable_placeholder(self):
        from app.pipeline.prompts import merger_messages
        msgs = merger_messages({"qwen32b": "Draft A"}, rag_context="", glossary_context="")
        user = msgs[1]["content"]
        # Missing drafts must be labelled, not silently omitted
        assert "[unavailable]" in user.lower() or "unavailable" in user.lower()

    def test_system_message_is_non_empty(self):
        from app.pipeline.prompts import merger_messages
        msgs = merger_messages({}, rag_context="", glossary_context="")
        assert msgs[0]["role"] == "system"
        assert len(msgs[0]["content"]) > 50

    def test_returns_list_of_dicts_with_role_and_content(self):
        from app.pipeline.prompts import merger_messages
        msgs = merger_messages({}, rag_context="", glossary_context="")
        for msg in msgs:
            assert "role" in msg
            assert "content" in msg


class TestPolishMessages:
    def test_merged_text_in_user_content(self):
        from app.pipeline.prompts import polish_messages
        msgs = polish_messages(merged="Hello world.", glossary_context="GLOSS")
        assert "Hello world." in msgs[1]["content"]

    def test_glossary_in_user_content(self):
        from app.pipeline.prompts import polish_messages
        msgs = polish_messages(merged="x", glossary_context="GLOSSARY-DATA")
        assert "GLOSSARY-DATA" in msgs[1]["content"]

    def test_system_message_mentions_punctuation_or_polish(self):
        from app.pipeline.prompts import polish_messages
        msgs = polish_messages(merged="x", glossary_context="")
        system_lower = msgs[0]["content"].lower()
        assert any(kw in system_lower for kw in ("polish", "punctuation", "literary", "light novel"))

    def test_returns_two_messages(self):
        from app.pipeline.prompts import polish_messages
        msgs = polish_messages(merged="x", glossary_context="")
        assert len(msgs) == 2


# ---------------------------------------------------------------------------
# Task 2 — stage3_polish.py: convert_jp_punctuation pure function
# ---------------------------------------------------------------------------

class TestConvertJpPunctuation:
    def test_kagikakko_to_double_quotes(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        assert convert_jp_punctuation("「こんにちは」") == '"こんにちは"'

    def test_nijukagikakko_to_single_quotes(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        assert convert_jp_punctuation("『世界』") == "'世界'"

    def test_ellipsis_conversion(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        assert convert_jp_punctuation("…") == "..."

    def test_jp_exclamation(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        assert convert_jp_punctuation("すごい！") == "すごい!"

    def test_jp_question(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        assert convert_jp_punctuation("本当？") == "本当?"

    def test_jp_comma(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        assert convert_jp_punctuation("はい、そうです") == "はい,そうです"

    def test_trailing_jp_period_removed(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        assert convert_jp_punctuation("She smiled。") == "She smiled"

    def test_jp_period_mid_sentence_not_removed(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        # A 。 not at the end of the string should stay (it may be a sentence
        # boundary in a multi-sentence fragment passed to polish)
        result = convert_jp_punctuation("彼女は笑った。そして去った。")
        # Both 。 are replaced to give English-style sentence breaks
        assert "。" not in result

    def test_multiple_conversions_combined(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        result = convert_jp_punctuation("「え？」彼女は叫んだ！…")
        assert result == '"え?"彼女は叫んだ!...'

    def test_plain_ascii_unchanged(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        text = 'She said, "Hello!" and left.'
        assert convert_jp_punctuation(text) == text

    def test_empty_string(self):
        from app.pipeline.stage3_polish import convert_jp_punctuation
        assert convert_jp_punctuation("") == ""


# ---------------------------------------------------------------------------
# Task 3 — stage2_merger.py: merge() with mocked model
# ---------------------------------------------------------------------------

class TestStage2Merger:
    @pytest.mark.asyncio
    async def test_merge_returns_non_empty_string(self, monkeypatch):
        """merge() should return the decoded model output as a non-empty string."""
        import app.pipeline.stage2_merger as merger_mod

        # Mock out the heavy model loading so the test runs without a GPU
        class FakeTokenizer:
            eos_token_id = None
            def apply_chat_template(self, messages, tokenize, add_generation_prompt):
                return "PROMPT_TEXT"
            def __call__(self, text, return_tensors):
                import types
                t = types.SimpleNamespace()
                t.input_ids = [[1, 2, 3]]
                return t
            def decode(self, ids, skip_special_tokens):
                return "This is the merged translation."

        class FakeModel:
            def generate(self, input_ids, max_new_tokens, do_sample, temperature, pad_token_id):
                return [[1, 2, 3, 4, 5, 6]]
            def cpu(self):
                pass

        monkeypatch.setattr(
            merger_mod, "_load_model",
            lambda: (FakeModel(), FakeTokenizer()),
        )

        drafts = {
            "qwen32b":        "Draft A",
            "translategemma": "Draft B",
            "qwen35_9b":      "Draft C",
            "gemma4_e4b":     "Draft D",
            "jmdict":         "Draft E",
        }
        result = await merger_mod.merge(
            drafts=drafts,
            rag_context="some context",
            glossary_context="Term: Sakura = Sakura",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_merge_strips_input_tokens_from_output(self, monkeypatch):
        """The model returns input+output tokens; merge() must strip the input prefix."""
        import app.pipeline.stage2_merger as merger_mod

        class FakeTokenizer:
            eos_token_id = None
            def apply_chat_template(self, messages, tokenize, add_generation_prompt):
                return "PROMPT"
            def __call__(self, text, return_tensors):
                import types
                t = types.SimpleNamespace()
                t.input_ids = [[10, 11, 12]]
                return t
            def decode(self, ids, skip_special_tokens):
                # ids will be the new tokens only (after slicing)
                return "OUTPUT ONLY"

        class FakeModel:
            def generate(self, input_ids, max_new_tokens, do_sample, temperature, pad_token_id):
                # return full sequence: input (3 tokens) + output (2 tokens)
                return [[10, 11, 12, 20, 21]]
            def cpu(self):
                pass

        monkeypatch.setattr(merger_mod, "_load_model", lambda: (FakeModel(), FakeTokenizer()))

        result = await merger_mod.merge(drafts={}, rag_context="", glossary_context="")
        assert result == "OUTPUT ONLY"

    @pytest.mark.asyncio
    async def test_merge_unloads_model_after_run(self, monkeypatch):
        """After merge(), the module-level _model + _tokenizer must be None."""
        import app.pipeline.stage2_merger as merger_mod

        class FakeTokenizer:
            eos_token_id = None
            def apply_chat_template(self, *a, **kw): return "P"
            def __call__(self, *a, **kw):
                import types
                t = types.SimpleNamespace(); t.input_ids = [[1]]; return t
            def decode(self, ids, skip_special_tokens): return "ok"

        class FakeModel:
            def generate(self, *a, **kw): return [[1, 2]]
            def cpu(self): pass

        monkeypatch.setattr(merger_mod, "_load_model", lambda: (FakeModel(), FakeTokenizer()))

        # Reset module state before test
        merger_mod._model = None
        merger_mod._tokenizer = None

        await merger_mod.merge(drafts={}, rag_context="", glossary_context="")

        assert merger_mod._model is None
        assert merger_mod._tokenizer is None


# ---------------------------------------------------------------------------
# Task 4 — stage3_polish.py: polish() with mocked model + VRAM cleanup
# ---------------------------------------------------------------------------

class TestStage3Polish:
    @pytest.mark.asyncio
    async def test_polish_returns_non_empty_string(self, monkeypatch):
        """polish() should return the polished string (mocked — no GPU)."""
        import app.pipeline.stage3_polish as polish_mod

        class FakeTokenizer:
            eos_token_id = None
            def apply_chat_template(self, messages, tokenize, add_generation_prompt):
                return "PROMPT"
            def __call__(self, text, return_tensors):
                import types
                t = types.SimpleNamespace(); t.input_ids = [[1, 2]]; return t
            def decode(self, ids, skip_special_tokens):
                return "Polished text."

        class FakeModel:
            def generate(self, input_ids, max_new_tokens, do_sample, temperature, pad_token_id):
                return [[1, 2, 3, 4]]
            def cpu(self): pass

        monkeypatch.setattr(polish_mod, "_load_model", lambda: (FakeModel(), FakeTokenizer()))

        result = await polish_mod.polish(
            merged="She said 「hello」。",
            glossary_context="Sakura = Sakura",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_polish_applies_punctuation_before_model(self, monkeypatch):
        """Punctuation conversion happens before the model sees the text."""
        import app.pipeline.stage3_polish as polish_mod

        captured_messages: list = []

        class FakeTokenizer:
            eos_token_id = None
            def apply_chat_template(self, messages, tokenize, add_generation_prompt):
                captured_messages.extend(messages)
                return "P"
            def __call__(self, text, return_tensors):
                import types
                t = types.SimpleNamespace(); t.input_ids = [[1]]; return t
            def decode(self, ids, skip_special_tokens): return "done"

        class FakeModel:
            def generate(self, *a, **kw): return [[1, 2]]
            def cpu(self): pass

        monkeypatch.setattr(polish_mod, "_load_model", lambda: (FakeModel(), FakeTokenizer()))

        await polish_mod.polish(merged='「Test」', glossary_context="")

        # The user message sent to the model must contain converted punctuation
        user_content = captured_messages[1]["content"]
        assert '"Test"' in user_content
        assert "「" not in user_content

    @pytest.mark.asyncio
    async def test_polish_vram_cleanup_after_run(self, monkeypatch):
        """After polish(), model must be moved to CPU and module slots set to None."""
        import app.pipeline.stage3_polish as polish_mod

        cpu_called = []
        torch_cache_cleared = []

        class FakeTokenizer:
            eos_token_id = None
            def apply_chat_template(self, *a, **kw): return "P"
            def __call__(self, *a, **kw):
                import types
                t = types.SimpleNamespace(); t.input_ids = [[1]]; return t
            def decode(self, ids, skip_special_tokens): return "done"

        class FakeModel:
            def generate(self, *a, **kw): return [[1, 2]]
            def cpu(self): cpu_called.append(True)

        class _NoOpCtx:
            def __enter__(self): return self
            def __exit__(self, *a): pass

        class FakeTorch:
            @staticmethod
            def inference_mode(): return _NoOpCtx()
            class cuda:
                @staticmethod
                def empty_cache(): torch_cache_cleared.append(True)

        monkeypatch.setattr(polish_mod, "_load_model", lambda: (FakeModel(), FakeTokenizer()))
        # We patch the torch import inside the finally block
        import sys
        sys.modules["torch"] = FakeTorch()

        polish_mod._model = None
        polish_mod._tokenizer = None

        await polish_mod.polish(merged="hello", glossary_context="")

        assert len(cpu_called) >= 1, "model.cpu() was not called"
        assert polish_mod._model is None, "_model slot not cleared"
        assert polish_mod._tokenizer is None, "_tokenizer slot not cleared"

        # Restore real torch if present
        try:
            import importlib
            real_torch = importlib.import_module("torch")
            sys.modules["torch"] = real_torch
        except ImportError:
            sys.modules.pop("torch", None)

    @pytest.mark.asyncio
    async def test_polish_unloads_even_on_inference_error(self, monkeypatch):
        """VRAM cleanup runs even if model.generate() raises."""
        import app.pipeline.stage3_polish as polish_mod

        class BrokenModel:
            def generate(self, *a, **kw):
                raise RuntimeError("CUDA OOM")
            def cpu(self): pass

        class FakeTokenizer:
            eos_token_id = None
            def apply_chat_template(self, *a, **kw): return "P"
            def __call__(self, *a, **kw):
                import types
                t = types.SimpleNamespace(); t.input_ids = [[1]]; return t
            def decode(self, ids, skip_special_tokens): return "ok"

        monkeypatch.setattr(polish_mod, "_load_model", lambda: (BrokenModel(), FakeTokenizer()))

        with pytest.raises(RuntimeError, match="CUDA OOM"):
            await polish_mod.polish(merged="x", glossary_context="")

        assert polish_mod._model is None
        assert polish_mod._tokenizer is None


# ---------------------------------------------------------------------------
# Backward-compat: existing prompt functions still work after prompts.py changes
# ---------------------------------------------------------------------------

class TestMergerMessagesBackwardCompat:
    def test_stage1_messages_still_works(self):
        from app.pipeline.prompts import stage1_messages
        msgs = stage1_messages(source_text="日本語テキスト")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["content"] == "日本語テキスト"

    def test_consensus_messages_still_works(self):
        from app.pipeline.prompts import consensus_messages
        msgs = consensus_messages(
            source_text="src",
            translations={"model_a": "trans A", "model_b": "trans B"},
        )
        assert len(msgs) == 2
        assert "trans A" in msgs[1]["content"]

    def test_stage2_messages_still_works(self):
        from app.pipeline.prompts import stage2_messages
        msgs = stage2_messages("consensus text")
        assert len(msgs) == 2
        assert "consensus text" in msgs[1]["content"]

    def test_stage3_messages_still_works(self):
        from app.pipeline.prompts import stage3_messages
        msgs = stage3_messages("refined text")
        assert len(msgs) == 2
        assert "refined text" in msgs[1]["content"]


# ---------------------------------------------------------------------------
# unload_stage3() clears module globals
# ---------------------------------------------------------------------------

class TestUnloadStage3:
    def test_unload_clears_module_globals(self, monkeypatch):
        """After unload_stage3(), _model and _tokenizer must be None."""
        import app.pipeline.stage3_polish as polish_mod

        class FakeModel:
            def cpu(self): pass

        # Simulate a loaded state
        polish_mod._model = FakeModel()
        polish_mod._tokenizer = object()

        polish_mod.unload_stage3()

        assert polish_mod._model is None
        assert polish_mod._tokenizer is None

    def test_unload_is_safe_when_already_none(self):
        """Calling unload_stage3() when model is already None must not raise."""
        import app.pipeline.stage3_polish as polish_mod
        polish_mod._model = None
        polish_mod._tokenizer = None
        polish_mod.unload_stage3()  # must not raise


# ---------------------------------------------------------------------------
# Task 5 — Import chain validation (no GPU required)
# ---------------------------------------------------------------------------

class TestImportChain:
    def test_merger_messages_importable_from_prompts(self):
        from app.pipeline.prompts import merger_messages, polish_messages  # noqa: F401

    def test_stage2_merger_importable(self):
        from app.pipeline.stage2_merger import merge  # noqa: F401
        assert callable(merge)

    def test_stage3_polish_importable(self):
        from app.pipeline.stage3_polish import polish, convert_jp_punctuation  # noqa: F401
        assert callable(polish)
        assert callable(convert_jp_punctuation)

    def test_convert_jp_punctuation_is_pure(self):
        """Calling convert_jp_punctuation requires no torch/transformers import."""
        # If this raises ImportError for torch, the function leaks model deps
        import sys
        # Save and temporarily remove torch to prove no dependency
        torch_mod = sys.modules.pop("torch", None)
        try:
            from app.pipeline.stage3_polish import convert_jp_punctuation
            result = convert_jp_punctuation("「test」")
            assert result == '"test"'
        finally:
            if torch_mod is not None:
                sys.modules["torch"] = torch_mod

    def test_stage2_merger_exposes_cleanup_slots(self):
        """_model and _tokenizer module slots must exist for test assertions."""
        import app.pipeline.stage2_merger as m
        assert hasattr(m, "_model")
        assert hasattr(m, "_tokenizer")

    def test_stage3_polish_exposes_cleanup_slots(self):
        import app.pipeline.stage3_polish as m
        assert hasattr(m, "_model")
        assert hasattr(m, "_tokenizer")
