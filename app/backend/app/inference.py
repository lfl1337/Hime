"""
Local inference client.

Talks to a local OpenAI-compatible server — llama.cpp (--server flag),
vllm, Ollama with OpenAI shim, etc. — running on localhost.

No data ever leaves the machine. The `api_key` field is required by the
openai SDK's constructor but is ignored by local servers; "local" is used
as a placeholder.
"""
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from .config import settings


# ---------------------------------------------------------------------------
# Generic helpers for multi-model pipeline
# ---------------------------------------------------------------------------

def _make_client(url: str) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=url, api_key="local")


async def complete(
    url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 8192,
    temperature: float = 0.3,
) -> str:
    """Non-streaming completion against an arbitrary local endpoint."""
    response = await _make_client(url).chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


async def stream_completion(
    url: str,
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 8192,
    temperature: float = 0.3,
) -> AsyncIterator[str]:
    """Streaming completion against an arbitrary local endpoint. Yields text deltas."""
    stream = await _make_client(url).chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

_SYSTEM_PROMPT = """\
You are an expert Japanese-to-English light novel translator.

Rules:
- Preserve the author's style, tone, narrative voice, and sentence rhythm.
- Translate honorifics literally and keep them attached (e.g. -san, -kun, -chan, -sama).
- Render onomatopoeia naturally in English; do not transliterate romaji sounds.
- Keep Japanese proper nouns (names, places) unless a canonical English form exists.
- Output only the English translation. Do not include the original Japanese, commentary,
  or explanatory footnotes unless the source text itself contains them.\
"""


def _client() -> AsyncOpenAI:
    return _make_client(settings.inference_url)


def _messages(text: str, notes: str) -> list[dict[str, str]]:
    system = _SYSTEM_PROMPT
    if notes:
        system += f"\n\nAdditional translator notes: {notes}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]


async def translate(text: str, model: str, notes: str = "") -> str:
    """Non-streaming translation. Returns the complete translated string."""
    response = await _client().chat.completions.create(
        model=model,
        messages=_messages(text, notes),
        max_tokens=8192,
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


async def translate_stream(
    text: str, model: str, notes: str = ""
) -> AsyncIterator[str]:
    """
    Streaming translation. Yields text deltas as they arrive from the model.

    Usage:
        async for token in translate_stream(text, model, notes):
            await websocket.send_json({"type": "token", "content": token})
    """
    stream = await _client().chat.completions.create(
        model=model,
        messages=_messages(text, notes),
        max_tokens=8192,
        temperature=0.3,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
