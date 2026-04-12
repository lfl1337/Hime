"""Qwen3.5-9B — v2 Stage 1C translator."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=4096,        # full context — 9B model fits easily on 32 GB (was 2048 for 32B compat)
    batch_size=4,        # 9B is ~4× smaller than 32B → safely fits; better GPU utilisation (was 1)
    grad_accum=4,        # effective batch stays 16 (4×4); fewer overhead steps vs 1×16 (was 16)
    lora_dropout=0.0,    # enables Unsloth fast CUDA kernels (0.05 disabled them, was 2–3× slower)
    trainer="unsloth",
    enable_thinking=False,
)
register(CONFIG)
