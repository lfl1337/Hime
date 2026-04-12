# Phase 8 — Integrations-Tests

## Backend Import-Chain

### Router-Module

| Modul | Status |
|---|---|
| app.routers.pipeline | OK |
| app.routers.translations | OK |
| app.routers.texts | OK |
| app.routers.training | OK |
| app.routers.epub | OK |
| app.routers.models | OK |
| app.routers.hardware | OK |
| app.routers.compare | OK |
| app.routers.review | OK |
| app.routers.lexicon | OK |
| app.routers.verify | OK |
| app.routers.glossary | OK |
| app.routers.flywheel | OK |
| app.routers.rag | OK |

**Ergebnis:** Alle 14 Router-Module importieren fehlerfrei.

### Service-Module

| Modul | Status |
|---|---|
| app.services.epub_service | OK |
| app.services.epub_export_service | FEHLER: Zirkulaerer Import mit app.pipeline.runner_v2 |
| app.services.flywheel_service | OK |
| app.services.glossary_service | OK |
| app.services.hardware_monitor | OK |
| app.services.lexicon_service | OK |
| app.services.model_manager | OK |
| app.services.reader_panel | OK |
| app.services.training_monitor | OK |
| app.services.training_runner | OK |
| app.services.verification_service | OK |

**Ergebnis:** 10 von 11 Services importieren fehlerfrei. `epub_export_service` hat einen zirkulaeren Import:
- `epub_export_service` importiert `..pipeline.postprocessor`
- `pipeline/__init__.py` importiert `runner_v2`
- `runner_v2` importiert `epub_export_service` -> Zirkel

**Hinweis:** Der direkte Import von `epub_export_service` schlaegt fehl, aber der Import ueber Router (z.B. `routers.pipeline`) funktioniert, da Python den Zirkel bei normalem App-Start aufloest. Der Fehler tritt nur bei isoliertem Direktimport des Service-Moduls auf.

## Ollama-Verfuegbarkeit

- **Daemon:** Laeuft (Port 11434 erreichbar)
- **API:** Erreichbar via `http://127.0.0.1:11434/api/tags`
- **Aktuell geladen:** Kein Modell aktiv im Speicher (`ollama ps` leer)
- **Registrierte Modelle:**

| Modell | Groesse | Familie | Quantisierung |
|---|---|---|---|
| qwen3.5:4b | 3.4 GB | qwen35 | Q4_K_M |
| qwen3:4b | 2.5 GB | qwen3 | Q4_K_M |
| bge-m3:latest | 1.2 GB | bert | F16 |
| hibiki-qwen:latest | 9.0 GB | qwen2 | Q4_K_M |
| qwen2.5:7b | 4.7 GB | qwen2 | Q4_K_M |
| nomic-embed-text:latest | 274 MB | nomic-bert | F16 |
| kizashi-deepseek:latest | 9.0 GB | qwen2 | Q4_K_M |
| kizashi-qwen:latest | 9.0 GB | qwen2 | Q4_K_M |
| deepseek-r1:14b | 9.0 GB | qwen2 | Q4_K_M |
| qwen2.5:14b | 9.0 GB | qwen2 | Q4_K_M |
| deepseek-r1:32b | 19 GB | qwen2 | Q4_K_M |
| minicpm-v:latest | 5.5 GB | qwen2 | Q4_0 |

**Gesamt:** 12 Modelle registriert, ca. 77 GB auf Disk.

## DB-Read-Tests

Datenbank: `N:\Projekte\NiN\Hime\hime.db`

| Tabelle | Zeilen | Status |
|---|---|---|
| books | 21 | OK |
| chapters | 430 | OK |
| paragraphs | 80.313 | OK |
| translations | 0 | OK (leer) |
| source_texts | 0 | OK (leer) |
| settings | 2 | OK |
| glossaries | 6 | OK |
| glossary_terms | 5 | OK |
| hardware_stats | 0 | OK (leer) |

