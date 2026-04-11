# Phase 7 — Frontend-Integration

## Dateistruktur

```
app/frontend/src/
├── App.tsx
├── main.tsx
├── globals.d.ts
├── store.ts
├── api/
│   ├── client.ts
│   ├── compare.ts
│   ├── epub.ts
│   ├── glossary.ts
│   ├── models.ts
│   ├── pipeline_v2.ts
│   ├── rag.ts
│   ├── review.ts
│   ├── training.ts
│   ├── translate.ts
│   ├── useBookPipelineV2.ts
│   ├── verify.ts
│   └── websocket.ts
├── components/
│   ├── BackendBanner.tsx
│   ├── BookDetails.tsx
│   ├── BookPipelinePanel.tsx
│   ├── GlossaryEditor.tsx
│   ├── LiveOutput.tsx
│   ├── ModelSelector.tsx
│   ├── ModelStatusDashboard.tsx
│   ├── PipelineExplanation.tsx
│   ├── PipelineProgress.tsx
│   ├── RagIndexPanel.tsx
│   ├── ReaderPanelView.tsx
│   ├── Sidebar.tsx
│   ├── Stage1Panel.tsx
│   ├── StatusBadge.tsx
│   ├── TrainingExplanation.tsx
│   ├── VerifyButton.tsx
│   ├── comparison/
│   │   ├── ComparisonPills.tsx
│   │   ├── ConsensusPanel.tsx
│   │   ├── LiveModelCard.tsx
│   │   ├── LiveViewTab.tsx
│   │   ├── ModelComparisonTab.tsx
│   │   ├── ModelPanel.tsx
│   │   └── modelConfig.ts
│   └── epub/
│       ├── BookCard.tsx
│       ├── BookLibrary.tsx
│       ├── ChapterList.tsx
│       ├── LeftPanel.tsx
│       ├── ParagraphNavigator.tsx
│       └── TranslationWorkspace.tsx
├── hooks/
│   └── useModelPolling.ts
├── types/
│   └── comparison.ts
├── utils/
│   └── connectionRegistry.ts
└── views/
    ├── Comparison.tsx
    ├── Editor.tsx
    ├── Settings.tsx
    ├── TrainingMonitor.tsx
    └── Translator.tsx
```

**Gesamt:** 51 TypeScript/TSX-Dateien (13 API, 24 Components, 5 Views, 9 sonstige)

## Tauri-Konfiguration

- **Identifier:** `dev.Ninym.hime` -- stimmt mit Erwartung ueberein
- **Version:** `1.1.2` (tauri.conf.json, Cargo.toml, package.json alle konsistent)
- **Build:**
  - beforeDevCommand: `npm run vite`
  - devUrl: `http://localhost:1420` (korrekt)
  - beforeBuildCommand: `npm run vite build`
  - frontendDist: `../dist`
- **Bundle:**
  - Targets: `nsis`
  - externalBin: `binaries/hime-backend`
  - Publisher: "Hime Project"
  - Icons: 32x32, 128x128, 128x128@2x, icns, ico
- **winresource:** Keine Konflikte gefunden. Kein `winresource`-Eintrag in Cargo.toml oder tauri.conf.json.
- **Cargo.toml:** Sauber, keine winresource-Dependency, kein build.rs mit WinRes.

## API-Client

