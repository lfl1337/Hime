"""Qwen2.5-72B-Instruct — v1 LoRA training config."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen72b",
    model="unsloth/Qwen2.5-72B-Instruct-bnb-4bit",
    lora_dir="Qwen2.5-72B-Instruct",
    max_seq=512,
    grad_accum=32,
    trainer="unsloth",
)
register(CONFIG)
