# Phase 6 — Backend-Code-Integration

## Einstiegspunkt

### main.py
- **FastAPI-App**: Instanz erstellt mit `title="Hime Translation API"`, `version="1.1.2"`, `lifespan=lifespan`
- **Lifespan-Handler**: Initialisiert DB (`init_db()`), fuehrt initialen EPUB-Scan durch, startet `_scan_loop` als Background-Task (alle 60s EPUB-Ordner scannen). Hardware-Loop ist seit v0.8.0 deaktiviert (auskommentiert).
- **Request-Logging**: HTTP-Middleware loggt alle Requests mit Methode, Pfad, Status und Dauer.
- **Rate-Limiting**: slowapi-Limiter auf `app.state` registriert, Exception-Handler fuer `RateLimitExceeded`.
- **Audit-Middleware**: `AuditMiddleware` registriert mit `settings.audit_log_path`.
- **15 Router** registriert (14 mit `/api/v1` Prefix + 1 WebSocket ohne Prefix).

### run.py
- **Binding**: `_HOST = "127.0.0.1"` — hardcoded, Kommentar warnt explizit vor Aenderung zu `0.0.0.0`
- **Port**: Standard `settings.port` (Default 18420), mit automatischer Suche nach freiem Port via `find_free_port(start=settings.port)`
- **Lock-File**: Schreibt `hime-backend.lock` (JSON mit port + pid) in Data-Dir
- **Data-Dir**: Unterstuetzt `--data-dir` (Tauri Sidecar), frozen PyInstaller, und Dev-Modus

### CORS
- **Erlaubte Origins**: `http://localhost:1420` (Tauri Vite Dev) + `https://tauri.localhost` (Packaged Tauri App)
- **Methoden**: GET, POST, PUT, DELETE
- **Headers**: Content-Type, X-API-Key
- **Credentials**: erlaubt

### Middleware
| Middleware | Typ | Details |
|---|---|---|
| `_log_requests` | HTTP-Middleware (Decorator) | Loggt Methode, Pfad, Status, Dauer (ms) |
| `AuditMiddleware` | Starlette BaseHTTPMiddleware | JSON-Lines Audit-Log (ts, method, path, status, duration_ms, client) |
| Rate-Limiter (slowapi) | App-State + Exception-Handler | `get_remote_address` als Key, Default-Limit aus `settings.rate_limit_per_minute` |
| CORSMiddleware | FastAPI built-in | Strikte Origins (siehe oben) |

---

## Router-Inventar

