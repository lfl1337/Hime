# Hime Code Review Report

**Reviewer:** Senior Developer (AI-Slop-free audit)
**Branch:** `fix/security-remediation-v2.1`
**Date:** 2026-04-16
**Scope:** Full codebase — backend, frontend, scripts, CI/CD, tests

---

## Blocker

### B01 — SQL Injection in database.py Settings Seed

**Datei:** `app/backend/app/database.py:207-211`
**Problem:** Der EPUB-Pfad wird per f-String direkt in ein SQL-Statement interpoliert. Wenn `HIME_EPUB_WATCH_DIR` ein Apostroph enthaelt (z.B. `C:\Users\O'Brien\data\epubs`), bricht das Statement oder ermoeglicht Injection.
**Beweis:**
```python
_epub_default = str(EPUB_WATCH_DIR).replace("\\", "/")
await conn.execute(text(
    "INSERT OR IGNORE INTO settings (key, value) VALUES "
    f"('epub_watch_folder', '{_epub_default}'), "
    "('auto_scan_interval', '60')"
))
```
**Fix:** Parameterized Query verwenden:
```python
await conn.execute(
    text(
        "INSERT OR IGNORE INTO settings (key, value) "
        "VALUES (:k1, :v1), (:k2, :v2)"
    ),
    {"k1": "epub_watch_folder", "v1": _epub_default,
     "k2": "auto_scan_interval", "v2": "60"},
)
```
**Severity:** Auf einem `security-remediation` Branch ist das inakzeptabel.

---

### B02 — Stale AppData-Pfad in run.py (Datenverlust-Pfad)

**Datei:** `app/backend/run.py:38-39`
**Problem:** Der frozen-exe Fallback hardcodet `"dev.hime.app"`, aber `lib.rs:80-101` migriert dieses Verzeichnis nach `dev.Ninym.hime`. Wenn jemand die frozen Backend-exe ohne `--data-dir` startet, landen Daten im falschen Verzeichnis. Die DB wird nicht gefunden, neue Daten gehen in ein verwaistes Directory.
**Beweis:**
```python
_DATA_DIR = _appdata / "dev.hime.app"
```
Aber in `lib.rs`:
```rust
let from_hime = std::path::PathBuf::from(&appdata).join("dev.hime.app");
// migrates TO dev.Ninym.hime
```
**Fix:** `run.py:39` auf `"dev.Ninym.hime"` aendern (muss mit dem Tauri-Identifier uebereinstimmen).

---

### B03 — .env-Writer ohne Env-Var-Syntax-Validation (Config Injection)

**Datei:** `app/backend/app/routers/training.py:246-256`
**Problem:** `update_training_config` schreibt `body.value` direkt in `.env` ohne Pruefung auf `${...}` oder `%VAR%`. Die `sanitize_text()`-Funktion hat diese Checks, wird hier aber nicht aufgerufen. Ein Wert wie `foo${HOME}bar` wird wortwörtlich in `.env` geschrieben und kann von downstream-Consumern expandiert werden.
**Beweis:**
```python
# Line 251-256: Schreibt body.value direkt in .env
lines[i] = f"{key_upper}={body.value}"
# ... oder:
lines.append(f"{key_upper}={body.value}")
```
Vergleich mit sanitize.py, das `_ENV_VAR_PATTERNS` prueft, aber hier nie aufgerufen wird.
**Fix:** `body.value` vor dem Schreiben durch eine Validierung jagen, die `${`, `%VAR%` und Newlines ablehnt. Die Newline-Pruefung existiert zwar im Pydantic-Validator `_no_dangerous_chars`, aber die env-var-Syntax-Pruefung fehlt:
```python
for pattern in _ENV_VAR_PATTERNS:
    if pattern.search(body.value):
        raise HTTPException(status_code=422, detail="Value contains env var syntax")
```

---

### B04 — Version Mismatch: main.py sagt 2.0.0, Git sagt 2.1.0

