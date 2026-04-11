"""Offline config+tokenizer load test for Qwen3-30B-A3B (Phase 2 Task 2.6)."""
from transformers import AutoConfig, AutoTokenizer

path = "N:/Projekte/NiN/Hime/modelle/qwen3-30b"

cfg = AutoConfig.from_pretrained(path, trust_remote_code=True)
print(f"architectures: {cfg.architectures}")
print(f"model_type: {cfg.model_type}")
print(f"hidden_size: {cfg.hidden_size}")
print(f"num_hidden_layers: {cfg.num_hidden_layers}")
print(f"num_experts: {cfg.num_experts}")
print(f"num_experts_per_tok: {cfg.num_experts_per_tok}")
print(f"torch_dtype: {cfg.torch_dtype}")
print(f"vocab_size (config): {cfg.vocab_size}")

tok = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
print(f"tokenizer_class: {type(tok).__name__}")
print(f"tokenizer vocab_size: {tok.vocab_size}")
print(f"tokenizer model_max_length: {tok.model_max_length}")

# Smoke test encoding a Japanese string (safe ASCII literal)
sample_jp = "\u3053\u3093\u306b\u3061\u306f\u3001\u4e16\u754c"  # "こんにちは、世界"
encoded = tok(sample_jp)
print(f"encode(<JP sample>) -> {len(encoded['input_ids'])} tokens")

print("[OK] Qwen3-30B-A3B config+tokenizer load")