| Router-Datei | Prefix | Endpoints | Auth | Rate-Limit |
|---|---|---|---|---|
| texts.py | `/texts` | `POST /` (SourceTextRead, 201), `GET /` (list), `GET /{text_id}`, `DELETE /{text_id}` | Nein | POST: 30/min |
| translations.py | `/translations` | `POST /translate` (TranslateJobResponse, 202), `GET /` (list), `GET /{translation_id}`, `DELETE /{translation_id}` | Nein | POST: 10/min |
| training.py | `/training` | `GET /status`, `GET /checkpoints`, `GET /loss-history`, `GET /log`, `GET /runs`, `GET /gguf-models`, `GET /stream` (SSE), `POST /start`, `POST /stop`, `POST /save-checkpoint`, `GET /processes`, `GET /available-checkpoints/{model_name}`, `GET /config`, `POST /config`, `GET /stop-config`, `PUT /stop-config`, `GET /conda-envs`, `GET /backend-log` | Nein | Nein |
| epub.py | `/epub` | `POST /import` (201), `GET /books`, `GET /books/{book_id}/chapters`, `GET /chapters/{chapter_id}/paragraphs`, `POST /paragraphs/{paragraph_id}/translation` (204), `GET /export/{chapter_id}`, `POST /books/{book_id}/rescan`, `PATCH /books/{book_id}`, `GET /settings`, `POST /settings` (204) | Nein | POST /import: 5/min, POST /rescan: 2/min, PATCH: 10/min |
| hardware.py | `/hardware` | `GET /stats`, `GET /history`, `GET /memory-detail`, `GET /stream` (SSE) | Nein | Nein |
| compare.py | `/compare` | `POST ` (job_id) | Nein | Nein |
| models.py | `/models` | `GET ` (list), `POST /{model_key}/download` | Nein | Nein |
| review.py | `/review` | `POST ` (ReviewResponse) | Nein | 10/min |
| lexicon.py | `/lexicon` | `GET /translate` | Nein | Nein |
| verify.py | `/verify` | `POST ` (VerificationResult) | Nein | Nein |
| glossary.py | `/books/{book_id}/glossary` | `GET ` (GlossaryResponse), `POST /terms`, `PUT /terms/{term_id}`, `DELETE /terms/{term_id}`, `POST /auto-extract` | Nein | Nein |
| flywheel.py | `/training/flywheel` | `POST /export` (FlywheelExportResponse) | Nein | Nein |
| rag.py | `/rag` | `POST /index/{book_id}`, `POST /query`, `GET /series/{series_id}/stats`, `DELETE /series/{series_id}`, `POST /vault/sync` | Nein | Nein |
| pipeline.py | `/pipeline` | `POST /{book_id}/preprocess` (PreprocessResponse), `WS /{book_id}/translate` | Nein | POST: 5/min |
| streaming.py (websocket) | *(kein /api/v1)* | `WS /ws/translate`, `WS /ws/translate/{job_id}` | Nein | Nein |

### Soll-Abgleich

| Erwarteter Router | Status | Bemerkung |
|---|---|---|
| translate.py | Umbenannt zu `translations.py` | Prefix `/translations`, enthaelt `/translate` Endpoint |
| compare.py | Vorhanden | Prefix `/compare` |
| models.py | Vorhanden | Prefix `/models` |
| training.py | Vorhanden | Prefix `/training` (umfangreichster Router, 18+ Endpoints) |
| history.py | Fehlt als eigene Datei | Historien-Funktionalitaet in `translations.py` (GET /) und `training.py` (loss-history) integriert |
| books.py / epub.py | Vorhanden als `epub.py` | Prefix `/epub`, enthaelt Books + Chapters + Paragraphs |
| rag.py | Vorhanden | Prefix `/rag` |
| pipeline.py | Vorhanden | Prefix `/pipeline` (Pipeline v2) |

**Zusaetzliche Router** (nicht in Erwartungsliste):
- `hardware.py` — Hardware-Monitoring (GPU/CPU/RAM)
- `review.py` — Reader-Panel Review
- `lexicon.py` — Algorithmische JP-EN Uebersetzung (MeCab + JMDict)
- `verify.py` — Bilinguale Fidelity-Verifikation
- `glossary.py` — Glossar-CRUD pro Buch
- `flywheel.py` — Export reviewter Uebersetzungen als Trainingsdaten
- `texts.py` — Quelltext-CRUD (SourceText)

---

## Services