**Datei:** `app/backend/app/main.py:99` und `main.py:156`
**Problem:** `FastAPI(version="2.0.0")` und der `/health`-Endpoint geben `"2.0.0"` zurueck, aber der Git-Log zeigt `chore: bump version to 2.1.0`. Eine der beiden Stellen luegt.
**Fix:** VERSION-File als Single Source of Truth lesen, oder zumindest die Strings auf `2.1.0` aktualisieren.

---

### B05 — Glossary Router: Fehlende sanitize_text() Calls

**Datei:** `app/backend/app/routers/glossary.py:42-53, 84-94`
**Problem:** `source_term`, `target_term`, `notes` aus User-Input passieren unsanitized in die DB. Das `CLAUDE.md` des Projekts sagt woertlich: *"All new endpoints must call sanitize_text() on user-supplied strings."* Gleiches gilt fuer `auto_extract`'s `source_text` und `translated_text`.
**Fix:** `sanitize_text()` auf alle User-Inputs aufrufen:
```python
from ..utils.sanitize import sanitize_text

# In add_term:
body.source_term = sanitize_text(body.source_term, "source_term")
body.target_term = sanitize_text(body.target_term, "target_term")
if body.notes:
    body.notes = sanitize_text(body.notes, "notes")
```

---

## Verbesserung

### V01 — VRAM-Leak in runner_v2.py Stage4-Retry-Loop

**Datei:** `app/backend/app/pipeline/runner_v2.py:312-316`
**Problem:** Wenn `reader.load()` erfolgreich ist, aber `aggregator.load()` oder `.aggregate_segment()` eine Exception wirft, wird `reader.unload()` nie aufgerufen. Das Modell bleibt im GPU-Speicher.
**Fix:** try/finally um den Load-Review-Unload-Block:
```python
reader.load(settings)
try:
    annotations = await reader.review(...)
finally:
    reader.unload()

aggregator.load(settings)
try:
    segment_verdict = await aggregator.aggregate_segment(annotations)
finally:
    aggregator.unload()
```

---

### V02 — streaming.py: _active_pipelines Memory-Leak bei Disconnect

**Datei:** `app/backend/app/websocket/streaming.py:209`
**Problem:** Bei `WebSocketDisconnect` bleibt der Task-Eintrag in `_active_pipelines` dict fuer immer. Bei vielen Disconnect/Reconnect-Zyklen waechst das Dict unbegrenzt.
**Fix:** Im `except WebSocketDisconnect` Block:
```python
except WebSocketDisconnect:
    # Task laeuft weiter, aber cleanup nach Abschluss planen
    pass
```
Besser: einen done-callback auf den Task setzen, der den Eintrag entfernt:
```python
task.add_done_callback(lambda _: _active_pipelines.pop(job_id, None))
```

---

### V03 — Verify Router: Kein Rate Limiting trotz Model Inference

**Datei:** `app/backend/app/routers/verify.py`
**Problem:** Der `POST /verify` Endpoint fuehrt Model-Inference aus (Verification Service), hat aber kein `@limiter.limit()`. Alle anderen Mutations/Expensive-Endpoints haben eins.
**Fix:** `@limiter.limit("10/minute")` hinzufuegen und den `request: Request` Parameter ergaenzen.

---

### V04 — Duplizierte .env-Aufloesung in zwei Config-Modulen

**Datei:** `app/backend/app/config/__init__.py:15-20` und `app/backend/app/config/pipeline_v2.py:18-23`
**Problem:** Identischer Code fuer `_HIME_DATA_DIR` / `_ENV_FILE`-Resolution. Wenn einer geaendert wird, divergiert der andere still.
**Fix:** In ein gemeinsames Modul extrahieren, z.B. `config/_env.py`:
```python
# config/_env.py
import os
from pathlib import Path
_HIME_DATA_DIR = os.environ.get("HIME_DATA_DIR")
ENV_FILE = (
    Path(_HIME_DATA_DIR) / ".env" if _HIME_DATA_DIR
    else Path(__file__).parent.parent.parent / ".env"
)
```

