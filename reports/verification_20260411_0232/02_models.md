# Phase 2 — Modell-Inventar

**Erstellt:** 2026-04-11 02:35
**Gesamtgröße `modelle/`:** 360 GB
**HuggingFace-Cache:** 26 GB

---

## LoRA-Adapter

Einziger LoRA-Adapter: `Qwen2.5-32B-Instruct`

| Unterverzeichnis | adapter_config.json | adapter_model.safetensors | Checkpoints | Größe |
|---|---|---|---|---|
| `adapter/` | Ja (1.253 B) | Ja (512 MB) | — (finaler Adapter) | 529 MB |
| `checkpoint/` | Ja (pro CP) | Ja (pro CP) | 37 Stück (20–620, Schritt 20 mit Extras bei 50, 150, 250, 350, 450, 550) | 29 GB |
| `checkpoint-B/` | Ja | Ja (512 MB) | 1 Stück: checkpoint-12400 | 791 MB |
| `cycle-1/` | Ja (pro CP) | Ja (pro CP) | 7 Stück (20–140, Schritt 20) | 5,4 GB |
| `cycle-2/` | — | — | Verzeichnis `checkpoint/` vorhanden, aber leer | 0 B |

**Gesamt LoRA:** 36 GB

### Qwen2.5-32B Checkpoint-Details (checkpoint-B/checkpoint-12400)

| Feld | Wert |
|---|---|
| `best_metric` | **0.9500** (eval accuracy) |
| `best_model_checkpoint` | `N:\Projekte\NiN\Hime\modelle\lora\Qwen2.5-32B-Instruct\checkpoint-B\checkpoint-12400` |
| `epoch` | 2.1006 |
| `global_step` | 12400 |

**LoRA-Konfiguration (adapter/):**
- `peft_type`: LORA, `r`: 16, `lora_alpha`: 32
- `target_modules`: q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj
- `base_model`: `unsloth/Qwen2.5-32B-Instruct-bnb-4bit`
- `task_type`: CAUSAL_LM

**Smart-Stop-State:**
- `patience_counter`: 1/5, `target_hit_count`: 0/3, `best_metric`: 1.0684 (loss)
- Training wurde nicht durch Smart-Stop beendet

---

## Basismodelle — Soll vs. Ist

| Stage | Modell (Soll) | Erwartetes Format | Pfad | Status | Größe | Anmerkung |
|---|---|---|---|---|---|---|
| 1A | Qwen2.5-32B-Instruct GGUF | GGUF Q4_K_M | `modelle/lmstudio-community/Qwen2.5-32B-Instruct-GGUF/` | OK | 19 GB | 1x `Qwen2.5-32B-Instruct-Q4_K_M.gguf` (18,5 GB) |
| 1A | Qwen2.5-32B LoRA Adapter | Safetensors | `modelle/lora/Qwen2.5-32B-Instruct/adapter/` | OK | 529 MB | Siehe LoRA-Sektion oben |
| 1B | TranslateGemma-12B-IT | Safetensors BF16 | `modelle/translategemma-12b/` | OK | 23 GB | 5 Shards, config.json vorhanden |
| 1C | Qwen3.5-9B | Safetensors (Qwen3_5ForConditionalGeneration) | `modelle/qwen3-9b/` | OK | 19 GB | 4 Shards, VLM-Architektur (Qwen3.5) |
| 1D | Gemma4 E4B | GGUF (alle Quants) | `modelle/gemma4-e4b/` | OK | 118 GB | 22 GGUF-Varianten (Q3_K_S bis BF16) + 3 mmproj |
| 1E | JMdict / MeCab | Algorithmisch | N/A | N/A | — | Kein Modell nötig |
| 2 | TranslateGemma-27B-IT | Safetensors BF16 | `modelle/translategemma-27b/` | OK | 52 GB | 12 Shards, config.json vorhanden |
| 3 | Qwen3-30B-A3B MoE | Safetensors | `modelle/qwen3-30b/` | **UNVOLLSTÄNDIG** | 386 MB | Nur config.json, README, merges.txt — **keine Gewichtsdateien (.safetensors)** |
| 4 | Qwen3.5-2B | Safetensors (Qwen3_5ForConditionalGeneration) | `modelle/qwen3-2b/` | OK | 4,3 GB | 1 Shard (model.safetensors), VLM-Architektur |
| 4 | LFM2-24B-A2B | Safetensors BF16 | `modelle/lfm2-24b/` | OK | 45 GB | 1x `model.safetensors` (44,4 GB), Lfm2MoeForCausalLM |
| 4 alt | LFM2-2B | Safetensors | `modelle/lfm2-2b/` | OK | 4,8 GB | 1x `model.safetensors` (4,8 GB), Lfm2ForCausalLM |

---

## Ollama-Registrierung

