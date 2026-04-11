# Hime — System Verification Report
**Datum:** 2026-04-11
**Pfad:** N:\Projekte\NiN\Hime
**Git Commit:** baebda0
**Branch:** main
**Aktuelle Version:** 1.1.2
**Zielversion:** 2.0.0

---

## TL;DR

- ✅ Backend-Architektur vollstaendig: 14 Router, 11 Services, 66 Routen, alle importierbar (→ Phase 6, 8)
- ✅ Pipeline v2 Code komplett implementiert: Preprocessing, Stage 1-4, WebSocket-Integration, VRAM-Management (→ Phase 6)
- ✅ 10 von 11 Pipeline-v2-Modellen lokal vorhanden, GPU (RTX 5090, 32 GB VRAM) einsatzbereit (→ Phase 1, 2)
- ✅ Frontend-Backend-API-Mapping lueckenlos: alle 54 Frontend-Calls haben passende Backend-Routen (→ Phase 7)
- ✅ RAG-System vollstaendig implementiert mit Obsidian-Vault-Export (→ Phase 5)

- ⚠️ Stage 3 Modell (Qwen3-30B-A3B) nur Konfigurationsdateien vorhanden, keine Gewichtsdateien (→ Phase 2)
- ⚠️ Trainings-Skript `train_generic.py` unterstuetzt nur v1-Modelle, Pipeline-v2-Modelle fehlen (→ Phase 3)
- ⚠️ Vier separate `hime.db`-Dateien mit unterschiedlichen Datenstaenden (→ Phase 4)
- ⚠️ Stage 4 Aggregator wird in `runner_v2.py` nie explizit geladen — `AttributeError` bei Aufruf erwartet (→ Phase 6)
- ⚠️ Zirkulaerer Import `epub_export_service` ↔ `pipeline.runner_v2` bei isoliertem Import (→ Phase 8)

- ❌ Hybrides Trainingssystem mit dynamisch erweiterbaren Daten fehlt komplett (→ Phase 3)
- ❌ Kein `--dry-run`-Modus fuer Pipeline v2 — Tests ohne aktive Modelle unmoeglich (→ Phase 3, 8)
- ❌ bge-m3 Embedding-Modell nicht lokal heruntergeladen, `modelle/embeddings/` und `data/rag/` existieren nicht (→ Phase 5, 8)
- ❌ VERSION nicht auf v2.0.0 gebumpt, steht noch auf 1.1.2 (→ Phase 0)
- ❌ Curriculum-Learning implementiert aber nicht aktiviert — aktive Config enthaelt keinen Curriculum-Block (→ Phase 3)

- 🎯 **Naechste 3 empfohlene Schritte:**
  1. Qwen3-30B-A3B Gewichtsdateien herunterladen und Stage 4 Aggregator `load()`-Aufruf in `runner_v2.py` fixen
  2. Trainings-Skripte fuer Pipeline-v2-Modelle erweitern (TranslateGemma-12B, Qwen3.5-9B, Qwen3-30B-A3B)
  3. Pipeline v2 End-to-End-Test mit einem einzelnen Buch durchfuehren

---

## 1. Environment

**Quelle: Phase 1 (01_environment.md)**

| Eigenschaft | Wert |
|---|---|
| GPU | NVIDIA GeForce RTX 5090 (32.607 MiB VRAM) |
| CUDA (torch) | 12.8, Treiber 595.97, CUDA 13.2 |
| Python | 3.11.15 (Conda-Env `hime`) |
| torch | 2.11.0+cu128, `torch.cuda.is_available = True` |
| Node.js | v22.20.0, npm 10.9.3 |
| Tauri CLI | 2.10.1 |

**Zwei Python-Environments:**
- **Conda `hime`**: Training/ML (unsloth 2026.4.4, transformers 5.5.0, trl 0.24.0, peft 0.18.1)
- **uv Backend**: Server (fastapi 0.135.1, uvicorn 0.42.0, openai 2.29.0)

Alle deklarierten Backend-Dependencies (pyproject.toml) sind installiert und innerhalb der Versionsanforderungen. → Phase 1

