# Claude Code Prompt — Comparison Tab (比) für Hime

## Aufgabe

Build the **Comparison Tab (比)** in the Hime desktop app. Currently the Comparison view at `app/frontend/src/views/ComparisonView.tsx` is a placeholder. Replace it with a fully functional, production-ready UI consisting of two sub-tabs.

---

## Projektkontext

- **Projekt-Root:** `C:\Projekte\Hime\`
- **Frontend:** `app/frontend/` — Tauri + React + TypeScript + Tailwind CSS
- **Backend:** `app/backend/` — FastAPI (Python), läuft auf `http://127.0.0.1:19522`
- **State Management:** Redux Toolkit (Slices in `app/frontend/src/store/`)
- **Routing:** Die 4 Haupt-Tabs (Translator 翻, Comparison 比, Editor 編, Monitor 訓) werden über die Sidebar navigiert
- **API-Key:** Wird bei jedem Request als `X-API-Key` Header mitgesendet (liegt in `app/frontend/.api_key`, wird beim Start gelesen)
- **Design-System:** Dark Theme (zinc-900 Hintergrund, zinc-800 Cards, purple-500/purple-600 Akzente), konsistent mit den bestehenden Tabs
- **Aktuelle Version:** 0.9.6 → wird auf **1.0.0** gebumpt (Milestone: alle 4 Haupt-Views implementiert)

---

## Tab-Struktur

Der Comparison Tab enthält zwei Sub-Tabs, umschaltbar über eine Pill-Navigation am oberen Rand der View:

| Sub-Tab | Label (JP) | Label (EN) | Zweck |
|---------|-----------|------------|-------|
| 1 | 比較 | Model Comparison | Vergleich der 3 Stage-1-Modelle auf demselben Inputtext |
| 2 | 生 | Live View | Echtzeit-Status aller 3 Stage-1-Modelle (Training / Inferenz / Idle) |

### Pill-Navigation

- Zwei nebeneinanderliegende Pills: `[比較]` `[生]`
- Aktiver Pill: `bg-purple-500 text-white`
- Inaktiver Pill: `bg-zinc-700 text-zinc-400 hover:bg-zinc-600`
- Abgerundete Ecken: `rounded-lg`
- Position: oben links in der View, unterhalb des Tab-Headers
- Default beim Öffnen: Sub-Tab 1 (比較) ist aktiv

---

## Sub-Tab 1: Model Comparison (比較)

### Zweck

Der Benutzer gibt japanischen Text ein und lässt alle 3 Stage-1-Modelle parallel übersetzen. Die Ergebnisse werden nebeneinander angezeigt, darunter ein Consensus-Panel mit der zusammengeführten Übersetzung.

### Layout (von oben nach unten)

#### 1. Eingabebereich

- **Textarea** für japanischen Eingabetext
  - Volle Breite des Content-Bereichs
  - Mindesthöhe: 120px, maximal 300px, resizable vertikal
  - Placeholder: `日本語テキストを入力...`
  - Font: Serif-Font (gleicher Font wie im Translator-Tab, z.B. `Noto Serif JP` oder `serif` Fallback)
  - Hintergrund: `bg-zinc-800`, Border: `border border-zinc-700 focus:border-purple-500`
  - Padding: `p-4`
  - Textfarbe: `text-zinc-100`

- **"Compare" Button** rechts neben oder unterhalb der Textarea
  - Text: `比較する` (mit Tooltip "Compare translations")
  - Farbe: `bg-purple-600 hover:bg-purple-500 text-white`
  - **Disabled-Zustand:** Wenn KEIN Modell online ist ODER die Textarea leer ist
    - `opacity-50 cursor-not-allowed`
    - Tooltip im Disabled-Zustand: `"Start inference servers to enable comparison"`
  - **Loading-Zustand:** Wenn Übersetzung läuft → Spinner-Icon + Text `"Translating..."`, Button disabled
  - Beim Klick: POST an `/api/v1/compare` mit dem japanischen Text, dann WebSocket-Streaming der Ergebnisse

#### 2. Modell-Panels (3 nebeneinander)

Drei gleichbreite Panels in einem `grid grid-cols-3 gap-4` Layout:

