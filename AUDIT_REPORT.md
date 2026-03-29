# Hime — DevOps Audit Report

**Datum:** 2026-03-29
**Auditor:** Claude Sonnet 4.6 (automatisierter Read-Only Audit)
**Scope:** Vollständiger Codebase-Audit: Security, Dependencies, Code Quality, Performance, Struktur

---

## Executive Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical | 1 |
| 🟠 High | 2 |
| 🟡 Medium | 5 |
| 🟢 Low | 5 |
| 🔵 Info | 8 |
| **Total** | **21** |

### Top 5 dringendste Fixes

1. **[Critical] Build ist kaputt** — `CreateJobObjectW` benötigt fehlendes `Win32_Security` Feature in Cargo.toml → App lässt sich nicht kompilieren
2. **[High] Path Traversal** — `/available-checkpoints/{model_name}` validiert den Pfadparameter nicht → potenziell traversal außerhalb des lora-Verzeichnisses
3. **[High] npm picomatch HIGH** — Method Injection in POSIX Character Classes, `<2.3.2`
4. **[Medium] stop-config fetch bypasses API client** — training.ts verwendet raw `fetch()` statt `apiFetch()` → bricht bei non-default Ports
5. **[Medium] SQLite ohne Indexes** — Keine expliziten Indexes auf Haupt-Tabellen → langsame Queries bei wachsenden Daten

---

## Detailed Findings

---

### AUDIT-001
- **Severity:** 🔴 Critical
- **Category:** Build / DevOps
- **File:** `app/frontend/src-tauri/Cargo.toml:20-24` + `app/frontend/src-tauri/src/lib.rs:87`
- **Description:** Der Tauri-Build schlägt fehl. `CreateJobObjectW` ist in `windows` crate v0.61.3 hinter dem `Win32_Security` Feature gegattet, das in Cargo.toml fehlt. Die aktuelle Feature-Liste enthält nur `Win32_Foundation`, `Win32_System_JobObjects`, `Win32_System_Threading`.
  ```
  error[E0432]: unresolved import `windows::Win32::System::JobObjects::CreateJobObjectW`
  note: the item is gated behind the `Win32_Security` feature
  ```
- **Recommendation:** `"Win32_Security"` zur Feature-Liste in Cargo.toml hinzufügen:
  ```toml
  [target.'cfg(target_os = "windows")'.dependencies]
  windows = { version = "0.61", features = [
      "Win32_Foundation",
      "Win32_Security",        # ← hinzufügen
      "Win32_System_JobObjects",
      "Win32_System_Threading",
  ] }
  ```
- **Effort:** Quick fix (< 5 Minuten)

---

### AUDIT-002
- **Severity:** 🟠 High
- **Category:** Security / Path Traversal
- **File:** `app/backend/app/routers/training.py:150-153`
- **Description:** Der Endpoint `GET /available-checkpoints/{model_name}` verwendet `model_name` als Path-Parameter ohne Validierung gegen `_RUN_PATTERN`. Alle anderen Endpoints wenden den Pattern `r"^[\w\-\.]+$"` via `Query(pattern=...)` an. Hier fehlt dies. `get_available_checkpoints(model_name)` konstruiert intern `Path(settings.models_base_path) / "lora" / model_name` — ein model_name wie `../../etc/passwd` würde das lora-Verzeichnis verlassen.
  ```python
  @router.get("/available-checkpoints/{model_name}")
  async def api_available_checkpoints(model_name: str) -> dict:   # kein Pattern!
      return {"checkpoints": get_available_checkpoints(model_name)}
  ```
  Erschwerend: `get_available_checkpoints` führt kein `resolve()`-Check durch (anders als `start_training`).
- **Recommendation:**
  ```python
  from fastapi import Path as FPath

  @router.get("/available-checkpoints/{model_name}")
  async def api_available_checkpoints(
      model_name: str = FPath(pattern=_RUN_PATTERN, max_length=128)
  ) -> dict:
      return {"checkpoints": get_available_checkpoints(model_name)}
  ```
- **Effort:** Quick fix (< 15 Minuten)

---

### AUDIT-003
- **Severity:** 🟠 High
- **Category:** Dependencies / Security
- **File:** `app/frontend/package.json` (transitiv)
- **Description:** `npm audit` meldet eine HIGH-Severity-Vulnerabilität in `picomatch < 2.3.2` (GHSA-3v7f-55p6-f55p). Method Injection in POSIX Character Classes ermöglicht Glob-Matching-Umgehung. CVSS 5.3 (AV:N/AC:L/PR:N). Dazu `brace-expansion < 1.1.13` mit MODERATE (CVSS 6.5, CWE-400 — DoS durch Memory Exhaustion).
- **Recommendation:**
  ```bash
  cd app/frontend
  npm audit fix
  # Falls nicht automatisch:
  npm install picomatch@latest
  ```
