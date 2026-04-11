# Phase 0 — Repo-Inventar

**Zeitstempel:** 20260411_0232
**Datum:** 2026-04-11

## Verzeichnis-Tree (Tiefe 3)

```
.
./.claude
./.claude/worktrees
./.claude/worktrees/agent-a6727894
./.claude/worktrees/agent-ad54c288
./.claude/worktrees/v1.2.1-ws1
./.claude/worktrees/v1.2.1-ws2
./.claude/worktrees/v1.2.1-ws4
./.env
./.env.example
./.github
./.github/dependabot.yml
./.github/workflows
./.github/workflows/code-scan.yml
./.github/workflows/secret-scan.yml
./.gitignore
./.worktrees
./.worktrees/pipeline-v2
ANALYSIS_v1.2.0.md
AUDIT_PLAN.md
AUDIT_REPORT.md
README.md
V121_HANDOFF.md
app/
app/.claude/settings.local.json
app/.gitignore
app/CLAUDE.md
app/README.md
app/VERSION
app/backend/
app/backend/.env.example
app/backend/.venv/
app/backend/app/
app/backend/hime-backend.lock
app/backend/hime.db
app/backend/logs/
app/backend/mcp_server/
app/backend/pyproject.toml
app/backend/run.py
app/backend/tests/
app/backend/uv.lock
app/build/
app/build/hime-backend-x86_64-pc-windows-msvc.spec
app/build/pyinstaller/
app/build/version_info.txt
app/docker/.gitkeep
app/frontend/
app/frontend/dist/
app/frontend/eslint.config.js
app/frontend/index.html
app/frontend/package-lock.json
app/frontend/package.json
app/frontend/postcss.config.js
app/frontend/public/
app/frontend/src/
app/frontend/src-tauri/
app/frontend/tailwind.config.js
app/frontend/tsconfig.app.json
app/frontend/tsconfig.json
app/frontend/tsconfig.node.json
app/frontend/vite.config.ts
app/hime.db
app/logs/audit.log
data/
data/aligned/
data/analysis/
data/analysis/analysis_results.jsonl
data/analysis/checkpoint.json
data/epubs/ (14 EPUB-Dateien)
data/raw_en/ (Mushoku_Tensei, Overlord, ReZero, ShuuKura, Sword_Art_Online)
data/raw_jp/ (Mushoku_Tensei, Overlord, ReZero, ShuuKura)
data/raw_jparacrawl/
data/training/ (diverse .jsonl Trainingsdaten)
docs/superpowers/
docs/superpowers/migration/
docs/superpowers/plans/ (28 Plan-Dokumente)
downloads(programme)/
frontend/src-tauri/binaries/
modelle/
modelle/gemma4-e4b/ (GGUF-Dateien, diverse Quantisierungen)
modelle/lfm2-24b/ (Safetensors)
modelle/lfm2-2b/ (Safetensors)
modelle/lmstudio-community/ (DeepSeek-R1, Qwen2.5-14B, Qwen2.5-32B, gemma-3-27b GGUF)
modelle/lora/Qwen2.5-32B-Instruct/ (checkpoint-B, cycle-1)
modelle/qwen3-2b/ (Safetensors)
modelle/qwen3-30b/ (Safetensors, unvollstaendig — nur config+merges)
modelle/qwen3-9b/ (Safetensors)
modelle/translategemma-12b/ (Safetensors)
modelle/translategemma-27b/ (Safetensors)
obsidian-vault/ (series_1, series_2 Chunks)
plans/comparison-tab.md
prompts/ (13 Prompt-Dateien inkl. pipeline_v2.md)
scripts/ (Training, Scraper, EPUB-Extraktor, Vault-Organizer etc.)
scripts/callbacks/ (manual_save.py, smart_stopping.py)
scripts/training_config.json
scripts/training_config_v121_proposed.json
unsloth_compiled_cache/
```

## Git-Status