**Ergebnis:** Alle 9 Tabellen lesbar. 21 Buecher mit 430 Kapiteln und 80.313 Absaetzen vorhanden. `translations`, `source_texts` und `hardware_stats` sind leer — kein Datenverlust, da noch keine Uebersetzungen durchgefuehrt wurden.

## MeCab Sanity-Check

```
MeCab OK: 1 tokens
```

**Ergebnis:** fugashi/MeCab funktioniert korrekt. Japanische Tokenisierung verfuegbar.

## Pipeline Dry-Run Inspektion

- **Dry-Run Flag:** Nicht vorhanden. Weder `runner.py` noch `runner_v2.py` enthalten `dry_run`, `DRY_RUN` oder `simulate` Parameter.
- **Architektur:** `runner_v2.py` ist funktionsbasiert (keine Klasse `PipelineRunnerV2`). Hauptfunktion ist `run_pipeline_v2()`.
- **Konstruktor/Signatur:**
  ```python
  async def run_pipeline_v2(
      book_id: int,
      ws_queue: asyncio.Queue,
      session: AsyncSession,
  ) -> None
  ```
- **Kann ohne Modell-Laden instanziiert werden:** Nein — die Funktion startet sofort mit `_preprocessor.preprocess_book()` und durchlaeuft alle 4 Stages. Es gibt keinen Mechanismus zum trockenen Durchlauf ohne aktive Modelle.

## Config-Pfad-Validierung

| Pfad-Variable | Wert | Existiert |
|---|---|---|
| DATA_DIR | `N:\Projekte\NiN\Hime\data` | OK |
| EMBEDDINGS_DIR | `N:\Projekte\NiN\Hime\modelle\embeddings` | FEHLT |
| EPUB_WATCH_DIR | `N:\Projekte\NiN\Hime\data\epubs` | OK |
| LOGS_DIR | `N:\Projekte\NiN\Hime\app\backend\logs` | OK |
| MODELS_DIR | `N:\Projekte\NiN\Hime\modelle` | OK |
| OBSIDIAN_VAULT_DIR | `N:\Projekte\NiN\Hime\obsidian-vault` | OK |
| PROJECT_ROOT | `N:\Projekte\NiN\Hime` | OK |
| RAG_DIR | `N:\Projekte\NiN\Hime\data\rag` | FEHLT |
| SCRIPTS_DIR | `N:\Projekte\NiN\Hime\scripts` | OK |
| TRAINING_DATA_DIR | `N:\Projekte\NiN\Hime\data\training` | OK |
| TRAINING_LOG_DIR | `N:\Projekte\NiN\Hime\app\backend\logs\training` | OK |

**Ergebnis:** 9 von 11 Pfaden existieren. 2 fehlende Verzeichnisse:
- `EMBEDDINGS_DIR` — wird fuer Embedding-Modelle benoetigt (bge-m3 liegt in Ollama, nicht als Datei)
- `RAG_DIR` — wird fuer RAG-Datenbanken benoetigt, Verzeichnis wurde noch nicht angelegt

## Zusammenfassung

- **Erfolgreiche Checks:** 11
  - 14/14 Router importieren fehlerfrei
  - 10/11 Services importieren fehlerfrei
  - Ollama-Daemon laeuft mit 12 Modellen
  - Alle 9 DB-Tabellen lesbar
  - MeCab/fugashi funktioniert
  - 9/11 konfigurierte Pfade existieren

- **Fehlgeschlagene / auffaellige Checks:** 3
  1. **Zirkulaerer Import** in `epub_export_service` <-> `pipeline.runner_v2` (funktioniert bei normalem App-Start, schlaegt bei isoliertem Import fehl)
  2. **Fehlende Verzeichnisse:** `modelle/embeddings` und `data/rag` existieren nicht auf Disk
  3. **Kein Dry-Run-Modus** in Pipeline v2 — Tests koennen Pipeline nicht ohne aktive Modelle ausfuehren
