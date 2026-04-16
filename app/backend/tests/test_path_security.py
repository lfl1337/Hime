"""Tests for path validation utilities in core/paths.py."""
import pytest
from pathlib import Path


def test_validate_safe_name_accepts_normal_names():
    from app.core.paths import validate_safe_name
    assert validate_safe_name("Qwen2.5-32B-Instruct") == "Qwen2.5-32B-Instruct"
    assert validate_safe_name("my_model_v2") == "my_model_v2"
    assert validate_safe_name("checkpoint-42") == "checkpoint-42"


def test_validate_safe_name_rejects_dots_only():
    from app.core.paths import validate_safe_name
    with pytest.raises(ValueError, match="unsafe"):
        validate_safe_name("..")
    with pytest.raises(ValueError, match="unsafe"):
        validate_safe_name(".")
    with pytest.raises(ValueError, match="unsafe"):
        validate_safe_name("...")


def test_validate_safe_name_rejects_path_separators():
    from app.core.paths import validate_safe_name
    with pytest.raises(ValueError, match="unsafe"):
        validate_safe_name("../etc/passwd")
    with pytest.raises(ValueError, match="unsafe"):
        validate_safe_name("foo/bar")
    with pytest.raises(ValueError, match="unsafe"):
        validate_safe_name("foo\\bar")


def test_validate_safe_name_rejects_empty():
    from app.core.paths import validate_safe_name
    with pytest.raises(ValueError, match="unsafe"):
        validate_safe_name("")


def test_validate_safe_name_rejects_null_bytes():
    from app.core.paths import validate_safe_name
    with pytest.raises(ValueError, match="unsafe"):
        validate_safe_name("model\x00evil")


def test_validate_within_directory_accepts_valid_child(tmp_path):
    from app.core.paths import validate_within_directory
    root = tmp_path / "models"
    root.mkdir()
    child = root / "my_model"
    child.mkdir()
    result = validate_within_directory(child, root)
    assert result == child.resolve()


def test_validate_within_directory_rejects_escape(tmp_path):
    from app.core.paths import validate_within_directory
    root = tmp_path / "models"
    root.mkdir()
    escaped = root / ".." / "secrets"
    with pytest.raises(ValueError, match="outside"):
        validate_within_directory(escaped, root)


def test_validate_within_directory_rejects_root_itself(tmp_path):
    from app.core.paths import validate_within_directory
    root = tmp_path / "models"
    root.mkdir()
    with pytest.raises(ValueError, match="outside"):
        validate_within_directory(root, root)
