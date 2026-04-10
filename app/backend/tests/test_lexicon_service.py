"""Tests for LexiconService — MeCab tokenization + JMdict lookup."""
import pytest

from app.services.lexicon_service import LexiconService, LexiconResult


@pytest.fixture(scope="module")
def lexicon():
    return LexiconService()


def test_translate_returns_lexicon_result(lexicon):
    result = lexicon.translate("猫が走る。")
    assert isinstance(result, LexiconResult)
    assert len(result.tokens) > 0


def test_known_word_has_glosses(lexicon):
    result = lexicon.translate("猫")
    cat_token = next((t for t in result.tokens if t.surface == "猫"), None)
    assert cat_token is not None
    assert any("cat" in g.lower() for g in cat_token.glosses)


def test_unknown_token_listed(lexicon):
    # A made-up name should appear in unknown_tokens or have empty glosses
    result = lexicon.translate("ザクザクラ")  # nonsense katakana
    assert (
        "ザクザクラ" in result.unknown_tokens
        or all(not t.glosses for t in result.tokens if t.surface == "ザクザクラ")
    )


def test_literal_translation_is_string(lexicon):
    result = lexicon.translate("彼女は本を読む。")
    assert isinstance(result.literal_translation, str)
    assert len(result.literal_translation) > 0


def test_confidence_in_range(lexicon):
    result = lexicon.translate("猫が走る。")
    assert 0.0 <= result.confidence <= 1.0


def test_empty_input_returns_empty_result(lexicon):
    result = lexicon.translate("")
    assert result.tokens == []
    assert result.literal_translation == ""
    assert result.unknown_tokens == []
    assert result.confidence == 0.0
