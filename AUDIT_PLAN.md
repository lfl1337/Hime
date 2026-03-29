# Hime — Audit Fix Implementation Plan

> **Basis:** AUDIT_REPORT.md (2026-03-29) — 13 aktionsfähige Findings (AUDIT-001 bis AUDIT-013)
> **Modus:** Implementierung. Code wird geändert. Jede Phase ist in einem neuen Chat selbst-contained.
> **Strategie:** Critical → High → Medium → Low. Phasen 1–4 sind atomare Quick-Fix-Batches.

---

## Übersicht

| Phase | Findings | Effort | Beschreibung |
|-------|----------|--------|-------------|
| 1 | AUDIT-001 | 5 min | Build reparieren (Cargo.toml) |
| 2 | AUDIT-002, AUDIT-003 | 30 min | Security: Path Traversal + npm vulns |
| 3 | AUDIT-004, AUDIT-006, AUDIT-007 | 45 min | Medium Quick Fixes (3 Dateien) |
| 4 | AUDIT-005, AUDIT-008, AUDIT-012 | 30 min | DB Indexes + .env.example |
| 5 | AUDIT-010, AUDIT-011 | 30 min | API Type Safety (response_model) |
| 5b | AUDIT-022 | 1 min | README Versions-Badge |
| 6 | AUDIT-009 | 20 min | Dependency Patch Updates |
| 7 | AUDIT-013 | 60 min | React.lazy Code Splitting |
| 8 | Cargo Dependabot | 30 min | Rust-Vulnerabilities prüfen + fixen |

---

## Phase 0: Kontext (für jeden Chat vorab lesen)

```
Projekt: C:\Projekte\Hime
Backend: app/backend/app/
Frontend: app/frontend/src/
```

Relevante Dateien pro Phase sind in der jeweiligen Phase angegeben.

---

## Phase 1: Build reparieren (AUDIT-001)

**Einzige Datei:** `app/frontend/src-tauri/Cargo.toml`

### Problem
`CreateJobObjectW` (verwendet in `src/lib.rs:87`) ist in `windows` crate v0.61.3
hinter dem `Win32_Security` Feature gegattet. Feature fehlt in Cargo.toml → Kompilierung schlägt fehl.

**Fehlermeldung:**
```
error[E0432]: unresolved import `windows::Win32::System::JobObjects::CreateJobObjectW`
note: the item is gated behind the `Win32_Security` feature
```

### Fix

Lies `app/frontend/src-tauri/Cargo.toml` Zeilen 19–24.

Ändere den `[target.'cfg(target_os = "windows")'.dependencies]` Block von:
```toml
windows = { version = "0.61", features = [
    "Win32_Foundation",
    "Win32_System_JobObjects",
    "Win32_System_Threading",
] }
```
zu:
```toml
windows = { version = "0.61", features = [
    "Win32_Foundation",
    "Win32_Security",
    "Win32_System_JobObjects",
    "Win32_System_Threading",
] }
```

### Verifikation
```bash
cd C:\Projekte\Hime\app\frontend
npm run tauri build 2>&1 | tail -5
# Alternativ nur Cargo-Check:
cd C:\Projekte\Hime\app\frontend\src-tauri
cargo check 2>&1 | grep -E "error|warning: unused"
```
Erwartetes Ergebnis: Kein `E0432` Fehler mehr.

### Anti-Pattern-Guards
- **Nicht** `Win32_Security_*` sub-features hinzufügen — nur `Win32_Security` genügt
- **Nicht** die `windows`-Crate-Version bumpen (bleibt `"0.61"`)

### Commit
```
fix(tauri): add Win32_Security feature to fix CreateJobObjectW compilation
```

---

## Phase 2: Security Fixes (AUDIT-002 + AUDIT-003)

**Dateien:** `app/backend/app/routers/training.py`, `app/frontend/` (npm)

### 2A: Path Traversal Fix (AUDIT-002)