**Fehlende optionale Packages:**
- `flash_attn`: Nicht installiert (optional, Windows-Installation problematisch) → Phase 1
- `pynvml`: Nicht im Conda-Env, aber `nvidia-ml-py` im uv-Backend vorhanden → Phase 1
- `fugashi`: Nicht installiert, `mecab-python3` + `unidic-lite` als funktionierender Ersatz → Phase 1

---

## 2. Modelle

**Quelle: Phase 0 (00_inventory.md), Phase 2 (02_models.md)**

**Gesamtgroesse `modelle/`:** 360 GB | **HuggingFace-Cache:** 26 GB | **Ollama:** ~82 GB

### Pipeline-v2-Modelle: Soll vs. Ist

| Stage | Modell | Format | Status | Groesse | Pfad |
|---|---|---|---|---|---|
| 1A | Qwen2.5-32B-Instruct GGUF + LoRA | GGUF Q4_K_M + Safetensors | **OK** | 19 GB + 529 MB | `modelle/lmstudio-community/Qwen2.5-32B-Instruct-GGUF/` + `modelle/lora/Qwen2.5-32B-Instruct/adapter/` |
| 1B | TranslateGemma-12B-IT | Safetensors BF16 | **OK** | 23 GB | `modelle/translategemma-12b/` |
| 1C | Qwen3.5-9B | Safetensors | **OK** | 19 GB | `modelle/qwen3-9b/` |
| 1D | Gemma4 E4B | GGUF (alle Quants) | **OK** | 118 GB | `modelle/gemma4-e4b/` |
| 1E | JMdict / MeCab | Algorithmisch | **OK** | — | N/A |
| 2 | TranslateGemma-27B-IT | Safetensors BF16 | **OK** | 52 GB | `modelle/translategemma-27b/` |
| 3 | Qwen3-30B-A3B MoE | Safetensors | **UNVOLLSTAENDIG** | 386 MB (nur Config) | `modelle/qwen3-30b/` |
| 4 Reader | Qwen3.5-2B (15 Personas) | Safetensors | **OK** | 4,3 GB | `modelle/qwen3-2b/` |
| 4 Aggregator | LFM2-24B-A2B | Safetensors BF16 | **OK** | 45 GB | `modelle/lfm2-24b/` |

**Hinweis zur Stage-4-Architektur:** Die tatsaechliche Architektur ist **15x Qwen3.5-2B Personas + 1x LFM2-24B-A2B Aggregator** (nicht "5x LFM2" wie in aelteren Specs). Dies ist eine bewusste Design-Entscheidung, dokumentiert in der Pipeline-v2-Spec. → Phase 0

### Fehlende Modelle

| Modell | HuggingFace-ID | Problem | Geschaetzte Groesse | Prioritaet |
|---|---|---|---|---|
| **Qwen3-30B-A3B** (Stage 3 Polish) | `Qwen/Qwen3-30B-A3B` | Nur config.json, README, merges.txt vorhanden — **keine .safetensors Gewichtsdateien**. Download unvollstaendig/abgebrochen. | ~16 GB (BF16 Safetensors) | **HOCH** — Stage 3 nicht lauffaehig |
| **bge-m3** (RAG Embeddings) | `BAAI/bge-m3` | Verzeichnis `modelle/embeddings/bge-m3` existiert nicht. Wird bei erstem Aufruf automatisch heruntergeladen wenn `HIME_ALLOW_DOWNLOADS=true`. | ~1,3 GB | MITTEL — RAG nicht nutzbar ohne |

→ Phase 2, Phase 5

### Alt-Modelle (Aufraeumkandidaten)

| Modell | Pfad | Groesse | Grund |
|---|---|---|---|
| DeepSeek-R1-Distill-Qwen-32B-GGUF | `modelle/lmstudio-community/DeepSeek-R1-Distill-Qwen-32B-GGUF/` | 19 GB | Nicht in Pipeline v2, redundant mit Ollama deepseek-r1:32b |
| gemma-3-27b-it-GGUF | `modelle/lmstudio-community/gemma-3-27b-it-GGUF/` | 17 GB | Durch Gemma4-E4B ersetzt |
| Qwen2.5-14B-Instruct-GGUF | `modelle/lmstudio-community/Qwen2.5-14B-Instruct-GGUF/` | 8,4 GB | Nicht in Pipeline v2, redundant mit Ollama qwen2.5:14b |
| Gemma4-E4B ueberfluessige Quants | `modelle/gemma4-e4b/` | ~80 GB einsparbar | Pipeline braucht nur Q4_K_M — BF16, Q8_0, Q6_K etc. koennten entfernt werden |
| LFM2-2B | `modelle/lfm2-2b/` | 4,8 GB | Nicht in Pipeline-v2-Spec referenziert |
| qwen3-30b (unvollstaendig) | `modelle/qwen3-30b/` | 386 MB | Nur Metadaten — muss komplett neu heruntergeladen werden |

