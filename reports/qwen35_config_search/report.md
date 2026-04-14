# Qwen3.5-9B Training Config Search — Living Report

**Hardware:** RTX 5090 (32607 MiB VRAM) | **Model:** Qwen/Qwen3.5-9B (hybrid GatedDeltaNet, 4-bit NF4 QLoRA)  
**Fixed params:** LORA_RANK=16, LORA_ALPHA=32, LR=5e-5, WARMUP=50 steps, EPOCHS=3, GRAD_NORM_CLIP=0.5  
**Dataset:** 94379 training + 10487 eval examples | **Total optimizer steps:** 35394  
**Last updated:** 2026-04-14

---

## Results Table

| Config | max_seq | batch | grad_accum | Speed (s/step) | Speed CV | VRAM peak (MiB) | VRAM baseline | Loss@10 | Loss@30 | Loss@100 | Verdict |
|--------|---------|-------|------------|----------------|----------|-----------------|---------------|---------|---------|----------|---------|
| A | 2048 | 1 | 8 | ~28 (22–33) | ~17% | 31380 | 81–88% | 18.48 | 13.60 | n/a | ❌ Too slow (~11.5 days) |
| B | 1024 | 2 | 4 | — | — | — | — | — | — | — | 🔄 Running |
| C | 1024 | 4 | 2 | — | — | — | — | — | — | — | ⏳ Pending |
| D | 512  | 8 | 1 | — | — | — | — | — | — | — | ⏳ Pending |

---

## Config A — Baseline (Anlauf 3, 2026-04-13)

**Parameters:** `max_seq=2048, batch_size=1, grad_accum=8, lora_dropout=0.0`  
**Effective batch:** 8 | **Tokens/optimizer step:** 16384

### Training Curve
| Step | Loss | grad_norm | LR |
|------|------|-----------|-----|
| 10 | 18.48 | 1.556 | 9e-06 |
| 20 | 16.95 | 1.130 | 1.9e-05 |
| 30 | 13.60 | 1.177 | 2.9e-05 |

### VRAM Profile
- Baseline (active training): 26340–28801 MiB (81–88%)
- Peak spikes: 31027–31380 MiB (95–96%)
- Pattern: spikes every 60–90 s, often at low GPU% (memory management operations)
- Temperature: not measured

### Speed Profile
- Compilation steps 1–8: 22–34 s/step (CUDA kernel compile, ignore)
- Stabilized steps 10–37: 22–33 s/step, mean ≈ 28 s
- Coefficient of variation: ~17% (high oscillation)
- Max observed: 33 s/step | Min observed: 22 s/step

### Projected Duration
35394 steps × 28 s = 990832 s ≈ **11.5 days** ❌

### Analysis
Loss descent: healthy (–8% per 10 steps during warmup, accelerating as LR rises).  
Gradient norm: stable (1.1–1.6), no explosion.  
Primary bottleneck: batch=1 + seq=2048 → serial processing, attention O(n²) at max context.  
VRAM spikes at optimizer steps (low GPU% signature) = optimizer state update memory pressure.  
RTX 5090 running at 162–218W (28–38% of 575W TDP) → severely underutilized compute.

### Verdict
**❌ NOT VIABLE** — 11.5 days per 3-epoch run is unacceptable for iterative development.

---

## Config B — Short Seq, 2× Batch (2026-04-14)

**Parameters:** `max_seq=1024, batch_size=2, grad_accum=4, lora_dropout=0.0`  
**Effective batch:** 8 | **Tokens/optimizer step:** 8192  

### Hypothesis
Halving sequence length reduces attention compute 4× (O(n²) scaling). Doubling batch processes 2 packed sequences in parallel, improving tensor core utilization. Total tokens per optimizer step = 8192 (half of Config A). VRAM footprint for activation checkpoints roughly halved (shorter sequences → smaller intermediate buffers). The GatedDeltaNet SSM layers scale O(n), so they benefit 2× from halved sequence length.

**Predicted speedup:** Attention ~4× faster, SSM ~2× faster, average ~1.6–2.5× → **11–18 s/step**  
**Predicted VRAM:** Activation memory ~2× less → fewer/smaller VRAM spikes, baseline lower

### Training Curve
*(to be filled)*

### VRAM Profile
*(to be filled)*

### Speed Profile
*(to be filled)*

### Projected Duration
*(to be filled)*

### Verdict
*(to be filled)*

---

## Config C — Higher Batch, Short Seq (pending)

**Parameters:** `max_seq=1024, batch_size=4, grad_accum=2, lora_dropout=0.0`  
**Effective batch:** 8 | **Tokens/optimizer step:** 8192  

*(to be filled after run — only if Config B FAILS or MARGINAL)*

---

## Config D — Very Short, Max Batch (pending)

**Parameters:** `max_seq=512, batch_size=8, grad_accum=1, lora_dropout=0.0`  
**Effective batch:** 8 | **Tokens/optimizer step:** 4096  

*(to be filled after run — only if Configs B+C both FAIL or MARGINAL)*

---

## Winner Config

*(to be filled after search completes)*