| Panel | Modell | Farbe-Akzent (für Badge) |
|-------|--------|--------------------------|
| 1 | Gemma 3 27B | blue-500 |
| 2 | DeepSeek R1 32B | emerald-500 |
| 3 | Qwen 32B | amber-500 |

**Jedes Panel enthält:**

- **Header:**
  - Modellname als Badge mit farbigem Akzent (links)
  - Status-Indikator (rechts):
    - **Online:** Grüner Punkt (`bg-green-500`) + Text `"Online"` in grün
    - **Offline:** Grauer Punkt (`bg-zinc-500`) + Text `"Offline"` in grau
    - **Training:** Orange pulsierender Punkt (`bg-orange-500 animate-pulse`) + Text `"Training"` in orange
  - Hintergrund Header: leicht abgesetzt, z.B. `bg-zinc-750` oder `bg-zinc-800/80`

- **Output-Bereich:**
  - Mindesthöhe: 200px
  - Scrollbar bei Overflow: `overflow-y-auto max-h-[400px]`
  - Wenn **Offline**: Zentrierter Platzhaltertext:
    ```
    Model offline
    Start inference server to compare
    ```
    Gesamtes Panel mit `opacity-60` abgedimmt
  - Wenn **Online aber kein Output**: Leer, bereit für Streaming
  - Wenn **Übersetzung läuft**: Text wird zeichenweise (oder tokenweise) per WebSocket gestreamt, mit blinkender Cursor-Animation am Ende
  - Wenn **Übersetzung abgeschlossen**: Vollständiger Text angezeigt

- **Footer:**
  - Copy-Button: Kleines Clipboard-Icon + `"Copy"` Text
    - Beim Klick: Output in Zwischenablage kopieren
    - Nach Klick: Text ändert sich kurz zu `"Copied!"` (2 Sekunden), dann zurück
    - Disabled wenn kein Output vorhanden

- **Panel-Styling:**
  - `bg-zinc-800 border border-zinc-700 rounded-xl`
  - Padding: `p-4`
  - Offline-Panels: `opacity-60` auf das gesamte Panel

#### 3. Consensus-Panel (volle Breite, darunter)

- **Header:** `"Consensus (合意)"` mit Icon (z.B. merge/combine Icon aus Lucide)
- Volle Breite: `col-span-3` oder eigener Block
- `bg-zinc-800 border border-purple-500/30 rounded-xl p-4`
- **Logik:**
  - Wenn **alle 3 Modelle** fertig übersetzt haben → Zeigt die zusammengeführte Consensus-Übersetzung
  - Wenn **weniger als 3** Modelle online sind → Zeigt die verfügbaren Outputs mit Hinweis:
    `"Partial consensus — only X of 3 models available"`
  - Wenn **kein Output** vorhanden → Leer mit Platzhaltertext:
    `"Translations will be merged here after all models complete"`
- Copy-Button analog zu den Modell-Panels

#### 4. Responsive Verhalten

- Ab `< 1200px` Breite: Panels wechseln auf `grid-cols-1` (untereinander statt nebeneinander)
- Textarea bleibt immer volle Breite

---

## Sub-Tab 2: Live View (生)

### Zweck

Echtzeit-Übersicht über den Status aller 3 Stage-1-Modelle: Wird trainiert? Ist der Inferenz-Server online? Idle?

### Layout

Drei Cards nebeneinander: `grid grid-cols-3 gap-4`

Jede Card repräsentiert ein Stage-1-Modell (gleiche Reihenfolge wie oben: Gemma, DeepSeek, Qwen).

### Card-Aufbau

#### Card Header

- Modellname (fett, `text-lg`)
- Status-Badge (rechts oben in der Card):
  - **Training:** Orange pulsierender Badge `"Training"` mit `animate-pulse`
  - **Online:** Grüner Badge `"Online"` (Inferenz-Server läuft)
  - **Idle:** Grauer Badge `"Idle"` (weder Training noch Inferenz)
  - **Offline:** Dunkelgrauer Badge `"Offline"` (Server nicht erreichbar)

#### Training-Sektion (nur sichtbar wenn Modell trainiert wird)

Wird angezeigt, wenn `GET /api/v1/training/runs` einen aktiven Run für dieses Modell zurückgibt.

