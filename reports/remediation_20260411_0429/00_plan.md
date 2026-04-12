# Phase 0 — Planning & Setup

_Status: complete — awaiting Proceed with Phase 1_

## 1. Report Reconciliation

Cross-check vs. Issue Matrix (baseline report: `reports/verification_20260411_0232/FINAL_REPORT.md`, commit `baebda0`):

- **C1 (Qwen3-30B-A3B missing)** — confirmed, unchanged. Report §2 documents `modelle/qwen3-30b/` at only 386 MB (nur Config, README, merges.txt — keine .safetensors). HuggingFace-ID `Qwen/Qwen3-30B-A3B`, geschätzt ~16 GB. Report verweist auf Phase 2.
- **C2 (Stage4Aggregator.load never called)** — confirmed, unchanged. Report §"Critical Issues/C2" says: "`reader.load(settings)` wird aufgerufen, aber `aggregator.load()` wird **nie** aufgerufen. Bei `_infer_one()` tritt `AttributeError` auf (`self._model` ist None)." → Einzeiler-Fix in `runner_v2.py`.
- **C3 (train_generic.py kennt keine v2-Modelle)** — confirmed. Report §3 listet TranslateGemma-12B / Qwen3.5-9B / Qwen3-30B-A3B explizit als "FEHLT" in MODEL_CONFIGS. Monolithisches Skript, 562 Zeilen.
- **C4 (Hybrid training / data registry missing)** — confirmed. Report §3 "KRITISCH: Hybrides Trainingssystem fehlt komplett" — kein dynamisches Datenquellen-Management, keine Daten-Registry, kein inkrementelles Training, kein Flywheel→Training.
- **C5 (Curriculum-Learning nicht aktiviert)** — confirmed. Code existiert in `curriculum.py` + `train_hime.py`, aber aktive `training_config.json` hat keinen `curriculum`-Block. Vorgeschlagene Variante liegt als `training_config_v121_proposed.json`.
- **W1 (4 divergente hime.db)** — confirmed. Report §4 Tabelle: Root `hime.db` (33.3 MB, 21 Bücher / 430 Kapitel / 80313 Absätze) vs. `app/backend/hime.db` (33.0 MB, 21 Bücher / 329 Kapitel / 80077 Absätze) vs. `app/hime.db` (12 KB, altes Schema) vs. `.worktrees/pipeline-v2/hime.db` (88 KB, leer).
- **W2 (Foreign Keys disabled)** — confirmed. `PRAGMA foreign_keys = 0` in allen 4 DBs.
- **W3 (circular import epub_export_service ↔ runner_v2)** — confirmed. Phase-8-Sektion: funktioniert bei normalem App-Start, bricht bei isoliertem Service-Import.
- **W4 (bge-m3 fehlt)** — confirmed. `modelle/embeddings/bge-m3` existiert nicht. RAG-System dadurch blockiert (siehe §5).
- **W5 (10 Backend-Routen ohne Frontend-Caller)** — confirmed. Report §7 listet explizit: texts GET/DELETE, translations DELETE, models download, lexicon translate, flywheel export, rag query/vault-sync, ws/translate Legacy.
- **W6 (Pipeline-v2 Model IDs hardcoded)** — confirmed. Stage 2/3 HF-IDs im Code, Stage 4 config-basiert (inkonsistent).
- **W7 (keine Frontend-Test-Infrastruktur)** — confirmed. Kein `test`-Script in package.json, kein vitest/jest in devDependencies.
- **W8 (kein Pipeline-Dry-Run)** — confirmed. Weder `runner.py` noch `runner_v2.py` haben `--dry-run`.
- **W9 (VERSION inconsistency)** — confirmed. `app/VERSION` = 1.1.2, `main.py` = 1.1.2, Doku referenziert v1.2.0/v1.2.1.
- **W10 (eval_loss > target)** — confirmed. train_loss ~0.46 vs. eval_loss 1.0066 (target 0.4). Out of scope für diese Remediation — gehört in ein eigenes Training-Tuning-Phase.

**Additional observations / deltas since the report was generated:**

