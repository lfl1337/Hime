"""Qwen3.5-9B — v2 Stage 1C translator."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="qwen35-9b",
    model="Qwen/Qwen3.5-9B",
    lora_dir="Qwen3.5-9B",
    max_seq=4096,
    batch_size=4,   # 9B 4-bit ~4.5 GB weights; batch=4 @ seq=4096 fits ~14 GB → safe on 32 GB
    grad_accum=4,   # effective batch = 4×4 = 16 (double the 32B baseline of 1×8=8)
    trainer="unsloth",
    enable_thinking=False,
)
register(CONFIG)
