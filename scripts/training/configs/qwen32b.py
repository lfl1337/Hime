"""Qwen2.5-32B-Instruct — v1 LoRA training config (backward-compat, checkpoint-12400)."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen32b",
    model="unsloth/Qwen2.5-32B-Instruct-bnb-4bit",
    lora_dir="Qwen2.5-32B-Instruct",
    max_seq=1024,
    grad_accum=8,
    trainer="unsloth",
)
register(CONFIG)