- **Progress Bar:**
  - Balken: `bg-purple-600` auf `bg-zinc-700` Track
  - Text: `"Step X / 17709 (XX%)"` — Schritte und Prozent
  - Animiert: smooth transition bei Updates
- **Metriken** (als kompakte Key-Value-Paare):
  - `Loss:` aktueller Wert (z.B. `0.9506`)
  - `ETA:` geschätzte Restzeit (z.B. `~4h 23m`)
  - `Epoch:` aktuelle Epoche (z.B. `2 / 3`)
  - `LR:` aktuelle Learning Rate (z.B. `2.0e-05`)
- **Link:** `"View in Monitor →"` als klickbarer Link
  - Farbe: `text-purple-400 hover:text-purple-300`
  - Beim Klick: Navigiert zum Monitor-Tab (dispatcht die entsprechende Navigation-Action im Redux Store oder nutzt den vorhandenen Tab-Switch-Mechanismus)

#### Inferenz-Sektion (nur sichtbar wenn Inferenz-Server läuft)

Wird angezeigt, wenn `GET /api/v1/models` einen erreichbaren Endpoint für dieses Modell meldet.

- Grüner Badge: `"Ready for translation"`
- **Endpoint URL:** Monospace-Text, z.B. `http://127.0.0.1:8080/v1`
- **Last used:** `"X minutes ago"` oder `"Never"` — falls die Info vom Backend verfügbar ist, sonst weglassen
- **Model info:** Geladenes Modell (falls vom Endpoint abrufbar), z.B. `"qwen2.5-32b-instruct-Q4_K_M.gguf"`

#### Empty State (weder Training noch Inferenz aktiv)

- Card ist leicht abgedunkelt: `opacity-70`
- Zentrierter Text: `"Not active"`
- Zwei Buttons (vertikal gestapelt, kompakt):
  - `"Start Training"` → Navigiert zum Monitor-Tab
    - `bg-zinc-700 hover:bg-zinc-600 text-zinc-300`
  - `"Start Inference"` → Placeholder-Aktion (zeigt Toast: `"Inference server management coming soon"`)
    - `bg-zinc-700 hover:bg-zinc-600 text-zinc-300`

### Daten-Polling

- **Polling-Intervall:** alle 10 Sekunden
- **Kein SSE nötig** — einfaches Polling reicht für diese View
- **Endpoints:**
  - `GET /api/v1/training/runs` → Filtere nach Modellname, um pro-Modell-Training-Status zu bekommen
  - `GET /api/v1/models` → Zeigt welche Inferenz-Endpoints erreichbar sind
- **Polling starten** wenn Sub-Tab 2 aktiv ist, **stoppen** wenn der User zu Sub-Tab 1 wechselt oder den Comparison-Tab verlässt
  - Nutze `useEffect` mit Cleanup-Funktion und Dependency auf den aktiven Sub-Tab
- **Error Handling:** Wenn ein Endpoint nicht erreichbar ist (Backend offline), alle Models als `"Offline"` anzeigen, KEIN Error-Banner — einfach den Status aktualisieren

### Responsive Verhalten

- Ab `< 1200px` Breite: `grid-cols-1` (Cards untereinander)

---

## Bestehende Backend-Endpoints (KEIN neuer Endpoint nötig)

Alle benötigten Endpoints existieren bereits. Hier die relevanten:

| Endpoint | Methode | Zweck | Relevante Response-Felder |
|----------|---------|-------|--------------------------|
| `/api/v1/models` | GET | Inferenz-Server-Status für alle konfigurierten Modelle | `models[].name`, `models[].endpoint`, `models[].status` ("online"/"offline") |
| `/api/v1/training/runs` | GET | Alle Training-Runs (aktiv und vergangene) | `runs[].model_name`, `runs[].status`, `runs[].current_step`, `runs[].total_steps`, `runs[].loss`, `runs[].eta`, `runs[].epoch` |
| `/api/v1/compare` | POST | Startet einen Vergleichs-Job (alle 3 Modelle übersetzen parallel) | `job_id` (zum Streamen via WebSocket) |
| `/ws/translate/{job_id}` | WebSocket | Streamt Übersetzungs-Chunks pro Modell in Echtzeit | Messages mit `model_name`, `chunk`, `done` Feldern |

