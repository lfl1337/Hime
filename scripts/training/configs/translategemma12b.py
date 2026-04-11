"""TranslateGemma-12B-IT — v2 Stage 1B translator (Transformers backend, NOT Unsloth)."""
from . import TrainingConfig, register

CONFIG = TrainingConfig(
    key="translategemma12b",
    model="google/translategemma-12b-it",
    lora_dir="translategemma-12b",
    max_seq=2048,
    grad_accum=16,
    trainer="transformers",
    dtype="bf16",
    quant="nf4",
    notes="Chat template must be preserved; Unsloth is NOT allowed for this model.",
)
register(CONFIG)