**Potenzielle Einsparung:** ~44 GB (Alt-Modelle) bzw. ~129 GB (inkl. Gemma4-Quant-Bereinigung) → Phase 2

**Claude Code loescht nichts automatisch — Luca entscheidet.**

### LoRA-Training-Status

- **Bester Checkpoint:** `checkpoint-B/checkpoint-12400` mit `best_metric = 0.95` (eval accuracy) bei Epoch 2.1 → Phase 2
- **Aktueller Run:** `checkpoint-620` (Step 620, loss ~0.46, eval_loss ~1.01) — seit 2026-04-06 kein Training mehr gelaufen → Phase 3
- **Overfitting-Tendenz:** train_loss (~0.46) nahe Ziel, aber eval_loss (1.0066) deutlich ueber target_loss (0.4) → Phase 3

---

## 3. Training

**Quelle: Phase 3 (03_training.md)**

### Trainings-Skripte

| Skript | Zeilen | Zweck | Status |
|---|---|---|---|
| `scripts/train_generic.py` | 562 | Generisches LoRA-Training | **Nur v1-Modelle** (qwen32b, qwen14b, qwen72b, gemma27b, deepseek) |
| `scripts/train_hime.py` | 685 | Curriculum-Learning | Curriculum-Code implementiert, aber **nicht aktiviert** |

### KRITISCH: Pipeline-v2-Modelle nicht im Trainings-Skript

`train_generic.py` kennt **keine** Pipeline-v2-Modelle:

| Modell | Stage | Status im Trainings-Skript |
|---|---|---|
| TranslateGemma-12B | Stage 1B | **FEHLT** |
| Qwen3.5-9B | Stage 1C | **FEHLT** |
| Qwen3-30B-A3B MoE | Stage 3 | **FEHLT** |

Das Skript ist monolithisch mit hardcodierten `MODEL_CONFIGS` und nicht modular erweiterbar. → Phase 3

### KRITISCH: Hybrides Trainingssystem fehlt komplett

Folgendes ist **nicht implementiert:**
- Dynamische Datenquellen-Verwaltung (neue Quellen automatisch aufnehmen)
- Hybrid-Architektur (verschiedene Datentypen gewichtet kombinieren)
- Daten-Registry (zentrale Metadaten-Verwaltung aller Trainingsquellen)
- Inkrementelles Training (neue Daten in bestehende Adapter einbringen)

Das aktuelle System kennt nur statische JSONL-Dateien. → Phase 3

### Curriculum-Learning

- Code in `curriculum.py` implementiert und in `train_hime.py` verdrahtet
- **Nicht aktiviert:** Aktive `training_config.json` enthaelt keinen `curriculum`-Block
- Vorgeschlagene Config existiert in `training_config_v121_proposed.json` (Status: "proposed")
- Wenig Fallback-Daten: Nur 1.806 Eintraege mit Score 0.62-0.70 in jparacrawl → Phase 3

### Trainingsdaten

| Datei | Zeilen | Status |
|---|---|---|
| `jparacrawl_500k.jsonl` | 500.000 | OK |
| `hime_training_filtered.jsonl` | 104.866 | OK |
| `shuukura_wn_aligned.jsonl` | 66 | OK |
| `hime_training_all.jsonl` | 104.932 | OK (= filtered + shuukura) |

Alle Dateien vorhanden und konsistent. → Phase 3

---

## 4. Datenbank

**Quelle: Phase 4 (04_database.md)**

### Datenbank-Dateien

