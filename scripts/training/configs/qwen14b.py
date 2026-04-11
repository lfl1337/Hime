"""Qwen2.5-14B-Instruct — v1 LoRA training config."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen14b",
    model="unsloth/Qwen2.5-14B-Instruct-bnb-4bit",
    lora_dir="Qwen2.5-14B-Instruct",
    max_seq=1024,
    grad_accum=16,
    trainer="unsloth",
)
register(CONFIG)