| Modell | Registriert | Größe | Pipeline-Relevanz |
|---|---|---|---|
| qwen3.5:4b | Ja | 3,4 GB | Nein (nicht in Pipeline v2) |
| qwen3:4b | Ja | 2,5 GB | Nein |
| bge-m3:latest | Ja | 1,2 GB | Embedding-Modell (evtl. RAG) |
| hibiki-qwen:latest | Ja | 9,0 GB | Nein |
| qwen2.5:7b | Ja | 4,7 GB | Nein |
| nomic-embed-text:latest | Ja | 274 MB | Embedding-Modell |
| kizashi-qwen:latest | Ja | 9,0 GB | Nein |
| kizashi-deepseek:latest | Ja | 9,0 GB | Nein |
| deepseek-r1:14b | Ja | 9,0 GB | Nein |
| qwen2.5:14b | Ja | 9,0 GB | Nein |
| deepseek-r1:32b | Ja | 19 GB | Nein |
| minicpm-v:latest | Ja | 5,5 GB | Nein |

**Ollama-Gesamt:** ~82 GB
**Hinweis:** Keines der Pipeline-v2-Modelle ist über Ollama registriert. Die Pipeline nutzt direkte GGUF/Safetensors-Dateien.

---

## Alt-Modelle (Aufräum-Kandidaten)

| Modell | Pfad | Größe | Empfehlung |
|---|---|---|---|
| DeepSeek-R1-Distill-Qwen-32B-GGUF | `modelle/lmstudio-community/DeepSeek-R1-Distill-Qwen-32B-GGUF/` | 19 GB | Löschen — nicht in Pipeline v2, redundant mit Ollama deepseek-r1:32b |
| gemma-3-27b-it-GGUF | `modelle/lmstudio-community/gemma-3-27b-it-GGUF/` | 17 GB | Löschen — durch Gemma4-E4B ersetzt |
| Qwen2.5-14B-Instruct-GGUF | `modelle/lmstudio-community/Qwen2.5-14B-Instruct-GGUF/` | 8,4 GB | Löschen — nicht in Pipeline v2, redundant mit Ollama qwen2.5:14b |
| Qwen2.5-72B-Instruct-GGUF | nicht gefunden | — | Bereits entfernt oder nie heruntergeladen |
| Gemma4-E4B überflüssige Quants | `modelle/gemma4-e4b/` | ~80 GB einsparbar | Pipeline braucht nur Q4_K_M — BF16 (14 GB), Q8_0 (7,6 GB), Q6_K (6,6 GB) etc. könnten entfernt werden |

**Potenzielle Einsparung Alt-Modelle:** ~44 GB (ohne Gemma4-Quant-Bereinigung)
**Potenzielle Einsparung mit Gemma4-Bereinigung:** ~124 GB

---

## HuggingFace-Cache

**Gesamtgröße:** 26 GB (`~/.cache/huggingface/hub/`)

### Größte Einträge

| Modell | Größe | Duplikat mit `modelle/`? |
|---|---|---|
| `unsloth/Qwen2.5-32B-Instruct-bnb-4bit` | 18 GB | **Ja** — Basismodell für LoRA-Training, wird von Unsloth benötigt |
| `Qwen/Qwen-Image-Edit-2509` | 3,1 GB | Nein — nicht in Pipeline |
| `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | 2,1 GB | Nein — nicht in Pipeline |
| `cardiffnlp/twitter-roberta-base-sentiment-latest` | 957 MB | Nein |
| `kha-white/manga-ocr-base` | 848 MB | Nein — wird für OCR genutzt |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 458 MB | Nein |
| `unitary/toxic-bert` | 418 MB | Nein |
| Diverse (LFM2, Qwen3, TranslateGemma etc.) | je ~1 KB | Nur Metadaten (Symlinks nach `modelle/`) |

**Hinweis:** Die meisten HF-Cache-Einträge für Pipeline-v2-Modelle enthalten nur Metadaten (~1 KB), da die eigentlichen Dateien in `modelle/` liegen. Die Qwen2.5-32B-bnb-4bit-Kopie (18 GB) ist die einzige echte Duplizierung und wird für LoRA-Training benötigt.

---

## Fehlende Modelle

| Modell | HuggingFace-ID | Problem | Priorität |
|---|---|---|---|
| **Qwen3-30B-A3B (Stage 3 Polish)** | `Qwen/Qwen3-30B-A3B` | Nur Konfigurationsdateien vorhanden, **keine Gewichtsdateien** — Download unvollständig/abgebrochen | **HOCH** — Stage 3 nicht lauffähig |

Alle anderen Pipeline-v2-Modelle sind vollständig vorhanden.

---

## Zusammenfassung

- **10 von 11** Pipeline-v2-Modelle sind vollständig vorhanden
- **1 kritischer Fehler:** `qwen3-30b/` (Qwen3-30B-A3B, Stage 3 Polish) hat keine Gewichtsdateien — Download muss wiederholt werden
- **LoRA-Training:** Checkpoint-B (Step 12400) zeigt best_metric 0.95 bei Epoch 2.1 — gutes Ergebnis
- **Speicherverbrauch:** 360 GB in `modelle/`, davon ~124 GB potenziell einsparbar (Alt-Modelle + überflüssige Gemma4-Quants)
- **Ollama:** 82 GB belegt, keines davon direkt Pipeline-relevant
