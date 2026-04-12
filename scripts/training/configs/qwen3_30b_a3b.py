"""Qwen3-30B-A3B MoE — v2 Stage 3 polisher."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen3-30b-a3b",
    model="Qwen/Qwen3-30B-A3B",
    lora_dir="Qwen3-30B-A3B",
    max_seq=4096,
    grad_accum=16,
    trainer="unsloth",
    enable_thinking=False,
    moe=True,
    notes="MoE: LoRA targets expert layers only; beware grad-checkpointing interactions.",
)
register(CONFIG)