---

### V05 — model_manager.py referenziert tote v1 Pipeline-Modelle

**Datei:** `app/backend/app/services/model_manager.py:18-25`
**Problem:** `PIPELINE_MODELS` listet noch Gemma 3 12B, DeepSeek R1 32B, etc. — die v1-Pipeline. Die v2-Pipeline nutzt TranslateGemma-12B, Qwen3.5-9B, Gemma4-E4B lokal via Unsloth. Dieses Modul ist entweder Dead Code oder muss aktualisiert werden.
**Fix:** Entweder die Liste auf v2-Modelle aktualisieren (wenn der Health-Check noch gebraucht wird) oder das Modul/die Route als deprecated markieren.

---

### V06 — database.py: Doppeltes PRAGMA table_info(paragraphs)

**Datei:** `app/backend/app/database.py:96-107`
**Problem:** `PRAGMA table_info(paragraphs)` wird zweimal ausgefuehrt — einmal fuer `_V121_PARAGRAPH_COLS` (Zeile 96-100), einmal fuer `_V200_PARAGRAPH_RETRY_COLS` (Zeile 103-107). Das ist ein unnuetzer Round-Trip.
**Fix:** Einmal lesen, einmal verwenden:
```python
rows_par = (await conn.execute(text("PRAGMA table_info(paragraphs)"))).fetchall()
existing_par = {r[1] for r in rows_par}
for col, dtype in _V121_PARAGRAPH_COLS + _V200_PARAGRAPH_RETRY_COLS:
    if col not in existing_par:
        await conn.execute(text(f"ALTER TABLE paragraphs ADD COLUMN {col} {dtype}"))
```

---

### V07 — TeeOutput-Klasse identisch in zwei Scripts dupliziert

**Datei:** `scripts/train_generic.py:101-127` und `scripts/train_hime.py:612-637`
**Problem:** Exakte Kopie. Wenn ein Bug in einer Kopie gefixed wird, bleibt er in der anderen.
**Fix:** In ein shared-Modul extrahieren, z.B. `scripts/utils/tee.py`.

---

### V08 — data_registry.py: Potentielle Path Traversal via entry_id

**Datei:** `app/backend/app/routers/data_registry.py:63`
**Problem:** `src = PROJECT_ROOT / entry["path"]` — der `path`-Wert kommt aus `registry.jsonl`, das vom CLI verwaltet wird. Aber die Registry-Datei liegt im `data/`-Verzeichnis und koennte theoretisch manipuliert werden. `entry["path"]` wird nicht gegen Path-Traversal validiert.
**Fix:** `validate_within_directory(src, PROJECT_ROOT)` aufrufen bevor die Datei gelesen wird.

---

### V09 — epub_service.py: save_translation zaehlt alle Paragraphs statt COUNT

**Datei:** `app/backend/app/services/epub_service.py:402-406`
**Problem:** Zum Zaehlen uebersetzter Paragraphen wird `len(result.scalars().all())` genutzt, was alle Rows in den Speicher laedt. Bei einem Buch mit tausenden Paragraphen ist das ein unnoetiger Performance-Hit.
**Fix:** `select(func.count()).where(...)` verwenden:
```python
from sqlalchemy import func
count_result = await session.execute(
    select(func.count(Paragraph.id)).where(
        Paragraph.chapter_id == chapter.id,
        Paragraph.is_translated == True
    )
)
chapter.translated_paragraphs = count_result.scalar_one()
```

---

### V10 — Glossary CRUD: book_id-Parameter in URL wird ignoriert