- **Effort:** Quick fix

---

### AUDIT-004
- **Severity:** 🟡 Medium
- **Category:** Quality / API Consistency
- **File:** `app/frontend/src/api/training.ts:231,238`
- **Description:** Die Funktionen `getStopConfig()` und `updateStopConfig()` verwenden direkte `fetch()` Calls mit hartkodiertem `baseUrl`, anstatt den zentralen `apiFetch()` Wrapper aus `client.ts`. Der `apiFetch` Wrapper setzt korrekte Headers und handhabt Port-Discovery. Die direkten Calls können bei non-default Ports (z.B. 8001-8010 Fallback) scheitern — der `baseUrl` müsste dann separat ermittelt werden.
  ```typescript
  // Aktuell:
  const res = await fetch(`${baseUrl}/api/v1/training/stop-config`)

  // Sollte sein:
  const res = await apiFetch('/api/v1/training/stop-config')
  ```
- **Recommendation:** Beide Calls auf `apiFetch()` umstellen.
- **Effort:** Quick fix (< 15 Minuten)

---

### AUDIT-005
- **Severity:** 🟡 Medium
- **Category:** Performance / Database
- **File:** `app/backend/app/database.py:52-76`
- **Description:** Die Tabelle `hardware_stats` wird ohne Indexes erstellt. Queries auf `timestamp` (für die 24h-Pruning und History-Abfragen) laufen als Full Table Scan. Bei 5-Sekunden-Intervall sammeln sich ~17.000 Zeilen/Tag an. Gleiches gilt für die `translations`-Tabelle: Queries nach Status, Paginierung, etc. haben keinen Index.
- **Recommendation:** Indexes in der `init_db()` Migration hinzufügen:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_hardware_stats_timestamp ON hardware_stats(timestamp);
  CREATE INDEX IF NOT EXISTS idx_translations_created ON translations(created_at);
  ```
- **Effort:** Quick fix (< 20 Minuten)

---

### AUDIT-006
- **Severity:** 🟡 Medium
- **Category:** Security / Subprocess
- **File:** `app/backend/app/services/training_runner.py:136-154`
- **Description:** Werte aus `training_config.json` werden unvalidiert als CLI-Argumente übergeben. `str(_cfg["target_loss"])` und `str(_cfg["patience"])` konvertieren beliebige JSON-Werte in Strings. Beispiel: `{"target_loss": [1, 2, 3]}` → `"--target-loss [1, 2, 3]"`. Da `subprocess.Popen` mit einer Liste (`shell=False`) aufgerufen wird, ist echte Shell-Injection nicht möglich. Aber argparse-Exploits oder Trainer-Crashes sind denkbar.
- **Recommendation:** Werte vor dem Hinzufügen validieren:
  ```python
  if _cfg.get("target_loss") is not None:
      val = float(_cfg["target_loss"])  # TypeError/ValueError wenn kein Float
      if val > 0:
          cmd += ["--target-loss", str(val)]
  ```
- **Effort:** Quick fix (< 30 Minuten)

---

### AUDIT-007
- **Severity:** 🟡 Medium
- **Category:** Quality / File Handle Management
- **File:** `app/backend/app/services/training_runner.py:157-164`
- **Description:** File Handle wird ohne Context Manager geöffnet. Obwohl der Kommentar erklärt warum das sicher ist (Child erbt eigene Kopie des FD), ist das Pattern nicht idiomatisch und bei Exceptions zwischen `open()` und `close()` läuft der Handle.
  ```python
  _stderr_fh = open(log, "a", encoding="utf-8")      # ← kein 'with'
  proc = subprocess.Popen(cmd, ..., stderr=_stderr_fh)
  _stderr_fh.close()  # wird nie erreicht wenn Popen wirft
  ```
- **Recommendation:**
  ```python
  with open(log, "a", encoding="utf-8") as _stderr_fh:
      proc = subprocess.Popen(cmd, ..., stderr=_stderr_fh)
  # Nach 'with': Parent-Handle geschlossen, Child-Kopie bleibt offen
  ```
- **Effort:** Quick fix (5 Minuten)

---

### AUDIT-008
- **Severity:** 🟡 Medium
- **Category:** Security / Config
- **File:** `app/backend/app/config.py:44-47` + `app/backend/app/main.py:27`
- **Description:** Hardcoded Windows-Pfade als Defaults in Production-Code:
  - `models_base_path = r"C:\Projekte\Hime\modelle"`
  - `training_log_path = r"C:\Projekte\Hime\app\backend\logs\training"`
  - `scripts_path = r"C:\Projekte\Hime\scripts"`
  - `DEFAULT_WATCH_FOLDER = "C:/Projekte/Hime/data/epubs/"`

  Auf jeder anderen Maschine oder bei anderer Verzeichnisstruktur schlägt die App ohne `.env`-Override stumm fehl. Es existiert kein `.env.example` im Repo.
- **Recommendation:**
  1. `.env.example` erstellen mit allen überschreibbaren Variablen
  2. `DEFAULT_WATCH_FOLDER` in Settings auslagern
- **Effort:** Quick fix (20 Minuten)

---

### AUDIT-009
- **Severity:** 🟢 Low
- **Category:** Dependencies / Outdated
- **File:** `app/frontend/package.json`
- **Description:** Mehrere Major-Versionen veraltet:

  | Package | Installed | Latest | Typ |
  |---------|-----------|--------|-----|
  | `react-router-dom` | 6.30.3 | **7.13.2** | Major |
  | `tailwindcss` | 3.4.19 | **4.2.2** | Major |
  | `zustand` | 4.5.7 | **5.0.12** | Major |
  | `typescript` | 5.9.3 | **6.0.2** | Major |
  | `@eslint/js` | 9.39.4 | **10.0.1** | Major |
  | `eslint` | 9.39.4 | **10.1.0** | Major |
  | `concurrently` | 8.2.2 | **9.2.1** | Major |
  | `recharts` | 3.8.0 | **3.8.1** | Patch (harmlos) |

- **Recommendation:** Patch-Updates sofort (`npm update recharts`). Major-Updates mit Breaking-Change-Check in separaten Branches: react-router-dom v7 hat Breaking Changes bei `<Route>` API; tailwind v4 hat neues Config-System.
- **Effort:** Medium (für Major-Upgrades mit Tests)

---

### AUDIT-010
- **Severity:** 🟢 Low
- **Category:** Quality / API Consistency
- **File:** `app/backend/app/routers/training.py:63-69, 150, 165, 249, 268`
- **Description:** Mehrere Endpoints ohne `response_model=`:
  - `GET /log` — gibt `dict` zurück, kein Schema
  - `GET /available-checkpoints/{model_name}` — gibt `dict` zurück
  - `GET /config` — gibt `dict` zurück
  - `GET /conda-envs` — gibt `dict` zurück
  - `GET /backend-log` — gibt `dict` zurück
  - `POST /stop` — gibt `dict` zurück

  Das verhindert automatische OpenAPI-Dokumentation und Typ-Validierung der Response.
- **Recommendation:** Pydantic-Response-Models für diese Endpoints definieren oder zumindest `dict[str, Any]` annotieren.
- **Effort:** Medium

---

### AUDIT-011
- **Severity:** 🟢 Low
- **Category:** Quality / Type Safety
- **File:** `app/backend/app/main.py:98`
- **Description:** `_log_requests` Middleware fehlt Return-Type-Annotation:
  ```python
  async def _log_requests(request: Request, call_next):  # kein -> Response
  ```
- **Recommendation:** `-> Response` hinzufügen und `Response` importieren.
- **Effort:** Quick fix (2 Minuten)

---

### AUDIT-012
- **Severity:** 🟢 Low
- **Category:** Security / Secrets Management
- **File:** Root
- **Description:** `.env.example` fehlt im Repository. Deployment auf neuer Maschine erfordert Trial-and-Error zum Herausfinden aller nötigen Umgebungsvariablen.
- **Recommendation:** `.env.example` anlegen mit:
  ```env
  PORT=8000
  MODELS_BASE_PATH=C:\path\to\modelle
  TRAINING_LOG_PATH=C:\path\to\logs\training
  SCRIPTS_PATH=C:\path\to\scripts
  INFERENCE_URL=http://127.0.0.1:8080/v1
  RATE_LIMIT_PER_MINUTE=60
  ```
- **Effort:** Quick fix (10 Minuten)

---

### AUDIT-013
- **Severity:** 🟢 Low
- **Category:** Performance / Frontend
- **File:** `app/frontend/src/views/TrainingMonitor.tsx`
- **Description:** Kein Code-Splitting / Lazy Loading für Views. Alle Views werden im initialen Bundle geladen. TrainingMonitor ist mit 39 `useState`-Hooks und 15 `useEffect`-Hooks die komplexeste Komponente — lädt auch wenn kein Training aktiv ist.
  ```
  useEffect:  15
  useState:   39
  useMemo/useCallback: 5
  React.memo: vorhanden
  ```
- **Recommendation:** `React.lazy()` + `Suspense` für View-Level Routing einführen.
- **Effort:** Medium

---

### AUDIT-014
- **Severity:** 🔵 Info
- **Category:** Security / Network
- **File:** `app/backend/app/main.py:116-128`
- **Description:** CORS korrekt konfiguriert — nur Tauri-spezifische Origins erlaubt, kein `*`.
  ```python
  allow_origins=["http://localhost:1420", "http://127.0.0.1:1420",
                 "tauri://localhost", "http://tauri.localhost"]
  ```
  Backend bindet nur auf `127.0.0.1` (run.py). Kein Netzwerk-Exposure möglich. ✅

---

### AUDIT-015
- **Severity:** 🔵 Info
- **Category:** Security / Input Validation
- **File:** `app/backend/app/utils/sanitize.py`
- **Description:** Sanitisierung mit 28 Regex-Patterns gegen Prompt-Injection, Max-Length 50k, Pattern-basierte Jailbreak-Detection. Alle POST/PUT-Endpoints verwenden Pydantic-Validation. ✅

---

### AUDIT-016
- **Severity:** 🔵 Info
- **Category:** Security / Audit Logging
- **File:** `app/backend/app/middleware/audit.py`
- **Description:** AuditMiddleware loggt jeden Request als JSON-Lines (timestamp, method, path, status, duration_ms, client IP). Middleware-Reihenfolge korrekt: Audit **vor** CORS (Zeile 114 vs 117). ✅

---

### AUDIT-017
- **Severity:** 🔵 Info
- **Category:** Security / Subprocess
- **File:** `app/backend/app/services/training_runner.py`
- **Description:** Alle `subprocess.Popen`/`subprocess.run` Calls verwenden Listen-Argumente (`shell=False`). `taskkill`-Aufruf übergibt PID als `str(p)` — da `p` eine Integer-Variable aus `psutil.pid_exists()` ist, keine Injection möglich. ✅

---

### AUDIT-018
- **Severity:** 🔵 Info
- **Category:** Quality / Dead Code
- **File:** `app/backend/unsloth_compiled_cache/`
- **Description:** Alle bare `except:` Klauseln (44 Stück) und alle TODO/FIXME-Kommentare befinden sich ausschließlich in `unsloth_compiled_cache/` — Third-Party generierter Code, kein eigener Code betroffen. ✅

---

### AUDIT-019
- **Severity:** 🔵 Info
- **Category:** Quality / TypeScript
- **File:** `app/frontend/src/views/Settings.tsx:286,296,420`, `app/frontend/src/views/TrainingMonitor.tsx:728,743`
- **Description:** Alle `any`-Casts in TypeScript sind für nicht-standardisierte Browser-APIs:
  - `(performance as any).memory` — Chrome-spezifische Memory-API
  - `(window as any).__himeDebug` — internes Debug-Objekt
  - `(window as any).gc` — V8 GC-Trigger für Dev-Tools

  Alle in Dev-only-Blöcken oder Debug-UIs. Akzeptabel. ✅

---

### AUDIT-020
- **Severity:** 🔵 Info
- **Category:** Security / Git
- **File:** `.gitignore`
- **Description:** `.env` ist in `.gitignore` enthalten (Zeile 45). Keine sensiblen Dateien im Git-Index (`git ls-files` zeigt keine .env, node_modules, __pycache__, .pyc, dist/ oder build/ Dateien). ✅

---

### AUDIT-021
- **Severity:** 🔵 Info
- **Category:** Security / Secrets Scan
- **File:** `app/backend/app/inference.py:23`
- **Description:** `api_key="local"` ist ein Dummy-Wert für die lokale LLM-Server-API (llama.cpp/vLLM), die keine echte Authentifizierung benötigt. Der Kommentar in der Datei erklärt dies explizit. Kein echter Secret-Fund. ✅

---

## Dependabot Summary Table

| # | Package | Ecosystem | Severity | Status | Action |
|---|---------|-----------|----------|--------|--------|
| #8 | `brace-expansion` | npm | Medium | Open | `npm audit fix` |
| #7 | `brace-expansion` | npm | Medium | Open | `npm audit fix` |
| – | `picomatch` | npm | High | (lokal) | `npm audit fix` |
| – | Cargo-Alerts | rust | TBD | Indexierung läuft | Nach Push prüfen |

> **Hinweis:** GitHub meldete beim Push "7 vulnerabilities (2 high, 4 moderate, 1 low)" — die Cargo-Vulnerabilities werden noch indexiert. Erneuter Check nach ~24h empfohlen:
> ```bash
> gh api "repos/lfl1337/Hime/dependabot/alerts?state=open&per_page=100" \
>   --jq '.[] | {number, ecosystem: .dependency.package.ecosystem, dependency: .dependency.package.name, severity: .security_advisory.severity}'
> ```

---

## Dependency Update Plan

### Sofort (Security-Fixes)
```bash
cd app/frontend
npm audit fix          # behebt brace-expansion + picomatch transitiv
```

### Kurzfristig (Patch/Minor, non-breaking)
```bash
npm install recharts@latest        # 3.8.0 → 3.8.1 (Bugfix)
npm install typescript-eslint@latest  # 8.57.1 → 8.57.2
npm install vite@latest            # 8.0.1 → 8.0.3
```

### Mittelfristig (Major, Breaking Changes prüfen)
In separaten Feature-Branches, jeweils mit Tests:

1. `zustand` v4 → v5: API weitgehend kompatibel, `immer`-Middleware-Signatur geändert
2. `@types/node` 24 → 25: Typ-Inkompatibilitäten möglich
3. `concurrently` 8 → 9: CLI-API geändert (package.json scripts prüfen)
4. `react-router-dom` v6 → v7: Breaking Changes bei `<Route>`, `loader`, `action` API
5. `tailwindcss` v3 → v4: Komplett neues Config-System (kein `tailwind.config.js` mehr)
6. `typescript` v5 → v6: Strengere Typ-Checks (mit `noImplicitAny` etc. testen)
7. `eslint` + `@eslint/js` v9 → v10: ESLint 10 erfordert ESM-only Config

---

---

### AUDIT-022
- **Severity:** 🔵 Info
- **Category:** Quality / Documentation
- **File:** `README.md:7`
- **Description:** Das Versions-Badge im README zeigt `0.10.0`, die App ist bei `1.1.0` (Cargo.toml, main.py, tauri.conf.json). Alle anderen Stellen sind korrekt aktualisiert.
  ```markdown
  ![version](https://img.shields.io/badge/version-0.10.0-blue)
  ```
- **Recommendation:** Badge auf `1.1.0` aktualisieren:
  ```markdown
  ![version](https://img.shields.io/badge/version-1.1.0-blue)
  ```
- **Effort:** Quick fix (1 Minute)

---

### Zusätzliche Checks (aus devops-audit-prompt.md)

| Check | Ergebnis |
|-------|----------|
| TODO/FIXME/HACK in eigenem Code | ✅ Keine — alle TODOs ausschließlich in `unsloth_compiled_cache/` (Third-Party) |
| TypeScript `: any` | ✅ Nur für nicht-standardisierte Browser-APIs (`performance.memory`, `window.gc`) — akzeptabel (siehe AUDIT-019) |
| README.md vorhanden und aktuell | ⚠️ Vorhanden (176 Zeilen), aber Versions-Badge veraltet (siehe AUDIT-022) |
| Git-getrackte Dateien die nicht sein sollten | ✅ Keine — `.env`, `node_modules`, `__pycache__`, `.pyc`, `dist/`, `build/` nicht im Index |
| Auskommentierter Dead Code >5 Zeilen | ✅ Keiner — mehrzeilige Kommentarblöcke in eigenem Code sind ausschließlich Dokumentation, kein deaktivierter Code |

---

## Sicherheitsarchitektur — Gesamtbewertung

```
CORS:           ✅ Sicher (nur Tauri-Origins)
Network:        ✅ localhost-only (127.0.0.1)
Input Valid.:   ✅ Pydantic + 28 Injection-Patterns
Subprocess:     ✅ shell=False überall, PIDs validiert
Audit Log:      ✅ Vollständig, korrekte Middleware-Reihenfolge
Secrets:        ✅ Keine echten Secrets im Code
Path Traversal: ⚠️  1 Endpoint ohne Validation (AUDIT-002)
Dependencies:   ⚠️  2 npm-Vulnerabilities offen
Build:          ❌  Cargo-Kompilierung schlägt fehl (AUDIT-001)
```
