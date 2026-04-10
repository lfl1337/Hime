"""Tests for RAG chunker."""
from app.rag.chunker import ChunkPair, chunk_paragraph_pairs


def test_returns_one_chunk_per_paragraph():
    pairs = [
        {"book_id": 1, "chapter_id": 10, "paragraph_id": 100,
         "source_text": "JP1", "translated_text": "EN1"},
        {"book_id": 1, "chapter_id": 10, "paragraph_id": 101,
         "source_text": "JP2", "translated_text": "EN2"},
    ]
    chunks = chunk_paragraph_pairs(pairs)
    assert len(chunks) == 2
    assert all(isinstance(c, ChunkPair) for c in chunks)
    assert chunks[0].source_text == "JP1"
    assert chunks[1].source_text == "JP2"


def test_skips_untranslated_paragraphs():
    pairs = [
        {"book_id": 1, "chapter_id": 10, "paragraph_id": 100,
         "source_text": "JP1", "translated_text": ""},
        {"book_id": 1, "chapter_id": 10, "paragraph_id": 101,
         "source_text": "JP2", "translated_text": "EN2"},
    ]
    chunks = chunk_paragraph_pairs(pairs)
    assert len(chunks) == 1
    assert chunks[0].paragraph_id == 101


def test_chunk_index_is_sequential():
    pairs = [
        {"book_id": 1, "chapter_id": 10, "paragraph_id": 100, "source_text": "a", "translated_text": "A"},
        {"book_id": 1, "chapter_id": 10, "paragraph_id": 101, "source_text": "b", "translated_text": "B"},
        {"book_id": 1, "chapter_id": 10, "paragraph_id": 102, "source_text": "c", "translated_text": "C"},
    ]
    chunks = chunk_paragraph_pairs(pairs)
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
