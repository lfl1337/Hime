"""Training config registry.

Each model has its own module under scripts/training/configs/ that defines
a CONFIG object. Importing this package registers all configs automatically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TrainingConfig:
    key: str                              # CLI key, e.g. "qwen32b"
    model: str                            # HF id or local path
    lora_dir: str                         # subdir under modelle/lora/
    max_seq: int
    grad_accum: int
    trainer: Literal["unsloth", "transformers"] = "unsloth"
    dtype: Literal["bf16", "fp16"] = "bf16"
    quant: Literal["nf4", "int4", "none"] = "nf4"
    batch_size: int = 1
    lora_dropout: float = 0.05   # 0.0 enables Unsloth fast path (2–3× kernel speedup)
    enable_thinking: bool = False
    moe: bool = False
    notes: str = ""
    extra: dict = field(default_factory=dict)


_REGISTRY: dict[str, "TrainingConfig"] = {}


def register(cfg: "TrainingConfig") -> None:
    if cfg.key in _REGISTRY:
        raise ValueError(f"Duplicate training config key: {cfg.key!r}")
    _REGISTRY[cfg.key] = cfg


def get_config(key: str) -> "TrainingConfig":
    if key not in _REGISTRY:
        raise KeyError(f"Unknown training config: {key!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[key]


def all_config_keys() -> list[str]:
    return sorted(_REGISTRY.keys())


# Side-effect imports: each module calls register() on load.
from . import qwen32b as _q32         # noqa: F401, E402
from . import qwen14b as _q14         # noqa: F401, E402
from . import qwen72b as _q72         # noqa: F401, E402
from . import gemma27b as _g27        # noqa: F401, E402
from . import deepseek as _ds         # noqa: F401, E402
from . import translategemma12b as _tg12  # noqa: F401, E402
from . import qwen35_9b as _q359          # noqa: F401, E402
from . import qwen3_30b_a3b as _q330      # noqa: F401, E402
