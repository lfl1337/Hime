import tempfile
from pathlib import Path

import pytest


class TestPathValidation:
    """Test path traversal prevention helpers."""

    def test_resolve_rejects_dotdot(self):
        allowed = Path(tempfile.gettempdir()) / "hime_test_epub"
        allowed.mkdir(exist_ok=True)
        malicious = allowed / ".." / ".." / "etc" / "passwd"
        resolved = malicious.resolve()
        assert not resolved.is_relative_to(allowed)

    def test_resolve_accepts_valid_child(self):
        allowed = Path(tempfile.gettempdir()) / "hime_test_epub"
        allowed.mkdir(exist_ok=True)
        valid = allowed / "book.epub"
        resolved = valid.resolve()
        assert resolved.is_relative_to(allowed)

    def test_rejects_symlink_outside_root(self, tmp_path):
        allowed = tmp_path / "epubs"
        allowed.mkdir()
        outside = tmp_path / "secret.epub"
        outside.write_text("not an epub")
        link = allowed / "sneaky.epub"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Symlink creation requires elevated privileges on Windows")
        resolved = link.resolve()
        assert not resolved.is_relative_to(allowed)