**Datei:** `app/backend/app/routers/glossary.py:55-76`
**Problem:** `update_term` und `delete_term` nehmen `book_id` als URL-Parameter, nutzen ihn aber nicht. Jeder User koennte Term-IDs aus einem anderen Buch aendern/loeschen, weil die Zugehoerigkeit nie geprueft wird (Broken Object Level Authorization).
**Fix:** In `update_term` und `delete_term` pruefen, dass der Term tatsaechlich zum Glossary des angegebenen `book_id` gehoert.

---

## Lob

### L01 — Windows Job Object Pattern (Backend + Rust)

**Dateien:** `app/backend/app/services/training_runner.py:25-89` und `app/frontend/src-tauri/src/lib.rs:179-221`
Beide Seiten (Python und Rust) implementieren Windows Job Objects mit `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Das stellt sicher, dass Training-Subprozesse bei App-Crash getoetet werden. Saubere Loesung fuer ein reales Problem auf Windows.

---

### L02 — validate_safe_name() und validate_within_directory()

**Datei:** `app/backend/app/core/paths.py:57-84`
Korrekte und vollstaendige Implementierung: Null-Bytes, dots-only, path separators, resolve()-basierte Directory-Containment-Pruefung. Wird konsistent in training_runner, training_monitor, und ueberall wo User-supplied Names in Pfade fliessen genutzt.

---

### L03 — Hardcoded 127.0.0.1 Binding mit explizitem Kommentar

**Datei:** `app/backend/run.py:60, 96`
```python
_HOST = "127.0.0.1"
# ...
host=_HOST,  # Local-only — do not change to 0.0.0.0
```
Korrekt. Dazu der Docstring: *"do not make it configurable via an environment variable, as that would undermine the local-only guarantee."* Genau richtig.

---

### L04 — CORS auf exakt zwei Origins beschraenkt

**Datei:** `app/backend/app/main.py:124-132`
`http://localhost:1420` (Vite dev) und `https://tauri.localhost` (packaged app). Kein Wildcard `*`. Genau das Richtige fuer eine local-first App.

---

### L05 — Test-Isolation in conftest.py

**Datei:** `app/backend/tests/conftest.py`
HIME_DATA_DIR auf tempdir vor jedem Config-Import, SAVEPOINT-basierte Session-Isolation pro Test, Assertions dass die DB-URL im tempdir liegt. Das ist die richtige Art, Tests zu isolieren.

---

### L06 — Prompt-Injection-Defense in sanitize.py

**Datei:** `app/backend/app/utils/sanitize.py:14-28`
Pre-compiled Regex-Patterns fuer `[INST]`, `<|im_start|>`, `### System:`, `<system>`, env-var-Syntax. Vollstaendig fuer die gaengigen Injection-Vektoren.

---

### L07 — sqlite-vec KNN Fix mit API-Doku-Referenz

**Datei:** `app/backend/app/rag/store.py:92-106`
Der Fix von `ORDER BY distance LIMIT ?` auf `AND k = ?` ist korrekt dokumentiert, mit Link zur API-Referenz. Das ist wie man Known-Bug-Fixes dokumentiert.

---

### L08 — Pydantic Settings extra="ignore"

**Datei:** `app/backend/app/config/__init__.py:114`
Loest das dokumentierte Startup-Crash-Problem wenn `.env` undeclared Keys enthaelt. Clean.

---

## Executive Summary

| Severity | Count |
|----------|-------|
| Blocker  | 5     |
| Verbesserung | 10 |
| Lob      | 8     |

**Gesamtbewertung:** Die Architektur ist solide — Pfad-Resolution, Process-Management, Test-Isolation, und die Grundstruktur sind gut durchdacht. Aber auf einem Branch namens `fix/security-remediation-v2.1` duerfen keine SQL-Injections, fehlende Input-Sanitization, und Config-Injection-Vektoren existieren. Die 5 Blocker muessen vor dem Merge gefixt werden. V01 (VRAM-Leak) und V10 (Broken Authorization im Glossary) sollten zeitnah folgen.
