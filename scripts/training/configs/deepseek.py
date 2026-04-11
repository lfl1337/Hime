"""DeepSeek-R1-Distill-Qwen-32B — v1 LoRA training config."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="deepseek",
    model="unsloth/DeepSeek-R1-Distill-Qwen-32B-bnb-4bit",
    lora_dir="DeepSeek-R1-Distill-Qwen-32B",
    max_seq=1024,
    grad_accum=16,
    trainer="unsloth",
)
register(CONFIG)