| Service | Zeilen | Klassen / Funktionen |
|---|---|---|
| epub_service.py | 513 | `_validate_epub_path`, `_split_sentences`, `_extract_toc_titles`, `_is_valid_title`, `_split_by_headings`, `_parse_epub_sync`, `import_epub`, `rescan_book_chapters`, `scan_watch_folder`, `get_library`, `get_chapters`, `get_paragraphs`, `save_translation`, `export_chapter`, `update_book_series`, `get_setting`, `set_setting`, `_book_to_dict`, `_chapter_to_dict`, `_paragraph_to_dict` |
| training_monitor.py | 698 | Klassen: `EtaInfo`, `StopConfigStatus`, `TrainingStatus`, `CheckpointInfo`, `LossPoint`, `RunInfo`, `GGUFModelInfo`. Funktionen: `get_training_status`, `get_checkpoints`, `get_loss_history`, `get_log_tail`, `get_all_runs`, `get_gguf_models`, `stream_events`, `parse_eta_from_log` u.a. |
| training_runner.py | 445 | Klasse: `TrainingProcess`. Funktionen: `start_training`, `stop_training`, `get_running_processes`, `get_available_checkpoints`, `_create_job_object`, `_assign_to_job`, `_kill_survivors` |
| hardware_monitor.py | 383 | Klassen: `HardwareStats`, `MemoryDetail`. Funktionen: `get_hardware_stats`, `save_hardware_stats`, `cleanup_old_hardware_stats`, `get_hardware_history`, `vacuum_hardware_db`, `get_memory_detail` |
| glossary_service.py | 167 | Klassen: `GlossaryTerm`, `Glossary`, `GlossaryService` |
| epub_export_service.py | 136 | Funktionen: `_build_epub_sync`, `export_book` |
| reader_panel.py | 131 | Klassen: `ReviewFinding`, `ReaderPanel`. Funktionen: `_load_prompt`, `_resolve_url` |
| verification_service.py | 113 | Klassen: `VerificationResult`, `VerificationService`. Funktionen: `_load_template`, `_extract_json` |
| lexicon_service.py | 110 | Klassen: `LexiconToken`, `LexiconResult`, `LexiconService`. Funktionen: `_get_tagger`, `_get_jam`, `_glosses_for` |
| flywheel_service.py | 92 | Klasse: `FlywheelService`. Funktionen: `_hash`, `_extract_fidelity` |
| model_manager.py | 88 | Funktionen: `get_model_configs`, `check_model_health`, `check_all_models` |

---

## Pipeline-Orchestrator (runner_v2.py)

### Stage-Reihenfolge
**Korrekt**: `preprocessor` -> `stage1` (parallel) -> `stage2_merger` -> `stage3_polish` -> `stage4` (Reader + Aggregator mit Retry-Loop) -> DB-Checkpoint -> EPUB-Export

### Modell-Konfiguration
- **Stage 1**: 5 Adapter (Qwen32B via Ollama, TranslateGemma-12B, Qwen3.5-9B, Gemma4-E4B, JMDict CPU-only). Modell-Pfade teils aus `HIME_MODELS_DIR` Env-Variable, teils aus HuggingFace-IDs.
- **Stage 2**: TranslateGemma-27B (`google/translategemma-27b-it`), lokaler Pfad via `HIME_MODELS_DIR/translategemma-27b`
- **Stage 3**: Qwen3-30B-A3B (`Qwen/Qwen3-30B-A3B`), lokaler Pfad via `HIME_MODELS_DIR/qwen3-30b`, Unsloth NF4
- **Stage 4 Reader**: Konfiguriert via `settings.stage4_reader_model_id` (config-basiert)
- **Stage 4 Aggregator**: Konfiguriert via `settings.stage4_aggregator_model_id` (LFM2-24B-A2B, config-basiert)
- **Fazit**: Mischung aus Config-basiert (Stage 4) und teils hardcoded HF-IDs mit lokalen Fallbacks (Stage 2, 3)

### VRAM-Management
- **Vorhanden und gruendlich**:
  - Stage 1: `_vram_cleanup()` mit `torch.cuda.empty_cache()` + `gc.collect()` zwischen sequentiellen Adaptern. OOM-Erkennung mit automatischem Fallback von parallel zu sequentiell.
  - Stage 2: `model.cpu()` + `del model` + `gc.collect()` + `torch.cuda.empty_cache()` im `finally`-Block
  - Stage 3: Identisch zu Stage 2 — explizites `unload_stage3()` als Safety-Net
  - Stage 4 Reader: `model.cpu()` + `del model` + `torch.cuda.empty_cache()` in `unload()`, wird zwischen Retries und nach Abschluss aufgerufen
  - Stage 4 Aggregator: Identisch — `unload()` nach Abschluss

