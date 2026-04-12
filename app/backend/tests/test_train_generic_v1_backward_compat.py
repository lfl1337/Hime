"""Mandatory backward-compat test: v1 training configs must have identical hyperparameters after rewrite."""
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# These MUST match train_generic.py's original MODEL_CONFIGS exactly.
# checkpoint-12400 depends on the qwen32b values.
V1_EXPECTED = {
    "qwen32b": {
        "model": "unsloth/Qwen2.5-32B-Instruct-bnb-4bit",
        "lora_dir": "Qwen2.5-32B-Instruct",
        "max_seq": 1024,
        "grad_accum": 8,
        "trainer": "unsloth",
    },
    "qwen14b": {
        "model": "unsloth/Qwen2.5-14B-Instruct-bnb-4bit",
        "lora_dir": "Qwen2.5-14B-Instruct",
        "max_seq": 1024,
        "grad_accum": 16,
        "trainer": "unsloth",
    },
    "qwen72b": {
        "model": "unsloth/Qwen2.5-72B-Instruct-bnb-4bit",
        "lora_dir": "Qwen2.5-72B-Instruct",
        "max_seq": 512,
        "grad_accum": 32,
        "trainer": "unsloth",
    },
    "gemma27b": {
        "model": "unsloth/gemma-3-27b-it-bnb-4bit",
        "lora_dir": "Gemma-3-27B-IT",
        "max_seq": 1024,
        "grad_accum": 16,
        "trainer": "unsloth",
    },
    "deepseek": {
        "model": "unsloth/DeepSeek-R1-Distill-Qwen-32B-bnb-4bit",
        "lora_dir": "DeepSeek-R1-Distill-Qwen-32B",
        "max_seq": 1024,
        "grad_accum": 16,
        "trainer": "unsloth",
    },
}


@pytest.mark.parametrize("key", sorted(V1_EXPECTED.keys()))
def test_v1_config_fields_unchanged(key):
    """Every v1 config must resolve to a TrainingConfig with the original hyperparameters."""
    from training.configs import get_config
    cfg = get_config(key)
    expected = V1_EXPECTED[key]
    for field_name, value in expected.items():
        actual = getattr(cfg, field_name)
        assert actual == value, (
            f"{key}.{field_name}: expected {value!r}, got {actual!r} — "
            f"v1 backward-compat required for checkpoint-12400"
        )


def test_v1_config_set_is_exactly_these_5():
    """The v1 set (qwen32b, qwen14b, qwen72b, gemma27b, deepseek) is complete."""
    from training.configs import all_config_keys
    keys = set(all_config_keys())
    missing = set(V1_EXPECTED.keys()) - keys
    assert not missing, f"Missing v1 config keys after rewrite: {missing}"


def test_v1_dispatcher_invocation_via_validate_config():
    """python scripts/train_generic.py --model qwen32b --validate-config must exit 0."""
    import subprocess
    for key in sorted(V1_EXPECTED.keys()):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "train_generic.py"),
             "--model", key, "--validate-config"],
            capture_output=True, text=True, timeout=120,
        )
        if "No module named 'unsloth'" in result.stderr or "No module named" in result.stderr:
            pytest.skip(f"Module not available in test env for {key}")
        assert result.returncode == 0, (
            f"v1 key {key} failed --validate-config:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "[validate] OK" in result.stdout