- `pyproject.toml` hat unstaged modification (seit Verifikation): laut git status `M app/backend/pyproject.toml`. Report vermerkt in "Während der Verifikation behoben": huggingface_hub-Duplikat entfernt + openai/pynvml/fugashi nachinstalliert. Mutmaßlich reflektiert der unstaged Diff genau diese Fixes — vor Phase 1 kurz verifizieren.
- `app/backend/hime-backend.lock` ist neu (untracked). Neutral, gehört zum uv-Backend.
- `dev.bat` ist neu untracked — Dev-Hilfsskript, neutral.
- Viele neue Plan-Dokumente in `docs/superpowers/plans/` — keine Relevanz für Code/Criticals.
- `obsidian-vault/` mit `.obsidian/*.json` Settings neu — RAG/Vault, neutral.
- `modelle/lfm2-24b/`, `modelle/lfm2-2b/`, `modelle/qwen3-2b/`, `modelle/qwen3-30b/`, `modelle/qwen3-9b/`, `modelle/translategemma-12b/`, `modelle/translategemma-27b/`, `modelle/lora/Qwen2.5-32B-Instruct/checkpoint-B/`, `modelle/lora/Qwen2.5-32B-Instruct/cycle-1/` werden als untracked angezeigt — das sind die vom Report bestätigten vorhandenen Modelle plus LoRA-Checkpoints. Kein Widerspruch.

**No new criticals observed beyond the Issue Matrix.** Der aktuelle Tree (HEAD = `baebda0`) stimmt mit dem Verifikationsstand überein; die Ergänzungen sind ausschließlich Doku/Unstaged-Fixes.

## 2. Report freshness

- Report commit: `baebda0` (2026-04-11 01:59:39 +0200)
- Current HEAD: `baebda0` (2026-04-11 01:59:39 +0200)
- Delta: **identical** — HEAD und Report-Commit sind derselbe Commit, keine Drift.

## 3. Issue list by priority

| ID  | Sev      | Thema                                                       | Phase |
|-----|----------|-------------------------------------------------------------|-------|
| C1  | Critical | Qwen3-30B-A3B weights missing                               | 2 |
| C2  | Critical | `Stage4Aggregator.load()` never called in runner_v2.py      | 3 |
| C3  | Critical | Training scripts don't know Pipeline-v2 models              | 5 |
| C4  | Critical | Hybrid training / data registry missing                     | 6 |
| C5  | Critical | Curriculum-Learning not activated                           | 5 |
| W1  | Warning  | 4 divergent `hime.db` files                                 | 1 |
| W2  | Warning  | Foreign keys disabled (all DBs)                             | 1 |
| W3  | Warning  | Circular import epub_export_service ↔ runner_v2             | 3 |
| W4  | Warning  | bge-m3 embedding model missing                              | 2 |
| W5  | Warning  | 10 backend routes without frontend caller                   | 8 doc |
| W6  | Warning  | Pipeline-v2 model IDs partially hardcoded                   | 4 |
| W7  | Warning  | No frontend test infrastructure                             | 7 |
| W8  | Warning  | No pipeline `--dry-run` mode                                | 4 |
| W9  | Warning  | VERSION inconsistency                                       | 9 |
| W10 | Warning  | eval_loss > target_loss                                     | Out of scope |

## 4. Estimated diff scope per phase

- **Phase 1:** DB files reorganised, 1 edit to `database.py` (`PRAGMA foreign_keys = ON`), VERSION audit (doc-only)
- **Phase 2:** ~17 GB downloaded into `modelle/qwen3-30b/` and `modelle/embeddings/bge-m3/`, 2 new dirs
- **Phase 3:** ~3 edits (`runner_v2.py` aggregator.load fix, `pipeline/__init__.py` lazy import for W3, new test files)
- **Phase 4:** ~8 new/modified files (`dry_run.py`, `config/pipeline_v2.py`, stage2/stage3 refactor for W6, runner_v2 wiring, tests)
- **Phase 5:** `train_generic.py` extended with v2 models, `training_config.json` curriculum block merged, new tests
- **Phase 6:** `scripts/hime_data.py`, `data/registry.jsonl`, `app/backend/app/routers/data_registry.py`, `main.py` include, tests
- **Phase 7:** `app/frontend/package.json` + `vitest.config.ts` + `test/setup.ts` + ~7 test files
- **Phase 8:** ~10 new backend test files + fixtures + `conftest.py` extensions
- **Phase 9:** VERSION bump in 6 files, `CHANGELOG.md`, `REMEDIATION_REPORT.md`

## 5. Rollback strategy

