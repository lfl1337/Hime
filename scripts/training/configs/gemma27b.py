"""Gemma 3-27B-IT — v1 LoRA training config."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="gemma27b",
    model="unsloth/gemma-3-27b-it-bnb-4bit",
    lora_dir="Gemma-3-27B-IT",
    max_seq=1024,
    grad_accum=16,
    trainer="unsloth",
)
register(CONFIG)
