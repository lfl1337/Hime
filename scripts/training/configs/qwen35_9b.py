"""Qwen3.5-9B — v2 Stage 1C translator."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=4096,
    grad_accum=8,
    trainer="unsloth",
    enable_thinking=False,
)
register(CONFIG)