**Wichtig:** Schaue dir die tatsächliche Response-Struktur in den bestehenden Route-Handlern an, bevor du die Frontend-Typen definierst. Die obigen Felder sind Richtwerte — die exakten Feldnamen aus dem Code übernehmen.

---

## Dateistruktur (Frontend)

Erstelle bzw. bearbeite folgende Dateien:

```
app/frontend/src/
├── views/
│   └── ComparisonView.tsx          ← Hauptkomponente (ersetze den Placeholder)
├── components/
│   └── comparison/
│       ├── ComparisonPills.tsx      ← Sub-Tab Pill-Navigation
│       ├── ModelComparisonTab.tsx   ← Sub-Tab 1: Eingabe + Panels + Consensus
│       ├── ModelPanel.tsx           ← Einzelnes Modell-Panel (wiederverwendbar)
│       ├── ConsensusPanel.tsx       ← Consensus-Zusammenführung
│       ├── LiveViewTab.tsx          ← Sub-Tab 2: Live View
│       └── LiveModelCard.tsx        ← Einzelne Modell-Card für Live View
├── store/
│   └── comparisonSlice.ts          ← Redux Slice für Comparison-State
├── hooks/
│   └── useModelPolling.ts          ← Custom Hook für 10s Polling (Live View)
└── types/
    └── comparison.ts               ← TypeScript-Typen für Comparison-Daten
```

**Hinweis:** Prüfe die bestehende Dateistruktur, bevor du loslegst. Wenn es bereits ähnliche Ordner/Dateien gibt, nutze die bestehende Struktur und passe die Pfade an. Erstelle den `comparison/` Ordner nur, wenn es noch keinen solchen gibt.

---

## State Management (Redux)

Erstelle ein neues Redux Slice `comparisonSlice.ts`:

```typescript
interface ComparisonState {
  activeSubTab: 'comparison' | 'liveview';
  
  // Sub-Tab 1
  inputText: string;
  isComparing: boolean;
  modelOutputs: {
    gemma: { text: string; done: boolean; error: string | null };
    deepseek: { text: string; done: boolean; error: string | null };
    qwen: { text: string; done: boolean; error: string | null };
  };
  consensusText: string;
  currentJobId: string | null;
  
  // Sub-Tab 2 (Live View)
  modelStatuses: {
    gemma: ModelLiveStatus;
    deepseek: ModelLiveStatus;
    qwen: ModelLiveStatus;
  };
}

interface ModelLiveStatus {
  inferenceOnline: boolean;
  inferenceEndpoint: string | null;
  isTraining: boolean;
  trainingProgress: {
    currentStep: number;
    totalSteps: number;
    loss: number | null;
    eta: string | null;
    epoch: number | null;
    learningRate: number | null;
  } | null;
}
```

**Registriere den Slice** im bestehenden Redux Store (`app/frontend/src/store/index.ts` oder `store.ts`).

---

## Wichtige Implementierungsdetails

### WebSocket-Streaming (Sub-Tab 1)

1. Beim Klick auf "Compare": `POST /api/v1/compare` mit `{ text: inputText }`
2. Erhalte `job_id` aus der Response
3. Öffne WebSocket-Verbindung: `ws://127.0.0.1:19522/ws/translate/{job_id}`
4. Empfange Messages im Format (prüfe das tatsächliche Format im Backend-Code):
   ```json
   { "model": "gemma", "chunk": "The ", "done": false }
   { "model": "deepseek", "chunk": "In the ", "done": false }
   { "model": "gemma", "chunk": "flower ", "done": false }
   ...
   { "model": "gemma", "chunk": "", "done": true }
   ```
5. Aktualisiere den Redux State pro Modell mit jedem Chunk
6. Wenn ALLE 3 Modelle `done: true` → Generiere Consensus (oder warte auf Backend-Consensus)
7. **Cleanup:** Schließe WebSocket bei Unmount oder neuem Compare-Request

### Modell-Erkennung

