"""Tests for VerificationService — bilingual fidelity check."""
import json

import pytest

from app.services.verification_service import VerificationResult, VerificationService


CANNED_PASS = json.dumps({
    "fidelity_score": 0.92,
    "missing_content": [],
    "added_content": [],
    "register_match": "match",
    "name_check": "consistent",
    "overall": "pass",
})

CANNED_FAIL = json.dumps({
    "fidelity_score": 0.45,
    "missing_content": ["second clause"],
    "added_content": ["explanatory phrase"],
    "register_match": "drift",
    "name_check": "inconsistent",
    "overall": "fail",
})


@pytest.fixture
def service(monkeypatch) -> VerificationService:
    s = VerificationService()
    return s


@pytest.mark.asyncio
async def test_verify_pass(service, monkeypatch):
    async def fake(url, model, messages, temperature=0.2):
        return CANNED_PASS
    monkeypatch.setattr(service, "_call_model", fake)
    result = await service.verify_paragraph(jp="日本語", en="Japanese")
    assert isinstance(result, VerificationResult)
    assert result.overall == "pass"
    assert result.fidelity_score == 0.92


@pytest.mark.asyncio
async def test_verify_fail(service, monkeypatch):
    async def fake(url, model, messages, temperature=0.2):
        return CANNED_FAIL
    monkeypatch.setattr(service, "_call_model", fake)
    result = await service.verify_paragraph(jp="日本語", en="Japanese")
    assert result.overall == "fail"
    assert "second clause" in result.missing_content


@pytest.mark.asyncio
async def test_verify_handles_extra_text(service, monkeypatch):
    async def fake(url, model, messages, temperature=0.2):
        return f"Here is the assessment:\n```json\n{CANNED_PASS}\n```\nDone."
    monkeypatch.setattr(service, "_call_model", fake)
    result = await service.verify_paragraph(jp="x", en="y")
    assert result.overall == "pass"


@pytest.mark.asyncio
async def test_verify_returns_warning_on_unparsable(service, monkeypatch):
    async def fake(url, model, messages, temperature=0.2):
        return "model said something unstructured"
    monkeypatch.setattr(service, "_call_model", fake)
    result = await service.verify_paragraph(jp="x", en="y")
    assert result.overall == "warning"
    assert result.fidelity_score == 0.0