Jede Phase ist über `git diff` vor dem finalen Commit reviewable. Wenn eine Phase fehlschlägt, wird ihr Datei-Set manuell rückgängig gemacht — bis Phase 9 findet **kein** Branch-Management statt. Es werden **keine** git commits während der Remediation gemacht — Luca reviewt den akkumulierten Diff in Phase 9 und committet manuell. Bei kritischem Zweifel: Phase-Report anschauen, dort stehen alle geänderten Dateien.

## 6. Baseline walkthrough result

**Status:** PASS

**Test stack used:**
- Backend: uvicorn on `127.0.0.1:23420` (`HIME_DATA_DIR=/tmp`, `HIME_PROJECT_ROOT=N:/Projekte/NiN/Hime`, launched via `app/backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir app/backend`). Health probe returned `{"status":"ok","app":"hime","version":"1.1.2"}` on first try. The backend created a fresh empty `/tmp/hime.db` (90 KB, migrations applied) on startup — the pre-made read-only prod copy at `/tmp/hime_baseline.db` was therefore NOT consumed, which is actually a stronger isolation guarantee (production data literally untouched).
- Frontend: Vite on `127.0.0.1:23421` via `npx vite --port 23421 --strictPort --host 127.0.0.1`. Lock file `app/backend/hime-backend.lock` was temporarily overwritten from `{"port": 18420, "pid": 60736}` to `{"port": 23420, "pid": 0}` so the Vite proxy would forward `/api/*` and `/ws/*` to the test backend; the original value was saved to `/tmp/hime_lock_orig_baseline.json` and restored afterwards.
- Screenshot capture: the Chrome MCP `computer → screenshot` action returns JPEGs only as inline conversation data (no disk sink), so baseline screenshots are produced by loading `html2canvas@1.4.1` from jsdelivr inside each page via `javascript_tool` and POSTing the PNG dataURL to a tiny one-off Python receiver on `127.0.0.1:23422` that writes the bytes into `reports/remediation_20260411_0429/screenshots/baseline/`. The receiver script (`_tmp_screenshot_receiver.py`) was removed after shutdown; to re-run a walkthrough in future phases, the html2canvas-via-javascript_tool + local receiver pattern should be reused. Alternative for later phases: use Playwright or Chrome DevTools Protocol (`Page.captureScreenshot`) directly instead of html2canvas — it avoids the jsdelivr CDN dependency.

**Views captured (7/7):**
| File | Route | Status |
|---|---|---|
| `01_root.png` | `/` | OK — Translator sidebar + empty Library |
| `02_translator.png` | `/` (same route, re-captured) | OK — `/` IS the Translator view in `App.tsx` line 111, so this intentionally aliases view 01 |
| `03_comparison.png` | `/comparison` | OK — 3-pane Gemma/DeepSeek/Qwen layout, all marked "Offline" (no inference servers running, expected) |
| `04_editor.png` | `/editor` | OK — empty-state card "Translation Editor — Select a book from the Translator tab…" |
| `05_training_monitor.png` | `/monitor` (actual route name, NOT `/training-monitor`) | OK — live hardware stats, prior Qwen2.5-32B checkpoint-620 run rendered, SSE loss stream active |
| `06_settings.png` | `/settings` | OK — theme, training defaults, all path fields populated with expected values |
| `07_library.png` | `/` (Library tab active, same route as 01/02) | OK — empty-state "Import an EPUB to get started" because the test backend uses a fresh DB |

**Baseline console errors:** see `baseline_console_errors.txt` — **0 errors, 0 warnings total across all views**. The only non-debug console output is the single `[client] baseUrl = http://127.0.0.1:23421 (dev/proxy mode)` DEBUG line from `src/api/client.ts:77` on initial page load (informational, always present). All 47 observed `/api/v1/*` requests on the Monitor view returned HTTP 200. These are the KNOWN baseline counts; later phases must introduce zero new console errors or warnings.

