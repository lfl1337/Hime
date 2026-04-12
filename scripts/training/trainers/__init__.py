"""Trainer plugin registry."""
from __future__ import annotations

from typing import Protocol
from ..configs import TrainingConfig


class TrainerProtocol(Protocol):
    def run(self, config: TrainingConfig, args) -> None: ...
    def validate_config(self, config: TrainingConfig) -> None: ...


_REGISTRY: dict[str, TrainerProtocol] = {}


def register(name: str, trainer: TrainerProtocol) -> None:
    _REGISTRY[name] = trainer


def get_trainer(name: str) -> TrainerProtocol:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown trainer backend: {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


from . import unsloth_trainer as _ut       # noqa: F401, E402
from . import transformers_trainer as _tt  # noqa: F401, E402