**Problem:** `GET /available-checkpoints/{model_name}` validiert `model_name` nicht.
Alle anderen Endpoints nutzen `Query(pattern=_RUN_PATTERN)`, hier fehlt es.

Lies `app/backend/app/routers/training.py` Zeilen 150–153 und 36.

**Aktuelle Code-Stelle (Zeilen 150–153):**
```python
@router.get("/available-checkpoints/{model_name}")
async def api_available_checkpoints(model_name: str) -> dict:
    """List available checkpoint names for a model (for the resume dropdown)."""
    return {"checkpoints": get_available_checkpoints(model_name)}
```

**Fix:** Import `Path as FPath` von FastAPI und Pattern anwenden:
```python
# Import-Zeile ergänzen (am Anfang der Datei, wo APIRouter etc. importiert werden):
from fastapi import APIRouter, HTTPException, Path as FPath, Query, status

# Endpoint ersetzen:
@router.get("/available-checkpoints/{model_name}")
async def api_available_checkpoints(
    model_name: str = FPath(pattern=_RUN_PATTERN, max_length=128),
) -> dict:
    """List available checkpoint names for a model (for the resume dropdown)."""
    return {"checkpoints": get_available_checkpoints(model_name)}
```

**Verifikation:**
```bash
# Pattern existiert im Import:
grep "Path as FPath" app/backend/app/routers/training.py

# Pattern wird im Endpoint verwendet:
grep -A3 "available-checkpoints" app/backend/app/routers/training.py | grep "FPath"
```

### 2B: npm Vulnerabilities (AUDIT-003)

```bash
cd C:\Projekte\Hime\app\frontend
npm audit fix
npm audit  # → sollte 0 vulnerabilities melden
```

Falls `npm audit fix` nicht alle behebt:
```bash
npm install picomatch@latest
npm audit  # nochmal prüfen
```

**Verifikation:**
```bash
npm audit 2>&1 | grep "found 0 vulnerabilities"
```

### Commit
```
fix(security): validate model_name path param + fix npm vulnerabilities (picomatch, brace-expansion)
```

---

## Phase 3: Medium Quick Fixes (AUDIT-004, AUDIT-006, AUDIT-007)

**Dateien:**
- `app/frontend/src/api/training.ts` (AUDIT-004)
- `app/backend/app/services/training_runner.py` (AUDIT-006, AUDIT-007)

### 3A: stop-config fetch → apiFetch (AUDIT-004)

Lies `app/frontend/src/api/training.ts` vollständig, insbesondere:
- Zeilen 231–245 (`getStopConfig` Funktion)
- Zeilen 247–265 (`updateStopConfig` Funktion)
- Den Import-Bereich oben (um zu sehen wie `apiFetch` importiert wird)

**Problem:** Direkter `fetch()` statt `apiFetch()` — bricht bei Port-Fallback (8001–8010).

Ändere beide Funktionen so, dass sie `apiFetch('/api/v1/training/stop-config')` nutzen,
analog zu den anderen Funktionen in derselben Datei. Orientiere dich an bestehenden
`apiFetch`-Aufrufen in der Datei als Vorlage (z.B. `getTrainingStatus`, `startTraining`).

**Verifikation:**
```bash
grep -n "fetch(" app/frontend/src/api/training.ts
# Darf nur noch in apiFetch-Definition selbst vorkommen (client.ts), nicht in training.ts
```

### 3B: training_config.json Werte validieren (AUDIT-006)

Lies `app/backend/app/services/training_runner.py` Zeilen 136–154.

**Problem:** `str(_cfg["target_loss"])` — beliebige JSON-Typen werden unkontrolliert in CLI-Args umgewandelt.

Ersetze den Block (Zeilen 143–152) durch explizite `float()`/`int()` Casts mit Validierung:

```python
# Vorher:
if _cfg.get("target_loss") is not None:
    cmd += ["--target-loss", str(_cfg["target_loss"])]
if _cfg.get("patience") is not None:
    cmd += ["--patience", str(_cfg["patience"])]
if _cfg.get("min_delta") is not None:
    cmd += ["--min-delta", str(_cfg["min_delta"])]
if _cfg.get("min_steps"):
    cmd += ["--min-steps", str(_cfg["min_steps"])]
if _cfg.get("max_epochs") is not None and _cfg["max_epochs"] != 3:
    cmd += ["--max-epochs", str(_cfg["max_epochs"])]

# Nachher — mit expliziten Float/Int-Casts:
if _cfg.get("target_loss") is not None:
    val = float(_cfg["target_loss"])
    if val > 0:
        cmd += ["--target-loss", str(val)]
if _cfg.get("patience") is not None:
    val = int(_cfg["patience"])
    if val > 0:
        cmd += ["--patience", str(val)]
if _cfg.get("min_delta") is not None:
    cmd += ["--min-delta", str(float(_cfg["min_delta"]))]
if _cfg.get("min_steps"):
    cmd += ["--min-steps", str(int(_cfg["min_steps"]))]
if _cfg.get("max_epochs") is not None and _cfg["max_epochs"] != 3:
    val = int(_cfg["max_epochs"])
    if val > 0:
        cmd += ["--max-epochs", str(val)]
```

### 3C: File Handle Context Manager (AUDIT-007)

Lies `app/backend/app/services/training_runner.py` Zeilen 157–164.

**Problem:** `open()` ohne `with`-Statement — Handle leckt wenn `Popen` wirft.

```python
# Vorher:
_stderr_fh = open(log, "a", encoding="utf-8")
proc = subprocess.Popen(
    cmd,
    creationflags=0,
    stdout=subprocess.DEVNULL,
    stderr=_stderr_fh,  # Capture C-level crashes (CUDA, OOM, import errors) to log
)
_stderr_fh.close()  # Safe: child process has inherited its own copy of the fd

# Nachher:
with open(log, "a", encoding="utf-8") as _stderr_fh:
    proc = subprocess.Popen(
        cmd,
        creationflags=0,
        stdout=subprocess.DEVNULL,
        stderr=_stderr_fh,  # Capture C-level crashes (CUDA, OOM, import errors) to log
    )
# Parent-Handle geschlossen; Child-Kopie des FD bleibt offen
```

**Verifikation:**
```bash
grep -n "open(log" app/backend/app/services/training_runner.py
# Muss "with open(log" zeigen
grep -n "_stderr_fh.close()" app/backend/app/services/training_runner.py
# Darf nicht mehr existieren
```

### Commit
```
fix(quality): use apiFetch for stop-config, validate training config types, fix file handle leak
```

---

## Phase 4: DB Indexes + .env.example (AUDIT-005, AUDIT-008, AUDIT-012)

**Dateien:**
- `app/backend/app/database.py` (AUDIT-005)
- `app/backend/app/main.py` (AUDIT-008)
- `.env.example` anlegen (AUDIT-012)

### 4A: SQLite Indexes (AUDIT-005)

Lies `app/backend/app/database.py` vollständig.

**Problem:** `hardware_stats` und `translations` haben keine Indexes.
Füge nach der `hardware_stats`-Tabellen-Erstellung (nach Zeile 76) folgende Indexes ein:

```python
# Nach dem hardware_stats CREATE TABLE, vor dem DELETE-Prune:
await conn.execute(text(
    "CREATE INDEX IF NOT EXISTS idx_hw_timestamp ON hardware_stats(timestamp)"
))
await conn.execute(text(
    "CREATE INDEX IF NOT EXISTS idx_translations_created "
    "ON translations(created_at)"
))
```

**Verifikation:**
```bash
grep "CREATE INDEX" app/backend/app/database.py
# Muss 2 Einträge zeigen
```

### 4B: DEFAULT_WATCH_FOLDER als Setting (AUDIT-008)

Lies `app/backend/app/main.py` Zeile 27 und `app/backend/app/config.py`.