- **Branch:** main
- **Letzter Commit:** `baebda0` — fix(tests): call init_db() in session-scoped autouse fixture so migrations run before direct DB fixtures
- **Remote:** `origin https://github.com/lfl1337/Hime.git`
- **Uncommitted Changes:** Zahlreiche untracked Dateien (??)
  - Analyse/Plan-Dokumente: ANALYSIS_v1.2.0.md, diverse docs/superpowers/plans/*
  - Backend: app/backend/hime-backend.lock, dev.bat
  - Modelle (nicht getrackt): lfm2-24b, lfm2-2b, lora/checkpoint-B, lora/cycle-1, qwen3-2b, qwen3-30b, qwen3-9b, translategemma-12b, translategemma-27b
  - Obsidian-Config: .obsidian/*.json
  - Prompts: 8 untracked Prompt-Dateien
  - unsloth_compiled_cache/
  - Keine geaenderten (modified) getrackte Dateien — sauberer Working Tree abgesehen von untracked Files

## Schlüsseldateien

| Datei | Existiert | Groesse | Letztes Update |
|---|---|---|---|
| app/VERSION | Ja | 7 Bytes (Inhalt: `1.1.2`) | 2026-03-31 — chore: bump version to 1.1.2 |
| app/CLAUDE.md | Ja | 6.448 Bytes | 2026-04-07 — docs: update CLAUDE.md for v1.2.0 |
| README.md | Ja | 2.537 Bytes | 2026-04-07 — docs: add project README |

**Auffaelligkeit:** VERSION steht auf `1.1.2`, obwohl CLAUDE.md bereits fuer v1.2.0 aktualisiert wurde. Versionsbump wurde vermutlich noch nicht durchgefuehrt.

## Pipeline v2 — Soll vs. Doku

### Gefundene Pipeline-v2-Dokumentation

1. **prompts/pipeline_v2.md** — Haupt-Architekturspec (365 Zeilen, vollstaendig)
2. **docs/superpowers/plans/pipeline-v2-subsystem-breakdown.md** (4,4 KB)
3. **docs/superpowers/plans/pipeline-v2-ws-a-preprocessing.md** (41 KB)
4. **docs/superpowers/plans/pipeline-v2-ws-b-stage1.md** (72 KB)
5. **docs/superpowers/plans/pipeline-v2-ws-c-stage23.md** (45 KB)
6. **docs/superpowers/plans/pipeline-v2-ws-d-stage4.md** (63 KB)
7. **docs/superpowers/plans/pipeline-v2-ws-e-runner.md** (51 KB)
8. **docs/superpowers/plans/pipeline-v2-ws-f-downloads.md** (16 KB)
9. **docs/superpowers/plans/pipeline-v2-ws-h-vault-organizer.md** (51 KB)
10. **.worktrees/pipeline-v2/** — Git Worktree fuer Pipeline-v2-Entwicklung vorhanden

### Soll-Ist-Vergleich

| Stage | Soll (erwartete Architektur) | Ist (Doku + Modelle auf Disk) | Status |
|---|---|---|---|
| Pre-Processing | EPUB-Import, MeCab, RAG-Query, regelbasiert | Dokumentiert in pipeline_v2.md + ws-a Plan | MATCH |
| Stage 1A | Qwen2.5-32B LoRA, Checkpoint 12400, Ollama GGUF Q4_K_M | Dokumentiert; LoRA-Checkpoints unter modelle/lora/Qwen2.5-32B-Instruct/ vorhanden; GGUF via lmstudio-community vorhanden | MATCH |
| Stage 1B | TranslateGemma-12B LoRA, Training geplant (Cloud) | Doku sagt: Training geplant **lokal (RTX 5090)**, nicht Cloud; Basismodell als Safetensors unter modelle/translategemma-12b/ vorhanden | ABWEICHUNG — Doku sagt lokal statt Cloud |
| Stage 1C | Qwen3.5-9B LoRA, Training geplant (Cloud) | Doku sagt: Training geplant **lokal (RTX 5090)**, nicht Cloud; modelle/qwen3-9b/ vorhanden (Safetensors) | ABWEICHUNG — Doku sagt lokal statt Cloud |
| Stage 1D | Gemma4 E4B, Inference-only, GGUF | Dokumentiert; modelle/gemma4-e4b/ mit zahlreichen GGUF-Quantisierungen vorhanden | MATCH |
| Stage 1E | JMdict/MeCab Lexikon, algorithmisch | Dokumentiert als "bereits implementiert" | MATCH |
| Stage 2 | TranslateGemma-27B (Merger), Transformers Safetensors | Dokumentiert; modelle/translategemma-27b/ mit 12 Safetensors-Shards vorhanden | MATCH |
| Stage 3 | Qwen3.5-35B-A3B MoE (Polish), Unsloth | Dokumentiert (Unsloth oder Transformers); Modell NICHT lokal vorhanden — muss noch heruntergeladen werden | MODELL FEHLT |
| Stage 4 | Reader Panel: 5x LFM2 + Aggregator | **GROSSE ABWEICHUNG:** Doku beschreibt **15x Qwen3.5-2B** Personas (nicht LFM2) + **1x LFM2-24B-A2B** als Aggregator; modelle/qwen3-2b/ vorhanden; modelle/lfm2-24b/ vorhanden; modelle/lfm2-2b/ ebenfalls vorhanden | ABWEICHUNG — Architektur ist 15x Qwen3.5-2B + 1x LFM2-24B Aggregator |
| Post-Processing | ebooklib EPUB-Export, regelbasiert | Dokumentiert in pipeline_v2.md | MATCH |

### Zusammenfassung der Abweichungen

1. **Stage 1B/1C Training-Ort:** Die erwartete Spezifikation sagt "Cloud", die aktuelle Doku spezifiziert "lokal (RTX 5090)". Basismodelle sind bereits heruntergeladen.
2. **Stage 3 Modell fehlt:** Qwen3.5-35B-A3B ist weder unter modelle/ noch als GGUF vorhanden. Download steht aus (siehe pipeline-v2-ws-f-downloads.md).
3. **Stage 4 Architektur weicht stark ab:** Die erwartete Tabelle nennt "5x LFM2 + Aggregator", die tatsaechliche Pipeline-v2-Spec beschreibt **15x Qwen3.5-2B Personas + 1x LFM2-24B-A2B Aggregator**. Dies ist eine bewusste Design-Entscheidung (dokumentiert), keine Inkonsistenz — die erwartete Tabelle scheint veraltet.
4. **Qwen3.5-2B fehlt lokal:** Nur Qwen3-2B vorhanden (Qwen3, nicht Qwen3.5). Falls Qwen3.5-2B tatsaechlich benoetigt wird, muss es noch heruntergeladen werden.
5. **VERSION nicht gebumpt:** VERSION zeigt 1.1.2, obwohl die Dokumentation bereits v1.2.0 referenziert.

### Vorhandene Modelle auf Disk (modelle/)

| Verzeichnis | Inhalt | Fuer Pipeline v2 |
|---|---|---|
| gemma4-e4b/ | 20 GGUF-Dateien (diverse Quants) | Stage 1D |
| lfm2-24b/ | Safetensors + Config | Stage 4 Aggregator |
| lfm2-2b/ | Safetensors + Config | Unklar (nicht in Spec) |
| lmstudio-community/ | DeepSeek-R1-32B, Qwen2.5-14B, Qwen2.5-32B, gemma-3-27b GGUF | Stage 1A (Qwen2.5-32B); Rest = Legacy |
| lora/Qwen2.5-32B-Instruct/ | checkpoint-B, cycle-1 | Stage 1A LoRA |
| qwen3-2b/ | Safetensors | Evtl. Stage 4 Reader (aber Qwen3, nicht Qwen3.5) |
| qwen3-30b/ | Unvollstaendig (nur config+merges) | Nicht in Spec |
| qwen3-9b/ | 4 Safetensors-Shards | Stage 1C Basis |
| translategemma-12b/ | 5 Safetensors-Shards | Stage 1B Basis |
| translategemma-27b/ | 12 Safetensors-Shards | Stage 2 Merger |
