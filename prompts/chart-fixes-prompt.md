# Loss History Chart — LR Achse Fix + Info Panel

Only visual changes. No logic changes. No version bump.

---

## FIX 1: Learning Rate unsichtbar wenn Grad Norm aktiv

Learning Rate (~0.00006) und Grad Norm (~0.5) teilen sich die rechte Y-Achse. LR ist 10.000x kleiner und zeigt als flache Linie bei 0.

### Fix: Drei unabhängige Y-Achsen

- **Linke Y-Achse:** Train Loss + Eval Loss (Scale ~0 bis 1.5) — `yAxisId="left"`
- **Rechte Y-Achse 1:** Grad Norm (Scale ~0 bis 1.0) — `yAxisId="gradNorm"`
- **Rechte Y-Achse 2:** Learning Rate (Scale ~0 bis 0.0002) — `yAxisId="lr"`

Recharts unterstützt mehrere YAxis-Komponenten:

```tsx
<YAxis yAxisId="left" orientation="left" ... />
<YAxis yAxisId="gradNorm" orientation="right" ... />
<YAxis yAxisId="lr" orientation="right" hide={true} domain={['auto','auto']} />
```

- LR-Achse verstecken (`hide={true}`) — zu viele sichtbare Achsen ist unübersichtlich
- LR-Wert ist im Tooltip auf Hover lesbar
- Jede YAxis nur anzeigen wenn der zugehörige Metrik-Toggle aktiv ist
- Jede `<Line>` muss das korrekte `yAxisId` haben:
  - Train Loss → `yAxisId="left"`
  - Eval Loss → `yAxisId="left"`
  - Grad Norm → `yAxisId="gradNorm"`
  - Learning Rate → `yAxisId="lr"`

---

## FIX 2: Info-Panel unter dem Chart

Füge eine klappbare Info-Sektion direkt unter dem Loss History Chart ein.

### Verhalten

- **Default:** Zugeklappt, zeigt nur einen kleinen Link: `ℹ Was bedeuten diese Werte?`
- **Klick:** Klappt eine Card auf mit Erklärungen zu allen Metriken

### Inhalt der Card

```
📊 Metriken-Erklärung

Train Loss — Wie gut das Modell die Trainingsdaten lernt.
  ✅ Gut: < 0.5 (Modell lernt effektiv)
  ⚠️ Okay: 0.5 – 0.8 (lernt noch, braucht mehr Zeit)
  🔴 Hoch: > 1.0 (Anfang oder Problem)
  📉 Sollte über die Zeit sinken

Eval Loss — Wie gut das Modell auf NEUEN Daten generalisiert.
  ✅ Gut: < 0.95 (verbessert sich gegenüber Base Model)
  ⚠️ Stagniert: Mehrere Evals ohne Verbesserung
  🔴 Steigt: Overfitting — Modell memoriert statt zu lernen
  📉 Wichtigster Indikator für echte Qualität

Learning Rate — Schrittgröße beim Lernen.
  📉 Sinkt planmäßig von ~2e-4 gegen 0 (Cosine Schedule)
  ℹ️ Kein "gut" oder "schlecht" — folgt dem Scheduler

Grad Norm — Wie stark die Gewichte pro Schritt angepasst werden.
  ✅ Stabil: 0.3 – 0.7 (gleichmäßiges Lernen)
  ⚠️ Spikes: > 1.0 (schwieriger Batch, normalerweise harmlos)
  🔴 Explodiert: > 5.0 dauerhaft (Training instabil)

Epoch-Marker (E2, E3) — Start einer neuen Epoche.
  ℹ️ Loss steigt kurz am Epochenanfang — das ist NORMAL
  📉 Sollte danach schnell wieder fallen
```

### Styling

- Dark Card: `bg-zinc-800/90` oder `bg-zinc-900` Hintergrund
- Text: `text-zinc-400` für Beschreibungen
- Farbige Emoji-Indikatoren wie oben
- Kompakt, jede Metrik als kleiner Block mit Metrik-Name fett
- Kein Bullet-Point-Style, eher Block-Layout
- Toggle-Button: `text-zinc-500 hover:text-zinc-300`, kleiner Text

---

## Zusammenfassung

Nur zwei visuelle Änderungen:
1. Learning Rate bekommt eine eigene versteckte Y-Achse damit die Linie sichtbar ist
2. Klappbares Info-Panel unter dem Chart erklärt alle Metriken mit Richtwerten

Keine Logik-Änderungen. Kein Version Bump. Keine anderen Dateien anfassen.