### Retry-Loop
- **Vorhanden**: `MAX_STAGE4_RETRIES = 3`
- Stage 4 Reader liefert Annotationen von 15 Personas, Stage 4 Aggregator aggregiert zu Verdict ("okay" / "retry")
- Bei "retry": Stage 3 wird erneut mit `retry_instruction` aufgerufen (konkretes Feedback aus Aggregator)
- Reader wird zwischen Retries unloaded und neu geladen

### WebSocket-Integration
- `run_pipeline_v2()` erhaelt eine `asyncio.Queue` (`ws_queue`)
- Events werden fuer jeden Pipeline-Schritt gesendet: `preprocess_complete`, `segment_start`, `stage1_complete`, `stage2_complete`, `stage3_complete`, `stage4_verdict`, `segment_complete`, `pipeline_complete` / `pipeline_error`
- `None`-Sentinel signalisiert Ende
- Router (`pipeline.py`) verwaltet `_active_v2` Dict um Doppel-Starts zu verhindern, 300s Timeout pro Event

### Stage-Implementierungen

| Stage | Datei(en) | Status | Details |
|---|---|---|---|
| Preprocessing | `preprocessor.py` | Implementiert | MeCab-Tokenisierung, Glossar + RAG Kontext-Injektion |
| Stage 1 | `stage1/runner.py` + 5 Adapter | Implementiert | `adapter_qwen32b.py` (Ollama API), `adapter_translategemma.py` (Unsloth lokal), `adapter_qwen35_9b.py` (Unsloth lokal), `adapter_gemma4.py` (Unsloth lokal), `adapter_jmdict.py` (CPU MeCab+JMDict). Parallel mit OOM-Fallback zu sequentiell. |
| Stage 2 | `stage2_merger.py` | Implementiert | TranslateGemma-27B via `transformers.AutoModelForCausalLM` (bfloat16), explizites Load/Unload pro Aufruf |
| Stage 3 | `stage3_polish.py` | Implementiert | Qwen3-30B-A3B via Unsloth NF4 (Non-Thinking Mode), JP-Punctuation Konvertierung, `retry_instruction` Parameter fuer Stage-4-Feedback |
| Stage 4 Reader | `stage4_reader.py` | Implementiert | 15 Personas (Purist, Stilist, Charakter-Tracker, Yuri-Leser, etc.), Qwen3.5-2B NF4 via Unsloth, JSON-Ausgabe pro Persona+Satz |
| Stage 4 Aggregator | `stage4_aggregator.py` | Implementiert | LFM2-24B-A2B via Transformers int4 (BitsAndBytes NF4), synthetisiert 15 Persona-Feedbacks zu "okay"/"retry" Verdict |
| Postprocessor | `postprocessor.py` | Vorhanden | (Nicht in runner_v2 integriert — moeglicherweise Legacy) |

---

## Sicherheit

| Check | Status | Details |
|---|---|---|
| API-Key-Mechanismus | Kein Auth-Mechanismus | Kein Bearer/API-Key Dependency auf Endpoints. `X-API-Key` ist nur als erlaubter CORS-Header konfiguriert, wird aber nirgends validiert. `inference.py` nutzt `api_key="local"` nur als Platzhalter fuer die lokale OpenAI-kompatible API. **Begruendung**: Local-only App (127.0.0.1 Binding), kein externer Zugriff moeglich. |
| Path-Traversal-Schutz | Vorhanden | `epub.py`: Null-Byte-Pruefung, Env-Var-Syntax-Pruefung (`${...}`, `%...%`), `.epub`-Suffix-Check, `is_relative_to(watch_folder)` Pruefung, Symlink-Ablehnung. `epub_service.py`: `_validate_epub_path()` existiert als separate Validierungsfunktion. |
| Input-Sanitization | Vorhanden und umfassend | `sanitize.py`: Strip, Null-Byte-Ablehnung, Max 50.000 Zeichen, Env-Var-Syntax-Ablehnung, 11 Prompt-Injection-Patterns (ignore instructions, act as, system prompt, ChatML-Tags, Instruct-Tags). Wird in `texts.py`, `translations.py`, `compare.py`, `review.py`, `epub.py` (sanitize_text) aufgerufen. |
| Audit-Log | Vorhanden | `middleware/audit.py`: JSON-Lines Format, loggt ts, method, path, status, duration_ms, client. Append-only, wird nie extern gesendet. Pfad via `settings.audit_log_path`. |
| Rate-Limiting | Vorhanden | `middleware/rate_limit.py`: slowapi mit `get_remote_address` Key. Default-Limit aus Config. Endpoint-spezifische Limits: POST /texts 30/min, POST /translate 10/min, POST /import 5/min, POST /rescan 2/min, PATCH /books 10/min, POST /review 10/min, POST /preprocess 5/min. |

