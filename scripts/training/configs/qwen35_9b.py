"""Qwen3.5-9B — v2 Stage 1C translator."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=2048,   # reduced from 4096 — halves activation VRAM; long seqs truncated
    batch_size=1,   # reduced from 4 — eliminates activation stacking; matches 32B baseline
    grad_accum=16,  # increased from 4 — keeps effective batch = 1×16 = 16
    trainer="unsloth",
    enable_thinking=False,
)
register(CONFIG)