| Pfad | Groesse | Buecher | Kapitel | Absaetze | Status |
|---|---|---|---|---|---|
| `hime.db` (Root) | 33,3 MB | 21 | 430 | 80.313 | Produktions-DB |
| `app/backend/hime.db` | 33,0 MB | 21 | 329 | 80.077 | Backend-Kopie (abweichend) |
| `app/hime.db` | 12 KB | — | — | — | Veraltet (altes Schema) |
| `.worktrees/pipeline-v2/hime.db` | 88 KB | 0 | 0 | 0 | Entwicklungs-DB |

### Schema-Status

- **Migrations-System:** Inline in `database.py` (kein Alembic), idempotent
- **ORM-Abgleich:** Alle 8 ORM-Models vorhanden, kleinere Typ-Divergenzen durch Inline-Migrationen (TEXT vs VARCHAR, DEFAULT-Constraints)
- **Foreign Keys:** In allen 4 DBs **deaktiviert** (`PRAGMA foreign_keys = 0`)
- **Legacy-Tabellen:** `source_texts` und `translations` in allen DBs leer (0 Zeilen) — ueberfluessig → Phase 4
- **hardware_stats:** Kein ORM-Model, nur Inline-DDL, wird bei jedem Start gepruned → Phase 4

---

## 5. RAG

**Quelle: Phase 5 (05_rag.md)**

- **Status:** Code vollstaendig implementiert (604 Zeilen, 7 Module)
- **Architektur:** Series-basiert, sqlite-vec Vektorsuche, bge-m3 Embeddings (1024-dim)
- **Backend-Endpoints:** 5 Routen (`/rag/index`, `/rag/query`, `/rag/series/stats`, `/rag/series/delete`, `/rag/vault/sync`)
- **Frontend-Integration:** API-Client + RagIndexPanel-Komponente vorhanden
- **Obsidian-Vault:** Aktiv mit series_1, series_2 und Index-Dateien

**Blockiert durch:**
- bge-m3 Modell nicht lokal vorhanden (`modelle/embeddings/bge-m3` fehlt) → Phase 5
- `data/rag/` Verzeichnis existiert nicht (wird bei erstem Aufruf automatisch erstellt) → Phase 8
- `/rag/query` Endpoint hat keinen Frontend-Caller → Phase 7

---

## 6. Backend

**Quelle: Phase 6 (06_backend.md)**

### Router-Uebersicht

| Router | Prefix | Endpoints | Rate-Limit |
|---|---|---|---|
| texts.py | `/texts` | 4 | POST: 30/min |
| translations.py | `/translations` | 4 | POST: 10/min |
| training.py | `/training` | 18+ | Nein |
| epub.py | `/epub` | 9 | POST: 2-5/min |
| hardware.py | `/hardware` | 4 | Nein |
| compare.py | `/compare` | 1 | Nein |
| models.py | `/models` | 2 | Nein |
| review.py | `/review` | 1 | 10/min |
| lexicon.py | `/lexicon` | 1 | Nein |
| verify.py | `/verify` | 1 | Nein |
| glossary.py | `/books/{id}/glossary` | 5 | Nein |
| flywheel.py | `/training/flywheel` | 1 | Nein |
| rag.py | `/rag` | 5 | Nein |
| pipeline.py | `/pipeline` | 2 (1 REST + 1 WS) | POST: 5/min |
| streaming.py | `/ws` | 2 WS | Nein |

**Gesamt: 15 Router, 66 Routen** (nach Installation von `openai`)

### Pipeline v2 Runner (`runner_v2.py`)

- **Stages korrekt implementiert:** Preprocessing → Stage 1 (parallel, OOM-Fallback) → Stage 2 → Stage 3 → Stage 4 (Reader + Aggregator + Retry-Loop) → DB-Checkpoint → EPUB-Export
- **VRAM-Management:** Gruendlich (torch.cuda.empty_cache, gc.collect, model.cpu + del in finally-Bloecken)
- **WebSocket-Events:** preprocess_complete, segment_start, stage1-4_complete, pipeline_complete/error
- **Retry-Loop:** MAX_STAGE4_RETRIES = 3, Aggregator gibt "okay"/"retry" zurueck

### Sicherheit