**Problem:** `DEFAULT_WATCH_FOLDER = "C:/Projekte/Hime/data/epubs/"` ist hardcoded in main.py.

Füge in `config.py` zur `Settings`-Klasse hinzu:
```python
epub_watch_folder_default: str = "C:/Projekte/Hime/data/epubs/"
```

Ersetze in `main.py` Zeile 27 und alle Verwendungen:
```python
# Vorher:
DEFAULT_WATCH_FOLDER = "C:/Projekte/Hime/data/epubs/"
# ... verwendet als:
folder = await get_setting("epub_watch_folder", session) or DEFAULT_WATCH_FOLDER

# Nachher: Konstante entfernen, direkt settings verwenden:
folder = await get_setting("epub_watch_folder", session) or settings.epub_watch_folder_default
```

### 4C: .env.example anlegen (AUDIT-012)

Lies `app/backend/app/config.py` vollständig (alle Settings-Felder).

Lege `app/backend/.env.example` an mit allen überschreibbaren Variablen:
```env
# Hime Backend Configuration
# Kopiere diese Datei nach .env und passe die Werte an.

PORT=8000
RATE_LIMIT_PER_MINUTE=60

# Inference endpoints
INFERENCE_URL=http://127.0.0.1:8080/v1
INFERENCE_MODEL=qwen2.5-14b-instruct

# Training paths (Windows-Beispiele — an eigene Installation anpassen)
MODELS_BASE_PATH=C:\path\to\modelle
LORA_PATH=C:\path\to\modelle\lora\Qwen2.5-32B-Instruct
TRAINING_LOG_PATH=C:\path\to\logs\training
SCRIPTS_PATH=C:\path\to\scripts

# EPUB
EPUB_WATCH_FOLDER_DEFAULT=C:\path\to\data\epubs

# Pipeline endpoints (optional — nur wenn mehrere Modelle gleichzeitig laufen)
HIME_GEMMA_URL=http://127.0.0.1:8001/v1
HIME_DEEPSEEK_URL=http://127.0.0.1:8002/v1
HIME_QWEN32B_URL=http://127.0.0.1:8003/v1
HIME_QWEN72B_URL=http://127.0.0.1:8004/v1
HIME_QWEN14B_URL=http://127.0.0.1:8005/v1
```

**Verifikation:**
```bash
ls C:\Projekte\Hime\app\backend\.env.example
# Muss existieren
grep "MODELS_BASE_PATH" C:\Projekte\Hime\app\backend\.env.example
```

### Commit
```
fix(config): add SQLite indexes, move DEFAULT_WATCH_FOLDER to settings, add .env.example
```

---

## Phase 5: API Type Safety (AUDIT-010, AUDIT-011)

**Dateien:**
- `app/backend/app/routers/training.py` (AUDIT-010)
- `app/backend/app/main.py` (AUDIT-011)

### 5A: response_model für dict-Endpoints (AUDIT-010)

Lies `app/backend/app/routers/training.py` vollständig.

Folgende Endpoints haben keinen `response_model=`. Für jeden: minimales Pydantic-Model
oder `dict[str, Any]` Annotation hinzufügen.

Empfohlene Lösung — neue Pydantic-Models am Anfang der Datei:

```python
from typing import Any

class LogResponse(BaseModel):
    lines: list[str]

class CheckpointsResponse(BaseModel):
    checkpoints: list[str]

class StopResponse(BaseModel):
    stopped: bool
    graceful: bool
    model_name: str

class CondaEnvsResponse(BaseModel):
    envs: list[str]
```

Dann die Endpoint-Dekoratoren aktualisieren:
- `GET /log` → `response_model=LogResponse`
- `GET /available-checkpoints/{model_name}` → `response_model=CheckpointsResponse`
- `POST /stop` → `response_model=StopResponse`
- `GET /conda-envs` → `response_model=CondaEnvsResponse`
- `GET /backend-log` → `response_model=LogResponse`
- `GET /config` und `POST /config` → `response_model=dict[str, str]`

