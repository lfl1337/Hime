"""Qwen3.5-9B — v2 Stage 1C translator."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=4096,        # full context — 9B model fits easily on 32 GB (was 2048 for 32B compat)
    batch_size=2,        # reduced from 4 — 96% VRAM at batch=4; batch=2 targets ~22 GB
    grad_accum=8,        # increased from 4 — keeps effective batch = 2×8 = 16
    lora_dropout=0.0,    # enables Unsloth fast CUDA kernels (0.05 disabled them, was 2–3× slower)
    trainer="unsloth",
    enable_thinking=False,
)
register(CONFIG)