- **Kein Auth-Mechanismus** — akzeptabel bei 127.0.0.1-only Binding → Phase 6
- **Path-Traversal-Schutz:** Vorhanden (Null-Byte, Env-Var, Symlink-Checks) → Phase 6
- **Input-Sanitization:** Umfassend (sanitize.py mit 11 Prompt-Injection-Patterns) → Phase 6
- **Audit-Log:** JSON-Lines Format, append-only → Phase 6
- **Rate-Limiting:** slowapi, aber nur auf 7 von 15 Routern endpoint-spezifisch konfiguriert → Phase 6

---

## 7. Frontend

**Quelle: Phase 7 (07_frontend.md)**

### Views

| View | Status | Datei |
|---|---|---|
| Translator | Vorhanden | `src/views/Translator.tsx` |
| Comparison | Vorhanden | `src/views/Comparison.tsx` |
| Editor | Vorhanden | `src/views/Editor.tsx` |
| Training Monitor | Vorhanden | `src/views/TrainingMonitor.tsx` |
| Settings | Vorhanden | `src/views/Settings.tsx` |
| Library | Als Komponente (kein eigenes Routing) | `src/components/epub/BookLibrary.tsx` |
| Glossary | Als Komponente (kein eigenes Routing) | `src/components/GlossaryEditor.tsx` |

### API-Matching

- **54 Frontend-API-Calls** — alle haben korrespondierende Backend-Routen → Phase 7
- **10 Backend-Routen ohne Frontend-Caller:** texts CRUD (GET/DELETE), translations DELETE, models download, lexicon translate, flywheel export, rag query/vault-sync, ws/translate (Legacy) → Phase 7
- **Kein Frontend-Test-Script** und keine Test-Infrastruktur (kein vitest/jest) → Phase 7

### Tauri

- Identifier: `dev.Ninym.hime` — korrekt
- Version: `1.1.2` — konsistent ueber tauri.conf.json, Cargo.toml, package.json
- externalBin: `binaries/hime-backend` konfiguriert
- CSP deaktiviert (`null`) — fuer lokale App akzeptabel → Phase 7

---

## 8. Integrations-Tests

**Quelle: Phase 8 (08_integration_tests.md)**

### Import-Chain

- **14/14 Router-Module:** Alle importieren fehlerfrei → Phase 8
- **10/11 Service-Module:** `epub_export_service` hat zirkulaeren Import mit `pipeline.runner_v2` (funktioniert bei normalem App-Start, nicht bei isoliertem Import) → Phase 8

### Weitere Checks

| Check | Ergebnis |
|---|---|
| Ollama-Daemon | Laeuft (12 Modelle, Port 11434) |
| DB-Read (alle 9 Tabellen) | OK (21 Buecher, 430 Kapitel, 80.313 Absaetze) |
| MeCab Sanity-Check | OK (japanische Tokenisierung funktioniert) |
| Pipeline Dry-Run | **Nicht moeglich** (kein --dry-run Flag) |
| Config-Pfade | 9/11 existieren |

### Fehlende Verzeichnisse

| Pfad | Zweck |
|---|---|
| `modelle/embeddings/` (EMBEDDINGS_DIR) | bge-m3 Embedding-Modell |
| `data/rag/` (RAG_DIR) | RAG-Datenbanken (Series-Stores) |

→ Phase 8

---

## Waehrend der Verifikation behoben

| Fix | Details | Phase |
|---|---|---|
| `openai` SDK installiert | v2.31.0 im uv-Backend — wird ausschliesslich als Client fuer lokale Inference-Server (llama.cpp, vllm, Ollama auf 127.0.0.1) genutzt, keine externen API-Aufrufe | Phase 6 |
| `pynvml` installiert | Fuer GPU-Monitoring im Conda-Env | Phase 1 |
| `fugashi` installiert | Japanische Tokenisierung (ergaenzend zu mecab-python3) | Phase 1 |
| Doppelter `huggingface_hub` Eintrag in `pyproject.toml` entfernt | Zeile 31 und 33 waren identisch (`>=0.24.0`) | Phase 1 |

---

## 🔴 Critical Issues (blockieren Pipeline v2 / Weg zu v2.0.0)