---

## Import-Test

**Ergebnis: FEHLER**

```
ModuleNotFoundError: No module named 'openai'
```

**Traceback-Kette**:
1. `app.main` -> `app.routers.pipeline`
2. -> `app.pipeline.__init__` -> `app.pipeline.runner_v2`
3. -> `app.pipeline.stage1.__init__` -> `app.pipeline.stage1.runner`
4. -> `app.pipeline.stage1.adapter_qwen32b`
5. -> `app.inference` -> `from openai import AsyncOpenAI`

**Analyse**: Das `openai` Paket ist in der `hime` Conda-Umgebung nicht installiert. Es wird von `adapter_qwen32b.py` ueber `app.inference` importiert (OpenAI-kompatible API fuer lokale llama.cpp/vllm Server). Dies ist eine **fehlende Dependency** in der Umgebung, nicht im Code.

**Hinweis**: 0 Routen konnten aufgelistet werden, da der Import vor der App-Erstellung scheitert.

---

## Probleme

1. ~~**Import-Fehler: `openai` Modul fehlt**~~ — **BEHOBEN**: `openai` SDK (v2.31.0) wurde waehrend der Verifikation installiert. App-Import jetzt erfolgreich mit 66 Routes. Hinweis: Das `openai` SDK wird ausschliesslich als Client fuer lokale Inference-Server (llama.cpp, vllm, Ollama auf 127.0.0.1) genutzt — keine externen API-Aufrufe.

2. **Kein API-Key / Auth-Mechanismus** — Kein Endpoint ist durch Auth geschuetzt. Bei lokalem Betrieb (127.0.0.1 only) akzeptabel, aber der CORS-Header `X-API-Key` suggeriert eine geplante aber nicht implementierte Auth-Schicht.

3. **Version-Inkonsistenz** — `main.py` deklariert Version `"1.1.2"`, aber Dateinamen in `docs/superpowers/plans/` referenzieren `v1.2.0` und `v1.2.1`. Moeglicherweise wurde `bump_version.py` nicht ausgefuehrt.

4. **Pipeline v2 Modell-IDs teilweise hardcoded** — Stage 2 und 3 haben HuggingFace Model-IDs direkt im Code (`google/translategemma-27b-it`, `Qwen/Qwen3-30B-A3B`). Stage 4 nutzt dagegen `settings.*_model_id`. Eine einheitliche Config-basierte Loesung waere konsistenter.

5. **Postprocessor nicht integriert** — `postprocessor.py` existiert, wird aber von `runner_v2.py` nicht importiert oder verwendet. Moeglicherweise Legacy aus Pipeline v1.

6. **Stage 4 Aggregator wird nicht explizit geladen** — In `runner_v2.py` wird `reader.load(settings)` aufgerufen, aber `aggregator.load()` wird nie aufgerufen. Der Aggregator versucht direkt `_infer_one()` ohne vorheriges Laden des Modells, was zu einem `AttributeError` fuehren wuerde (`self._model` ist None).

7. **Einige Endpoints ohne Rate-Limiting** — `compare.py`, `models.py`, `lexicon.py`, `verify.py`, `glossary.py`, `flywheel.py`, `rag.py` haben keine endpoint-spezifischen Rate-Limits (nur den globalen Default-Limit).
