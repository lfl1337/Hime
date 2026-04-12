"""Tests for the confidence-log parser used by pipeline/runner.py."""
from app.pipeline.runner import _parse_confidence_log


def test_parses_fenced_json():
    raw = '''Final consensus text here.

```json
{"confidence": [{"sentence": 1, "score": 5}, {"sentence": 2, "score": 3}]}
```
'''
    result = _parse_confidence_log(raw)
    assert result is not None
    assert len(result["confidence"]) == 2
    assert result["confidence"][0]["score"] == 5


def test_returns_none_for_no_block():
    assert _parse_confidence_log("just plain text") is None


def test_handles_no_json_label():
    raw = 'Text\n\n```\n{"confidence": [{"sentence": 1, "score": 4}]}\n```'
    result = _parse_confidence_log(raw)
    assert result is not None
    assert result["confidence"][0]["score"] == 4


def test_returns_none_for_malformed():
    raw = 'Text\n\n```json\n{not valid}\n```'
    assert _parse_confidence_log(raw) is None
