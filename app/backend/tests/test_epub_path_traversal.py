"""Regression test for the AUDIT-009 path traversal bypass in import_epub()."""
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services.epub_service import _validate_epub_path, import_epub


def test_validate_rejects_path_outside_root(tmp_path: Path):
    safe = tmp_path / "books"
    safe.mkdir()
    bad = tmp_path / "elsewhere" / "evil.epub"
    bad.parent.mkdir()
    bad.write_text("")
    with pytest.raises(ValueError, match="outside allowed directory"):
        _validate_epub_path(str(bad), str(safe))


def test_validate_rejects_null_byte(tmp_path: Path):
    safe = tmp_path / "books"
    safe.mkdir()
    with pytest.raises(ValueError, match="null bytes"):
        _validate_epub_path("hello\x00.epub", str(safe))


def test_validate_rejects_non_epub(tmp_path: Path):
    safe = tmp_path / "books"
    safe.mkdir()
    bad = safe / "evil.txt"
    bad.write_text("")
    with pytest.raises(ValueError, match=".epub"):
        _validate_epub_path(str(bad), str(safe))


@pytest.mark.asyncio
async def test_import_epub_rejects_path_outside_default_root(monkeypatch, tmp_path: Path):
    """The bug fix: import_epub() must validate even when allowed_root is omitted."""
    # Point EPUB_WATCH_DIR at a temp dir
    from app.core import paths
    fake_watch = tmp_path / "watch"
    fake_watch.mkdir()
    monkeypatch.setattr(paths, "EPUB_WATCH_DIR", fake_watch)

    # Place an epub file outside the watch dir
    outside = tmp_path / "outside" / "evil.epub"
    outside.parent.mkdir()
    outside.write_text("")

    fake_session = AsyncMock()
    with pytest.raises(ValueError, match="outside allowed directory"):
        # Note: NO allowed_root passed → must still reject
        await import_epub(str(outside), fake_session)
