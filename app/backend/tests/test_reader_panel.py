"""Tests for ReaderPanel — multi-persona reviewer ensemble."""
import json

import pytest

from app.services.reader_panel import ReaderPanel, ReviewFinding


class FakeStream:
    """Async iterator yielding a single JSON-string token."""
    def __init__(self, payload: str):
        self.payload = payload

    def __aiter__(self):
        async def gen():
            yield self.payload
        return gen()


@pytest.fixture
def panel(monkeypatch) -> ReaderPanel:
    """A ReaderPanel where the inference call is monkey-patched to return canned JSON."""
    async def fake_inference(url: str, model: str, messages: list[dict]) -> str:
        # Return one finding for the names reader, empty for others
        system = messages[0]["content"]
        if "name-consistency" in system or "Namen" in system or "name" in system.lower():
            return json.dumps([
                {"severity": "warning", "finding": "Aiko vs Aiko-san", "suggestion": "Use Aiko-san"}
            ])
        return "[]"

    p = ReaderPanel()
    monkeypatch.setattr(p, "_call_model", fake_inference)
    return p


@pytest.mark.asyncio
async def test_panel_returns_findings_list(panel):
    findings = await panel.review(translation="Aiko walks home. Aiko-san waves.", source=None)
    assert isinstance(findings, list)
    assert all(isinstance(f, ReviewFinding) for f in findings)


@pytest.mark.asyncio
async def test_panel_includes_reader_field(panel):
    findings = await panel.review(translation="x", source=None)
    readers = {f.reader for f in findings}
    # At least one finding came from the names reader
    assert any("name" in r.lower() for r in readers)


@pytest.mark.asyncio
async def test_empty_translation_returns_empty(panel):
    findings = await panel.review(translation="", source=None)
    assert findings == []


@pytest.mark.asyncio
async def test_malformed_response_does_not_crash(monkeypatch):
    p = ReaderPanel()

    async def bad_inference(url, model, messages):
        return "this is not json"

    monkeypatch.setattr(p, "_call_model", bad_inference)
    findings = await p.review(translation="hello", source=None)
    # Should return empty list, not crash
    assert isinstance(findings, list)