### C1: Stage 3 Modell fehlt — Pipeline v2 nicht lauffaehig
- **Was:** `modelle/qwen3-30b/` enthaelt nur Konfigurationsdateien (config.json, README, merges.txt), **keine Gewichtsdateien (.safetensors)**
- **HuggingFace-ID:** `Qwen/Qwen3-30B-A3B`
- **Warum blockierend:** Stage 3 (Polish) kann nicht ausgefuehrt werden → gesamte Pipeline v2 bricht nach Stage 2 ab
- **Fix:** Download der Safetensors-Dateien (~16 GB) via `huggingface-cli download Qwen/Qwen3-30B-A3B --local-dir modelle/qwen3-30b`
- **Referenz:** Phase 2

### C2: Stage 4 Aggregator wird nie geladen — Runtime-Fehler
- **Was:** In `runner_v2.py` wird `reader.load(settings)` aufgerufen, aber `aggregator.load()` wird **nie** aufgerufen. Bei `_infer_one()` tritt `AttributeError` auf (`self._model` ist None).
- **Warum blockierend:** Stage 4 Aggregation schlaegt bei jedem Aufruf fehl
- **Fix:** `aggregator.load(settings)` Aufruf in `runner_v2.py` vor der Aggregator-Nutzung einfuegen
- **Referenz:** Phase 6

### C3: Trainings-Skripte unterstuetzen keine Pipeline-v2-Modelle
- **Was:** `train_generic.py` hat nur v1-Modelle (qwen32b, qwen14b, qwen72b, gemma27b, deepseek). TranslateGemma-12B, Qwen3.5-9B und Qwen3-30B-A3B fehlen komplett.
- **Warum blockierend:** Ohne Training der Pipeline-v2-Modelle keine qualitativ hochwertigen Uebersetzungen moeglich
- **Fix:** MODEL_CONFIGS erweitern oder modulares Config-System implementieren; separate Trainer-Konfigurationen fuer Unsloth (Qwen3.5-9B, Qwen3-30B-A3B) und Transformers (TranslateGemma-12B)
- **Referenz:** Phase 3

### C4: Hybrides Trainingssystem fehlt komplett
- **Was:** Kein dynamisches Datenquellen-Management, keine Daten-Registry, kein inkrementelles Training, kein Flywheel-Integration ins Training
- **Warum blockierend:** v2.0.0 Ziel beinhaltet dynamisch erweiterbare Trainingsdaten — aktuell nur statische JSONL-Dateien
- **Fix:** Daten-Registry mit Metadaten (Qualitaet, Groesse, Domaene) implementieren; Flywheel-Export als Trainingsquelle integrieren; inkrementelles Adapter-Update ermoeglichen
- **Referenz:** Phase 3

### C5: Curriculum-Learning nicht aktiviert
- **Was:** Code implementiert und verdrahtet, aber aktive `training_config.json` enthaelt keinen `curriculum`-Block. Nur als "proposed" in separater Config vorhanden.
- **Warum blockierend:** Geplante Tier-basierte Trainingsqualitaet (strict→expanded→loose) wird nicht genutzt
- **Fix:** `curriculum`-Block aus `training_config_v121_proposed.json` in aktive `training_config.json` mergen
- **Referenz:** Phase 3

---

## 🟡 Warnings (nicht blockierend, aber zu beachten)

### W1: Vier separate hime.db-Dateien mit unterschiedlichen Datenstaenden
- Root-DB: 430 Kapitel, 80.313 Absaetze vs. Backend-DB: 329 Kapitel, 80.077 Absaetze. Unklar welche autoritativ ist.
- `app/hime.db` ist veraltet (nur 2 Tabellen, altes Schema).
- **Empfehlung:** Autoritative DB festlegen, Rest entfernen oder in .gitignore aufnehmen.
- **Referenz:** Phase 4

### W2: Foreign Keys in allen DBs deaktiviert
- `PRAGMA foreign_keys = 0` in allen 4 Datenbanken. Verwaiste Datensaetze moeglich.
- **Empfehlung:** `PRAGMA foreign_keys = ON` im Connection-Handler setzen.
- **Referenz:** Phase 4

### W3: Zirkulaerer Import epub_export_service ↔ pipeline.runner_v2
- Funktioniert bei normalem App-Start (Python loest den Zirkel auf), schlaegt bei isoliertem Service-Import fehl.
- **Empfehlung:** Lazy Import oder Dependency Injection verwenden.
- **Referenz:** Phase 8