Die Modellnamen in den Backend-Responses müssen den 3 Panels zugeordnet werden. Schaue dir an, wie die Modelle im Backend konfiguriert sind (vermutlich in einer Config-Datei oder in `app/backend/app/config.py`). Die Zuordnung könnte auf Basis des Modellnamens oder eines Identifiers passieren.

Erstelle ein Mapping, z.B.:

```typescript
const MODEL_CONFIG = {
  gemma: {
    displayName: 'Gemma 3 27B',
    matchPattern: /gemma/i,
    accentColor: 'blue',
  },
  deepseek: {
    displayName: 'DeepSeek R1 32B',
    matchPattern: /deepseek/i,
    accentColor: 'emerald',
  },
  qwen: {
    displayName: 'Qwen 32B',
    matchPattern: /qwen.*32/i,
    accentColor: 'amber',
  },
} as const;
```

### Kein Mock-Data

- Zeige **echte Statusdaten** an. Da noch keine Modelle trainiert/deployed sind, werden alle Panels "Offline" zeigen — das ist gewollt.
- **Keine Fake-Daten**, keine Dummy-Texte in den Output-Bereichen
- Die UI soll **sofort funktionieren**, sobald ein Modell online geht

### Error Handling

- **Backend nicht erreichbar:** Alle Modelle als "Offline" anzeigen, kein großes Error-Banner
- **WebSocket-Verbindung fehlgeschlagen:** Zeige dezenten Fehlertext im betroffenen Panel: `"Connection failed — retry?"` mit Retry-Button
- **Einzelnes Modell antwortet nicht:** Markiere nur dieses Panel als fehlerhaft, andere laufen weiter
- **Timeout:** Wenn ein Modell nach 120 Sekunden nicht `done: true` sendet → Zeige `"Timed out"` im Panel

### Animationen & Transitions

- Sub-Tab-Wechsel: Sanfter Fade (`transition-opacity duration-200`)
- Streaming-Text: Smooth append, kein Flackern
- Status-Wechsel: `transition-colors duration-300`
- Pulsierender Training-Indikator: `animate-pulse` (Tailwind built-in)
- Progress Bar: `transition-all duration-500 ease-out`

---

## Tests & Validierung

Nach der Implementierung:

1. **Kompilierung prüfen:** `cd app/frontend && npm run build` — darf keine TypeScript-Fehler werfen
2. **Lint prüfen:** `npm run lint` — keine ESLint-Fehler
3. **Manueller Smoke-Test:**
   - Comparison Tab öffnen → Pill-Navigation funktioniert
   - Sub-Tab 1: Textarea sichtbar, Button disabled (alle Modelle offline), Panels zeigen "Offline"
   - Sub-Tab 2: Alle 3 Cards zeigen "Not active" / "Offline", Buttons navigieren korrekt
4. **Keine Regressionen:** Stelle sicher, dass die anderen Tabs (Translator, Editor, Monitor) weiterhin funktionieren

---

## Version Bump

Nach erfolgreicher Implementierung:

```bash
python scripts/bump_version.py minor
```

Dies bumpt die Version auf **1.0.0** — ein Milestone, da alle 4 Haupt-Views nun implementiert sind. Das Script committed, tagged und pushed automatisch zu GitHub.

---

## Zusammenfassung der Anforderungen

- [ ] Placeholder in `ComparisonView.tsx` durch vollständige Implementierung ersetzen
- [ ] Pill-Navigation für 2 Sub-Tabs
- [ ] Sub-Tab 1: Japanische Text-Eingabe, 3 Modell-Panels mit Live-Streaming, Consensus-Panel
- [ ] Sub-Tab 2: 3 Live-Status-Cards mit 10s Polling, Training-/Inferenz-/Idle-States
- [ ] Redux Slice für Comparison-State
- [ ] Bestehende Endpoints nutzen (kein neues Backend nötig)
- [ ] Kein Mock-Data — echte Statusanzeige (alles offline ist OK)
- [ ] Error Handling für offline Backend, fehlgeschlagene WebSockets, Timeouts
- [ ] Responsive Layout (3-spaltig → 1-spaltig unter 1200px)
- [ ] Dark Theme konsistent mit restlicher App
- [ ] TypeScript-Typen für alle Comparison-Daten
- [ ] Build + Lint fehlerfrei
- [ ] Version bump auf 1.0.0