**Notes:**
- The prior "Qwen2.5-32B-Instruct, checkpoint-620, Epoch 0.05/3, 1.8%, ETA 1729:34:58" rendered on the Monitor view is pre-existing state from the real filesystem (reads `training_log_path = app/backend/logs/training`). It's not a training run triggered by this walkthrough — no Start/Stop/Run buttons were clicked.
- Routes differ from the spec: the plan mentioned `/training` or `/training-monitor`, but the actual route is `/monitor` (see `App.tsx` line 114). Filename `05_training_monitor.png` preserved for cross-phase diff stability.
- `/translator` and `/library` do NOT exist as distinct routes; both `02_translator.png` and `07_library.png` re-capture `/` because that route hosts the `<Translator />` component which in turn hosts the `<BookLibrary />` panel. Treating later phase diffs: any file-size delta between 01/02/07 is likely cosmetic (Claude overlay chip position, toast animations), NOT app state change.
- The `html2canvas` library injects DEBUG console spam during each snapshot; this is filtered out of the per-view files and the aggregated `baseline_console_errors.txt` because it's tooling noise, not app output.
- The Chrome MCP `read_network_requests` tool returned 3.5M chars unfiltered on the Monitor view and hit the token limit; filtering by `urlPattern: "/api/"` gave 47 requests, all 200. Future phases should always pass a URL pattern when probing the Monitor view.

## 7. Open questions for Luca — RESOLVED 2026-04-11

Alle 5 Fragen wurden nach Abschluss von Phase 0 und vor Start von Phase 1 beantwortet.

1. **Authoritative DB (W1):** ✅ **Root `hime.db`** ist autoritativ (430 Kapitel, 80.313 Absätze — die vollständigere Variante).
   - **Phase 1 Vorgabe:** Vor jeder Änderung manuelles Backup `hime.db.bak_20260411` anlegen.
   - Die anderen drei (`app/backend/hime.db`, `app/hime.db`, `.worktrees/pipeline-v2/hime.db`) werden in `archive/obsolete_dbs/` **verschoben**, nicht gelöscht.

2. **Download budget (C1, W4):** ✅ **17 GB freigegeben.** Beide Modelle (Qwen3-30B-A3B + bge-m3) sind zwingend für Pipeline v2 (Stage 3 Polish + RAG Embeddings). Platz ist ausreichend.
   - **Separater Aufräum-Schritt (NICHT Teil dieser Remediation):** 49 GB Alt-Modelle + ~80 GB Gemma4-Quant-Überschuss können später entfernt werden, falls Platz knapp wird.

3. **Modularer Rewrite von train_generic.py (C3):** ✅ **Modular umbauen** mit strikter Rückwärts­kompatibilität.
   - **Phase 5 Vorgabe:** Plugin-Struktur wie in Plan-Sektion 5.1 beschrieben — `scripts/training/configs/` (eine Config-Datei pro Modell) + `scripts/training/trainers/` (ein Plugin pro Backend: Unsloth, Transformers). `train_generic.py` wird zum dünnen Dispatcher.
   - **Backward-Compat ist Pflicht:** Die bestehenden v1-Configs (`qwen32b`, `qwen14b`, `qwen72b`, `gemma27b`, `deepseek`) müssen weiterhin funktionieren, damit `checkpoint-12400` weiter bedient werden kann.
   - **Backward-Compat-Absicherung:** Ein parametrisierter Unit-Test muss alle alten Config-Namen explizit laden und validieren. Ohne diesen Test gilt Phase 5 als nicht bestanden.

4. **Chrome MCP (alle Phasen):** ✅ **Bestätigt** für `127.0.0.1:23421` (Vite UI) **und** `127.0.0.1:23420` (Backend Calls via Browser im Proxy-Modus).
   - Safety-Regeln aus dem Chrome-MCP-Abschnitt bleiben strikt in Kraft: keine destruktiven Klicks (Delete / Reset / Clear), keine externen Navigationen, nur Dry-Run. Erst ab Phase 4, wenn `HIME_DRY_RUN=1` verfügbar ist, dürfen Pipeline-Runs aus der UI getriggert werden.

5. **Branch strategy:** ✅ **Neuer Branch `remediation/v2.0.0-20260411`** — in Phase 0 angelegt (post-HALT, mit Freigabe). Main bleibt unverändert als Fallback.
   - **Commits NUR am Ende von Phase 9 nach Lucas Review.** Keine Zwischen-Commits, außer Luca gibt sie explizit frei.
   - Falls die Remediation entgleist: Branch wegwerfen, main ist unberührt.

## 8. Constraints reminder

- NO git commits während der Remediation
- NO training runs
- NO downloads ohne Phase-2-Freigabe
- Test-Ports ≥ 23420
- Test-DBs nur in `tmp_path` / `:memory:`
- Chrome MCP Baseline = Vergleichsfloor für alle späteren Phasen-Error-Diffs
- HALT nach jeder Phase, auf `Proceed with Phase N+1` warten