**Verifikation:**
```bash
grep -c "response_model" app/backend/app/routers/training.py
# Vorher: 9, Nachher: 15
```

### 5B: Return Type für _log_requests (AUDIT-011)

Lies `app/backend/app/main.py` Zeilen 97–106.

```python
# Vorher:
from fastapi import FastAPI, Request

async def _log_requests(request: Request, call_next):

# Nachher:
from fastapi import FastAPI, Request
from fastapi.responses import Response

async def _log_requests(request: Request, call_next) -> Response:
```

**Verifikation:**
```bash
grep "_log_requests" app/backend/app/main.py | grep "-> Response"
```

### Commit
```
fix(types): add response_model to dict endpoints, add return type to _log_requests middleware
```

---

## Phase 6: Dependency Patch Updates (AUDIT-009)

**Verzeichnis:** `app/frontend/`

### Sofort (Patch/Minor, safe)

```bash
cd C:\Projekte\Hime\app\frontend
npm install recharts@latest          # 3.8.0 → 3.8.1
npm install typescript-eslint@latest # 8.57.1 → 8.57.2
npm install vite@latest              # 8.0.1 → 8.0.3
npm audit                            # Muss 0 vulnerabilities zeigen
```

**Verifikation:**
```bash
npm outdated 2>&1 | grep -E "recharts|typescript-eslint|vite"
# Alle sollten "Current == Latest" oder nicht mehr auftauchen
```

### Major Updates (eigene Branches — NICHT in diesem Chat)

Für jeden dieser Updates: eigenen Branch anlegen, Breaking Changes lesen, dann migrieren.

| Package | Von | Nach | Wichtigste Breaking Change |
|---------|-----|------|---------------------------|
| `react-router-dom` | 6 | 7 | `<Route>` Syntax, loader/action API |
| `tailwindcss` | 3 | 4 | Neues Config-System (kein tailwind.config.js) |
| `zustand` | 4 | 5 | `immer`-Middleware Signatur |
| `typescript` | 5 | 6 | Strengere noImplicitAny |
| `eslint` | 9 | 10 | ESM-only Config |

### Commit
```
chore(deps): update recharts, vite, typescript-eslint to latest patch versions
```

---

## Phase 7: React.lazy Code Splitting (AUDIT-013)

**Dateien:** `app/frontend/src/App.tsx` (oder Router-Datei)

Lies die App-Router-Datei (lese `app/frontend/src/App.tsx` oder suche wo `<Route>`-Definitionen stehen).

### Pattern

Ersetze statische Imports der Views durch `React.lazy`:

```tsx
// Vorher (in Router-Datei):
import TrainingMonitor from './views/TrainingMonitor'
import Settings from './views/Settings'
// ... weitere Views

// Nachher:
import { lazy, Suspense } from 'react'

const TrainingMonitor = lazy(() => import('./views/TrainingMonitor'))
const Settings = lazy(() => import('./views/Settings'))
// ... alle Views lazifizieren

// Router in Suspense wrappen:
<Suspense fallback={<div className="flex h-screen items-center justify-center">Laden…</div>}>
  {/* bestehende Routes */}
</Suspense>
```

**Verifikation:**
```bash
cd C:\Projekte\Hime\app\frontend
npm run build 2>&1 | grep -E "chunk|kB"
# Chunks sollten jetzt aufgeteilt sein (mehrere separate JS-Dateien)
grep "React.lazy\|lazy(" app/frontend/src/App.tsx
```

### Anti-Pattern-Guards
- **Nicht** alle Komponenten lazifizieren — nur Top-Level-Views (die im Router referenziert werden)
- **Nicht** `Suspense` wegvergessen — sonst Runtime-Error
- `TrainingMonitor` ist Priorität (39 useState, schwerste Komponente)

### Commit
```
perf(frontend): add React.lazy code splitting for all views
```

---

## Phase 5b: README Badge Fix (AUDIT-022)