### W4: bge-m3 Embedding-Modell nicht lokal vorhanden
- `modelle/embeddings/bge-m3` existiert nicht. RAG-System nicht nutzbar ohne Download (~1,3 GB).
- **Empfehlung:** `HIME_ALLOW_DOWNLOADS=true` setzen oder Modell manuell herunterladen.
- **Referenz:** Phase 5, Phase 8

### W5: 10 Backend-Routen ohne Frontend-Caller
- texts CRUD (GET/DELETE), translations DELETE, models download, lexicon translate, flywheel export, rag query/vault-sync, ws/translate Legacy.
- **Empfehlung:** Entweder Frontend-Integration ergaenzen oder als "Backend-only/CLI"-Endpoints dokumentieren.
- **Referenz:** Phase 7

### W6: Pipeline v2 Modell-IDs teilweise hardcoded
- Stage 2 und 3 haben HF-IDs direkt im Code, Stage 4 nutzt config-basierte Settings.
- **Empfehlung:** Einheitliches Config-System fuer alle Stages.
- **Referenz:** Phase 6

### W7: Kein Frontend-Test-Infrastruktur
- Kein `test`-Script in package.json, kein vitest/jest in devDependencies.
- **Referenz:** Phase 7

### W8: Kein Pipeline-Dry-Run-Modus
- Weder `runner.py` noch `runner_v2.py` haben `--dry-run`. Tests koennen Pipeline nicht ohne aktive Modelle ausfuehren.
- **Referenz:** Phase 3, Phase 8

### W9: VERSION-Inkonsistenz
- `app/VERSION` = 1.1.2, `main.py` Version = 1.1.2, aber Dokumentation referenziert v1.2.0/v1.2.1.
- **Referenz:** Phase 0, Phase 6

### W10: eval_loss deutlich ueber target
- train_loss ~0.46 (nahe Ziel 0.4), aber eval_loss 1.0066 — Overfitting-Tendenz. Seit 2026-04-06 kein Training mehr gelaufen.
- **Referenz:** Phase 3

---

## 🟢 Alles OK

| Komponente | Status | Referenz |
|---|---|---|
| GPU + CUDA | RTX 5090, 32 GB VRAM, torch.cuda verfuegbar | Phase 1 |
| Conda-Env `hime` | Alle ML-Packages (unsloth, transformers, trl, peft, accelerate, bitsandbytes) installiert | Phase 1 |
| uv Backend-Env | Alle 22 deklarierten Dependencies installiert | Phase 1 |
| Frontend Node-Env | Node 22.20.0, npm 10.9.3, Tauri 2.10.1 | Phase 1 |
| 10/11 Pipeline-v2-Modelle | Vollstaendig vorhanden und korrekt formatiert | Phase 2 |
| Qwen2.5-32B LoRA-Adapter | Finaler Adapter + 37 Checkpoints + checkpoint-B (best_metric 0.95) | Phase 2 |
| Trainingsdaten | 4 JSONL-Dateien konsistent, Zeilenzahlen korrekt | Phase 3 |
| DB-Schema + Migrationen | Idempotentes Inline-System, alle ORM-Models vorhanden | Phase 4 |
| RAG-Code | 604 Zeilen, 7 Module, Series-basiert, sqlite-vec + bge-m3 | Phase 5 |
| Obsidian-Vault-Export | Aktiv mit Index + Series-Chunks | Phase 5 |
| MeCab/JMDict Lexikon | Funktionsfaehig (Tokenisierung + Wort-Glossare) | Phase 5, 8 |
| Backend Import-Chain | 14/14 Router + 10/11 Services importieren fehlerfrei | Phase 8 |
| Input-Sanitization | 11 Prompt-Injection-Patterns, Null-Byte-Schutz, Path-Traversal-Schutz | Phase 6 |
| Audit-Log + Rate-Limiting | JSON-Lines Audit, slowapi mit endpoint-spezifischen Limits | Phase 6 |
| Frontend-Backend API-Match | Alle 54 Frontend-Calls haben passende Backend-Routen | Phase 7 |
| Tauri-Konfiguration | Identifier, Version, Build-Config konsistent | Phase 7 |
| Ollama-Daemon | Laeuft mit 12 Modellen auf Port 11434 | Phase 8 |
| Pipeline v2 Runner-Code | Alle 6 Stages implementiert, VRAM-Management, WebSocket-Events, Retry-Loop | Phase 6 |

