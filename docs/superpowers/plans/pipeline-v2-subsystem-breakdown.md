# Pipeline v2 — Subsystem Breakdown (Updated nach WS2/WS3)

> **Stand:** 2026-04-10 — WS1 + WS2 + WS3 + WS4 abgeschlossen.
> Plan-Dateien: siehe unten.

---

## Was WS2/WS3 geliefert hat

| Komponente | Datei | Was es kann |
|---|---|---|
| RAG System | `app/backend/app/rag/` (7 Dateien) | sqlite-vec Store, bge-m3 Embeddings, Chunker, Retriever, VaultExporter |
| Glossar | `app/backend/app/services/glossary_service.py` | CRUD + `format_for_prompt()` für Pipeline-Injection |
| Lexikon | `app/backend/app/services/lexicon_service.py` | MeCab-Tokenisierung + JMdict-Lookup (= Stage 1E) |
| Flywheel | `app/backend/app/services/flywheel_service.py` | Reviewed translations → Training-Daten exportieren |
| Reader Panel | `app/backend/app/services/reader_panel.py` | 6 Personas via Ollama-Endpoints |
| Verification | `app/backend/app/services/verification_service.py` | JP/EN Paragraph-Verifikation |
| EPUB Import | `app/backend/app/services/epub_service.py` | Import + path-validation |
| DB Schema | `app/backend/app/models.py` | Book, Chapter, Paragraph, Translation, Glossary, GlossaryTerm |
| Routers | `routers/rag.py`, `glossary.py`, `lexicon.py`, `flywheel.py`, `compare.py`, `texts.py`, `translations.py`, `verify.py`, `models.py` | Alle Endpoints vorhanden |

### Was noch NICHT existiert

- `pipeline/runner.py` → **alte Architektur** (3 Ollama-Modelle, kein v2)
- `pipeline/preprocessor.py` → fehlt komplett
- `pipeline/stage1/` → fehlt (neue lokale Inferenz-Adapter)
- `pipeline/stage2_merger.py` → fehlt
- `pipeline/stage3_polish.py` → fehlt
- `pipeline/stage4_aggregator.py` → fehlt
- `pipeline/postprocessor.py` → fehlt
- `services/epub_export_service.py` → fehlt (nur Import vorhanden)
- `scripts/download_models_v2.py` → fehlt
- `scripts/model_inventory_report.py` → fehlt
- `scripts/vault_organizer.py` → fehlt

### Kritische Dep-Lücke

`transformers` und `unsloth` sind **nicht** in `pyproject.toml` (nur `sentence-transformers` für RAG). Alle Stage 1-4 Local-Inference-Workstreams benötigen:
```
transformers>=5.0.0
unsloth
torch  (vermutlich schon installiert)
```
Muss in WS-B als erster Schritt hinzugefügt werden.

---

## Workstream-Übersicht

| WS | Titel | Plan-Datei | Status |
|---|---|---|---|
| WS-A | Pre-Processing (EPUB → Segments → RAG) | `pipeline-v2-ws-a-preprocessing.md` | Plan bereit |
| WS-B | Stage 1 — Lokale Inferenz-Adapter | `pipeline-v2-ws-b-stage1.md` | Plan bereit |
| WS-C | Stage 2+3 — Merger + Polish | `pipeline-v2-ws-c-stage23.md` | Plan bereit |
| WS-D | Stage 4 — Reader Panel ×15 + Aggregator | `pipeline-v2-ws-d-stage4.md` | Plan bereit |
| WS-E | Pipeline Runner v2 + EPUB Export | `pipeline-v2-ws-e-runner.md` | Plan bereit |
| WS-F | Modell-Downloads + Inventory Report | `pipeline-v2-ws-f-downloads.md` | Plan bereit |
| WS-G | Training TranslateGemma-12B + Qwen3.5-9B | *(noch nicht geschrieben)* | Wartet auf Qwen2.5-32B Training-Ende |
| WS-H | Vault Organizer (standalone) | `pipeline-v2-ws-h-vault-organizer.md` | Plan bereit |

---

## Ausführungsreihenfolge

```
SOFORT:
  WS-F (Downloads) ─────── läuft im Hintergrund
  WS-H (Vault Organizer) ─ standalone, unabhängig

PARALLEL DANACH:
  WS-A (Pre-Processing) ── pure Python, alle deps vorhanden
  WS-E (EPUB Export) ───── pure Python, alle deps vorhanden

NACH DOWNLOADS:
  WS-B (Stage 1) ──────────────────────────────────┐
  WS-C (Stage 2+3) ────── nach WS-B ───────────────┼── sequentiell
  WS-D (Stage 4) ─────────────────────────────────-┘

ZULETZT:
  Runner v2 Integration ── alle Stages verdrahten

BLOCKIERT:
  WS-G (Training) ── wartet auf Ende des laufenden Qwen2.5-32B Runs
```

---

## Offene Fragen (vor Ausführung klären)

1. **Qwen3.5 Modell-IDs** — HuggingFace kennt aktuell "Qwen3", nicht "Qwen3.5". IDs vor Download verifizieren.
2. **ReaderPanel v2 Architektur** — aktuell: 6 Personas je eigener Ollama-URL. v2: 1 lokales Qwen3.5-2B mit 15 System-Prompts. Breaking change in Settings-Schema.
3. **LFM2-24B-A2B Transformers ≥5.0.0** — Hybrid-Architektur, kein Unsloth. Verify Transformers version nach dep-update.
4. **TranslateGemma Chat-Template** — muss nach LoRA erhalten bleiben. Testen vor Stage 2 Integration.