**Datei:** `README.md:7`

Das Versions-Badge zeigt `0.10.0`, die App ist bei `1.1.0`.

```markdown
<!-- Vorher: -->
![version](https://img.shields.io/badge/version-0.10.0-blue)

<!-- Nachher: -->
![version](https://img.shields.io/badge/version-1.1.0-blue)
```

**Verifikation:**
```bash
grep "version-" README.md
# Muss version-1.1.0 zeigen
```

**Commit:**
```
docs(readme): fix version badge 0.10.0 → 1.1.0
```

---

## Phase 8: Cargo Dependabot Alerts (nach 24h)

**Kontext:** Beim Push wurden 7 Vulnerabilities gemeldet (2 high, 4 moderate, 1 low).
Die Cargo-Alerts werden noch indexiert. Nach ~24h prüfen:

```bash
gh api "repos/lfl1337/Hime/dependabot/alerts?state=open&per_page=100" \
  --jq '.[] | {number, ecosystem: .dependency.package.ecosystem, dependency: .dependency.package.name, severity: .security_advisory.severity, summary: .security_advisory.summary}'
```

Für jeden offenen Cargo-Alert:
1. Betroffenes Crate identifizieren
2. In `app/frontend/src-tauri/Cargo.toml` updaten (falls direkte Dependency)
   oder `cargo update <crate>` ausführen (falls transitiv)
3. `cargo check` zur Verifikation

### Verifikation (am Ende von Phase 8)
```bash
gh api "repos/lfl1337/Hime/dependabot/alerts?state=open&per_page=100" \
  --jq 'length'
# Ziel: 0
```

---

## Gesamtfortschritt-Tracker

```
[ ] Phase 1 — AUDIT-001: Build fix (Cargo.toml)
[ ] Phase 2 — AUDIT-002: Path Traversal (training.py)
[ ] Phase 2 — AUDIT-003: npm audit fix
[ ] Phase 3 — AUDIT-004: apiFetch in training.ts
[ ] Phase 3 — AUDIT-006: Config-Wert-Validierung
[ ] Phase 3 — AUDIT-007: File Handle Context Manager
[ ] Phase 4 — AUDIT-005: SQLite Indexes
[ ] Phase 4 — AUDIT-008: DEFAULT_WATCH_FOLDER → Settings
[ ] Phase 4 — AUDIT-012: .env.example anlegen
[ ] Phase 5 — AUDIT-010: response_model für dict-Endpoints
[ ] Phase 5 — AUDIT-011: Return Type _log_requests
[ ] Phase 5b — AUDIT-022: README Versions-Badge
[ ] Phase 6 — AUDIT-009: Patch Dependency Updates
[ ] Phase 7 — AUDIT-013: React.lazy Code Splitting
[ ] Phase 8 — Cargo Dependabot Alerts prüfen
```

---

## Dateien pro Phase (Quick Reference)

| Phase | Zu lesende Dateien | Zu ändernde Dateien |
|-------|-------------------|---------------------|
| 1 | `src-tauri/Cargo.toml` | `src-tauri/Cargo.toml` |
| 2A | `routers/training.py` | `routers/training.py` |
| 2B | — | `app/frontend/` (npm) |
| 3A | `api/training.ts`, `api/client.ts` | `api/training.ts` |
| 3B | `services/training_runner.py:136-154` | `services/training_runner.py` |
| 3C | `services/training_runner.py:157-164` | `services/training_runner.py` |
| 4A | `database.py` | `database.py` |
| 4B | `main.py`, `config.py` | `main.py`, `config.py` |
| 4C | `config.py` (alle Fields) | `.env.example` (neu) |
| 5A | `routers/training.py` | `routers/training.py` |
| 5B | `main.py:97-106` | `main.py` |
| 6 | `package.json` | `package.json` (npm) |
| 7 | `App.tsx` (Router) | `App.tsx` |
| 8 | GitHub API | `src-tauri/Cargo.toml` |