---

## Aufraeumempfehlungen

### Alt-Modelle

| Modell | Pfad | Groesse |
|---|---|---|
| DeepSeek-R1-Distill-Qwen-32B-GGUF | `modelle/lmstudio-community/DeepSeek-R1-Distill-Qwen-32B-GGUF/` | 19 GB |
| gemma-3-27b-it-GGUF | `modelle/lmstudio-community/gemma-3-27b-it-GGUF/` | 17 GB |
| Qwen2.5-14B-Instruct-GGUF | `modelle/lmstudio-community/Qwen2.5-14B-Instruct-GGUF/` | 8,4 GB |
| LFM2-2B | `modelle/lfm2-2b/` | 4,8 GB |
| **Summe** | | **~49 GB** |

### Gemma4-E4B Quant-Bereinigung

Pipeline v2 braucht nur Q4_K_M. Ueberfluessige Quantisierungen (BF16, Q8_0, Q6_K, etc.) koennten ~80 GB freigeben. → Phase 2

### Veraltete DB-Dateien

- `app/hime.db` (12 KB, altes Schema) — sicher loeschbar → Phase 4
- `.worktrees/pipeline-v2/hime.db` (88 KB, leere Dev-DB) — nach Worktree-Abschluss loeschbar → Phase 4

### HuggingFace-Cache

- `Qwen/Qwen-Image-Edit-2509` (3,1 GB) — nicht in Pipeline → Phase 2
- `TinyLlama/TinyLlama-1.1B-Chat-v1.0` (2,1 GB) — nicht in Pipeline → Phase 2

**Claude Code loescht nichts automatisch — Luca entscheidet.**

---

## Naechste Schritte — empfohlene Reihenfolge (Weg zu v2.0.0)

### Prio 1: Pipeline v2 lauffaehig machen

1. **Qwen3-30B-A3B Gewichtsdateien herunterladen** — `Qwen/Qwen3-30B-A3B` (~16 GB) nach `modelle/qwen3-30b/`. Ohne dieses Modell ist Stage 3 (Polish) nicht ausfuehrbar. → C1

2. **Stage 4 Aggregator `load()` Bug fixen** — In `runner_v2.py` fehlt der `aggregator.load(settings)` Aufruf. Einzeiler-Fix, aber ohne ihn crasht Stage 4 bei jedem Aufruf. → C2

3. **bge-m3 Embedding-Modell bereitstellen** — `HIME_ALLOW_DOWNLOADS=true` setzen oder `BAAI/bge-m3` (~1,3 GB) nach `modelle/embeddings/bge-m3` herunterladen. → W4

4. **Pipeline v2 End-to-End-Test** — Ein einzelnes Buch durch die komplette Pipeline (Stage 1-4) schicken und alle WebSocket-Events verifizieren.

### Prio 2: Training-System fuer v2.0.0

5. **train_generic.py um Pipeline-v2-Modelle erweitern** — MODEL_CONFIGS fuer TranslateGemma-12B (`google/translate-gemma-12b-it`), Qwen3.5-9B und Qwen3-30B-A3B ergaenzen. → C3

6. **Curriculum-Learning aktivieren** — `curriculum`-Block aus `training_config_v121_proposed.json` in aktive `training_config.json` mergen. → C5

7. **Overfitting adressieren** — eval_loss (1.0066) weit ueber target_loss (0.4). Regularisierung oder Datenerweiterung pruefen. → W10

### Prio 3: Qualitaet und Aufraeumen

8. **Autoritative DB festlegen** — Entscheiden ob `hime.db` (Root) oder `app/backend/hime.db` die Produktions-DB ist. Veraltete `app/hime.db` entfernen. → W1

9. **Frontend-Test-Infrastruktur aufsetzen** — vitest oder aehnliches in devDependencies ergaenzen. → W7

10. **VERSION auf 2.0.0 bumpen** — Erst wenn Pipeline v2 End-to-End laeuft und alle Critical Issues behoben sind. → W9