- **Base-URL:** In Dev-Modus: `window.location.origin` (Vite-Proxy). In Produktion: `http://127.0.0.1:{port}` wobei Port aus `hime-backend.lock` gelesen oder 18420-18430 geprobt wird.
- **Default-Port:** `18420` -- stimmt mit Backend-Port ueberein
- **Port-Discovery:** Lock-File aus `%APPDATA%\dev.Ninym.hime\` → Probe 18420-18430 → Fallback 18420

### API-Funktionen

| Funktion | HTTP-Methode | Frontend-Pfad | Backend-Route (vollstaendig) | Vorhanden |
|---|---|---|---|---|
| `createSourceText` | POST | `/api/v1/texts/` | `/api/v1/texts/` | Ja |
| `startTranslation` | POST | `/api/v1/translations/translate` | `/api/v1/translations/translate` | Ja |
| `getTranslation` | GET | `/api/v1/translations/{id}` | `/api/v1/translations/{translation_id}` | Ja |
| `listTranslations` | GET | `/api/v1/translations/` | `/api/v1/translations/` | Ja |
| `startCompare` | POST | `/api/v1/compare` | `/api/v1/compare` | Ja |
| `fetchModelEndpoints` | GET | `/api/v1/models` | `/api/v1/models` | Ja |
| `checkHealth` | GET | `/health` | `/health` | Ja |
| `getHealthInfo` | GET | `/health` | `/health` | Ja |
| `checkBackendOnline` | GET | `/health` | `/health` | Ja |
| `getTrainingStatus` | GET | `/api/v1/training/status` | `/api/v1/training/status` | Ja |
| `getCheckpoints` | GET | `/api/v1/training/checkpoints` | `/api/v1/training/checkpoints` | Ja |
| `getLossHistory` | GET | `/api/v1/training/loss-history` | `/api/v1/training/loss-history` | Ja |
| `getTrainingLog` | GET | `/api/v1/training/log` | `/api/v1/training/log` | Ja |
| `fetchAllRuns` | GET | `/api/v1/training/runs` | `/api/v1/training/runs` | Ja |
| `fetchGGUFModels` | GET | `/api/v1/training/gguf-models` | `/api/v1/training/gguf-models` | Ja |
| `createTrainingEventSource` | SSE | `/api/v1/training/stream` | `/api/v1/training/stream` | Ja |
| `startTraining` | POST | `/api/v1/training/start` | `/api/v1/training/start` | Ja |
| `stopTraining` | POST | `/api/v1/training/stop` | `/api/v1/training/stop` | Ja |
| `saveTrainingCheckpoint` | POST | `/api/v1/training/save-checkpoint` | `/api/v1/training/save-checkpoint` | Ja |
| `getRunningProcesses` | GET | `/api/v1/training/processes` | `/api/v1/training/processes` | Ja |
| `getAvailableCheckpoints` | GET | `/api/v1/training/available-checkpoints/{model}` | `/api/v1/training/available-checkpoints/{model_name}` | Ja |
| `getBackendLog` | GET | `/api/v1/training/backend-log` | `/api/v1/training/backend-log` | Ja |
| `getTrainingConfig` | GET | `/api/v1/training/config` | `/api/v1/training/config` | Ja |
| `updateTrainingConfig` | POST | `/api/v1/training/config` | `/api/v1/training/config` | Ja |
| `getStopConfig` | GET | `/api/v1/training/stop-config` | `/api/v1/training/stop-config` | Ja |
| `updateStopConfig` | PUT | `/api/v1/training/stop-config` | `/api/v1/training/stop-config` | Ja |
| `getCondaEnvs` | GET | `/api/v1/training/conda-envs` | `/api/v1/training/conda-envs` | Ja |
| `getHardwareStats` | GET | `/api/v1/hardware/stats` | `/api/v1/hardware/stats` | Ja |
| `getHardwareHistory` | GET | `/api/v1/hardware/history` | `/api/v1/hardware/history` | Ja |
| `getMemoryDetail` | GET | `/api/v1/hardware/memory-detail` | `/api/v1/hardware/memory-detail` | Ja |
| `createHardwareEventSource` | SSE | `/api/v1/hardware/stream` | `/api/v1/hardware/stream` | Ja |
| `runReview` | POST | `/api/v1/review` | `/api/v1/review` | Ja |
| `verifyParagraph` | POST | `/api/v1/verify` | `/api/v1/verify` | Ja |
| `getGlossary` | GET | `/api/v1/books/{id}/glossary` | `/api/v1/books/{book_id}/glossary` | Ja |
| `addTerm` | POST | `/api/v1/books/{id}/glossary/terms` | `/api/v1/books/{book_id}/glossary/terms` | Ja |
| `updateTerm` | PUT | `/api/v1/books/{id}/glossary/terms/{tid}` | `/api/v1/books/{book_id}/glossary/terms/{term_id}` | Ja |
| `deleteTerm` | DELETE | `/api/v1/books/{id}/glossary/terms/{tid}` | `/api/v1/books/{book_id}/glossary/terms/{term_id}` | Ja |
| `autoExtract` | POST | `/api/v1/books/{id}/glossary/auto-extract` | `/api/v1/books/{book_id}/glossary/auto-extract` | Ja |
| `buildIndex` (RAG) | POST | `/api/v1/rag/index/{book_id}` | `/api/v1/rag/index/{book_id}` | Ja |
| `getStats` (RAG) | GET | `/api/v1/rag/series/{id}/stats` | `/api/v1/rag/series/{series_id}/stats` | Ja |
| `deleteIndex` (RAG) | DELETE | `/api/v1/rag/series/{id}` | `/api/v1/rag/series/{series_id}` | Ja |
| `importEpub` | POST | `/api/v1/epub/import` | `/api/v1/epub/import` | Ja |
| `getLibrary` | GET | `/api/v1/epub/books` | `/api/v1/epub/books` | Ja |
| `getChapters` | GET | `/api/v1/epub/books/{id}/chapters` | `/api/v1/epub/books/{book_id}/chapters` | Ja |
| `getParagraphs` | GET | `/api/v1/epub/chapters/{id}/paragraphs` | `/api/v1/epub/chapters/{chapter_id}/paragraphs` | Ja |
| `saveTranslation` | POST | `/api/v1/epub/paragraphs/{id}/translation` | `/api/v1/epub/paragraphs/{paragraph_id}/translation` | Ja |
| `exportChapter` | GET | `/api/v1/epub/export/{chapter_id}` | `/api/v1/epub/export/{chapter_id}` | Ja |
| `rescanBookChapters` | POST | `/api/v1/epub/books/{id}/rescan` | `/api/v1/epub/books/{book_id}/rescan` | Ja |
| `updateBookSeries` | PATCH | `/api/v1/epub/books/{id}` | `/api/v1/epub/books/{book_id}` | Ja |
| `getEpubSettings` | GET | `/api/v1/epub/settings` | `/api/v1/epub/settings` | Ja |
| `updateEpubSetting` | POST | `/api/v1/epub/settings` | `/api/v1/epub/settings` | Ja |
| `triggerPreprocess` | POST | `/api/v1/pipeline/{id}/preprocess` | `/api/v1/pipeline/{book_id}/preprocess` | Ja |
| `createWebSocket` | WS | `/ws/translate/{jobId}` | `/ws/translate/{job_id}` | Ja |
| `createBookPipelineWebSocket` | WS | `/api/v1/pipeline/{id}/translate` | `/api/v1/pipeline/{book_id}/translate` | Ja |

### Backend-Routen ohne Frontend-Caller

| Route | Methode | Pfad | Kommentar |
|---|---|---|---|
| texts | GET | `/api/v1/texts/` | Liste aller SourceTexts -- kein expliziter Frontend-Call |
| texts | GET | `/api/v1/texts/{text_id}` | Einzelnen SourceText abrufen -- kein Frontend-Call |
| texts | DELETE | `/api/v1/texts/{text_id}` | SourceText loeschen -- kein Frontend-Call |
| translations | DELETE | `/api/v1/translations/{translation_id}` | Translation loeschen -- kein Frontend-Call |
| models | POST | `/api/v1/models/{model_key}/download` | Modell-Download -- kein Frontend-Call |
| lexicon | GET | `/api/v1/lexicon/translate` | Lexikon-Uebersetzung -- kein Frontend-Call |
| flywheel | POST | `/api/v1/training/flywheel/export` | Flywheel-Export -- kein Frontend-Call |
| rag | POST | `/api/v1/rag/query` | RAG-Query -- kein Frontend-Call |
| rag | POST | `/api/v1/rag/vault/sync` | Vault-Sync -- kein Frontend-Call |
| streaming | WS | `/ws/translate` | WS ohne job_id -- vermutlich Legacy |

**10 Backend-Routen** haben keinen direkten Frontend-Caller.

### Frontend-Calls ohne passende Backend-Route

Keine gefunden. Alle Frontend-API-Aufrufe haben eine korrespondierende Backend-Route.

## Views

| Erwartete View | Status | Datei |
|---|---|---|
| Translator | vorhanden | `src/views/Translator.tsx` |
| Comparison | vorhanden | `src/views/Comparison.tsx` |
| Editor | vorhanden | `src/views/Editor.tsx` |
| Training Monitor | vorhanden | `src/views/TrainingMonitor.tsx` |
| Library | **fehlt als eigene View** | Eingebettet in `src/components/epub/BookLibrary.tsx` (Component, nicht View) |
| Glossary | **fehlt als eigene View** | Eingebettet in `src/components/GlossaryEditor.tsx` (Component, nicht View) |
| Settings | vorhanden (unerwartet) | `src/views/Settings.tsx` |

**Hinweis:** Library und Glossary existieren als Komponenten, nicht als eigene View-Dateien. Sie werden vermutlich in andere Views eingebettet (z.B. Editor/Translator).

## Build-Scripts

Aus `package.json`:
```json
{
  "vite": "vite",
  "dev:backend": "cd ../backend && uv run python run.py",
  "dev:frontend": "tauri dev",
  "dev": "concurrently --kill-others-on-fail \"npm:dev:backend\" \"npm:dev:frontend\"",
  "build": "tauri build",
  "tauri": "tauri",
  "lint": "eslint .",
  "preview": "vite preview"
}
```

- `dev` startet Backend + Frontend gleichzeitig via `concurrently`
- `build` ruft `tauri build` auf (bundelt Backend-Binary via `externalBin`)
- Kein separates `test`-Script vorhanden

## Abhaengigkeiten

- **React:** 19.2.4
- **Tauri API:** 2.10.1
- **Zustand:** 4.5.7
- **Recharts:** 3.8.1 (fuer Training-Charts)
- **Tailwind CSS:** 3.4.19
- **TypeScript:** 5.9.3
- **Vite:** 8.0.3

## Probleme

1. **Kein Frontend-Test-Script:** `package.json` enthaelt kein `test`-Script. Es gibt keine erkennbare Test-Infrastruktur (kein vitest, jest o.ae. in devDependencies).

2. **10 Backend-Routen ohne Frontend-Caller:**
   - `GET/DELETE /api/v1/texts/` und `/api/v1/texts/{id}` -- CRUD fuer SourceTexts nur teilweise angebunden (nur POST)
   - `DELETE /api/v1/translations/{id}` -- Loeschen nicht im UI
   - `POST /api/v1/models/{model_key}/download` -- Modell-Download-Feature nicht im Frontend
   - `GET /api/v1/lexicon/translate` -- Lexikon-Endpunkt komplett ungenutzt
   - `POST /api/v1/training/flywheel/export` -- Flywheel-Export nicht im Frontend
   - `POST /api/v1/rag/query` und `POST /api/v1/rag/vault/sync` -- RAG-Queries nicht direkt aufgerufen
   - `WS /ws/translate` -- WS ohne job_id (moeglicherweise Legacy)

3. **Library/Glossary keine eigenen Views:** Stattdessen als Komponenten eingebettet. Kein direktes Routing zu `/library` oder `/glossary`.

4. **CSP deaktiviert:** `tauri.conf.json` hat `"csp": null` -- fuer lokale App akzeptabel, aber security-technisch suboptimal.

5. **Versionsinkonsistenz:** tauri.conf.json/Cargo.toml/package.json alle auf `1.1.2`, aber CLAUDE.md erwaehnt Plaene fuer v1.2.0/v1.2.1. Kein Versions-Mismatch zwischen den Dateien selbst.

---

## Zielversion

**Das Ziel ist v2.0.0** — Hime vollstaendig funktionsfaehig mit allen Pipeline-v2-Features. Wenn alle Phasen abgeschlossen, alle fehlenden Modelle heruntergeladen, das modulare hybride Trainingssystem implementiert, alle Backend-Routen im Frontend angebunden und alle offenen Punkte aus diesem Verification-Report behoben sind, wird die Version auf **2.0.0** gesetzt.
