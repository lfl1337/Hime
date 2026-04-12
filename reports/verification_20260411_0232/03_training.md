# Phase 3 — Trainings-Infrastruktur

## Skripte

| Skript | Existiert | Zeilen | Letztes Update |
|---|---|---|---|
| `scripts/train_generic.py` | Ja | 562 | 2026-04-07 — `merge(ws2): pipeline overhaul` |
| `scripts/train_hime.py` | Ja | 685 | 2026-04-08 — `feat(training): wire curriculum loader/callback` |

### train_generic.py CLI-Interface

```
usage: train_generic.py [-h] --model
                        {qwen32b,qwen14b,qwen72b,gemma27b,deepseek}
                        [--run-name RUN_NAME] [--epochs EPOCHS]
                        [--resume RESUME] [--log-file LOG_FILE]
                        [--data-file DATA_FILE] [--rank RANK]
                        [--output-dir OUTPUT_DIR] [--target-loss TARGET_LOSS]
                        [--patience PATIENCE] [--min-delta MIN_DELTA]
                        [--min-steps MIN_STEPS] [--max-epochs MAX_EPOCHS]
                        [--max-steps MAX_STEPS] [--full-resume] [--fresh]
                        [--model-dir MODEL_DIR]
                        [--training-data TRAINING_DATA]

Hime Generic Training Script

options:
  -h, --help            show this help message and exit
  --model {qwen32b,qwen14b,qwen72b,gemma27b,deepseek}
                        Model key
  --run-name RUN_NAME   Run name (overrides auto-derived adapter name)
  --epochs EPOCHS       Number of training epochs
  --resume RESUME       Path to checkpoint to resume from
  --log-file LOG_FILE   Tee stdout/stderr to this file
  --data-file DATA_FILE Path to JSONL training data file
  --rank RANK           LoRA rank (overrides default)
  --output-dir OUTPUT_DIR
                        Output directory for checkpoints/adapter
  --target-loss TARGET_LOSS
                        Stop when loss <= this value
  --patience PATIENCE   Evals without improvement before stopping
  --min-delta MIN_DELTA Min improvement for patience mode
  --min-steps MIN_STEPS Don't stop before this step
  --max-epochs MAX_EPOCHS
                        Max training epochs
  --max-steps MAX_STEPS Stop after this many steps (for auto-restart cycle)
  --full-resume         Full resume incl. optimizer state (may cause VRAM
                        thrashing on 32GB GPUs)
  --fresh               Ignore checkpoints, train from scratch
  --model-dir MODEL_DIR Base models directory
  --training-data TRAINING_DATA
                        Training data directory
```

### Unterstuetzte Modelle

Aus `MODEL_CONFIGS` in `train_generic.py`:

| Key | HF-Modell | LoRA-Dir | max_seq | grad_accum |
|---|---|---|---|---|
| `qwen32b` | `unsloth/Qwen2.5-32B-Instruct-bnb-4bit` | `Qwen2.5-32B-Instruct` | 1024 | 8 |
| `qwen14b` | `unsloth/Qwen2.5-14B-Instruct-bnb-4bit` | `Qwen2.5-14B-Instruct` | 1024 | 16 |
| `qwen72b` | `unsloth/Qwen2.5-72B-Instruct-bnb-4bit` | `Qwen2.5-72B-Instruct` | 512 | 32 |
| `gemma27b` | `unsloth/gemma-3-27b-it-bnb-4bit` | `Gemma-3-27B-IT` | 1024 | 16 |
| `deepseek` | `unsloth/DeepSeek-R1-Distill-Qwen-32B-bnb-4bit` | `DeepSeek-R1-Distill-Qwen-32B` | 1024 | 16 |

**Hinweis:** `train_generic.py` kennt kein Curriculum-Learning — das ist nur in `train_hime.py` implementiert.

### training_config.json

Aktive Konfiguration (`scripts/training_config.json`):
```json
{
  "stop_mode": "both",
  "target_loss": 0.4,
  "target_loss_metric": "loss",
  "target_confirmations": 3,
  "patience": 5,
  "patience_metric": "eval_loss",
  "min_delta": 0.001,
  "min_steps": 1000,
  "max_epochs": 3
}
```

**Kein Curriculum-Block** in der aktiven Config. Der Curriculum-Block existiert nur in der vorgeschlagenen Config `scripts/training_config_v121_proposed.json` (Status: `proposed`, noch nicht gemergt).

## Trainingsdaten

| Datei | Existiert | Zeilen (Soll) | Zeilen (Ist) | JSON-Schema | Groesse |
|---|---|---|---|---|---|
| `jparacrawl_500k.jsonl` | Ja | 500.000 (raw) | 500.000 | `instruction, input, output, score` | 207 MB |
| `hime_training_filtered.jsonl` | Ja | 104.866 | 104.866 | `instruction, input, output, score` | 54,6 MB |
| `shuukura_wn_aligned.jsonl` | Ja | 66 | 66 | `instruction, input, output, source, part` | 773 KB |
| `hime_training_all.jsonl` | Ja | 104.932 | 104.932 | `instruction, input, output, score` | 55,3 MB |

Alle Dateien vorhanden. Zeilenzahlen stimmen exakt mit den Soll-Werten ueberein. JSON valide (erste 3 Zeilen pro Datei erfolgreich geparsed).

**Konsistenz-Check:** `hime_training_filtered.jsonl` (104.866) + `shuukura_wn_aligned.jsonl` (66) = 104.932 = `hime_training_all.jsonl` — korrekt.

### Zusaetzliche literarische Dateien (Curriculum)

| Datei | Existiert | Groesse |
|---|---|---|
| `data/training/shuukura_jp.jsonl` | Ja | 1,0 MB |
| `data/training/seiyuu_radio_all_jp.jsonl` | Ja | 2,5 MB |

## Curriculum-Learning

### Architektur

Das Curriculum-System ist in `app/backend/app/training/curriculum.py` implementiert:

- **`CurriculumDataLoader`**: Laedt `jparacrawl_500k.jsonl`, filtert nach `min_score`-Schwellenwert und merged literarische Quellen bedingungslos dazu.
- **`Tier`-Dataclass**: Definiert eine Stufe mit `name` und `min_score`.
- **`estimate_tier_sizes()`**: Zaehlt vorab, wie viele Samples jede Stufe liefern wuerde (Sanity-Check vor Tokenisierung).
- **Caching**: Bereits geladene Tiers werden im Speicher gecached (Key = `min_score`).

### Geplante Tier-Definitionen (aus v1.2.1-Proposal)

| Tier | min_score | Beschreibung |
|---|---|---|
| `strict` | 0.70 | Nur hochwertige Paare |
| `expanded` | 0.62 | Erweiterter Datensatz |
| `loose` | 0.55 | Maximaler Datensatz |

### Promotion-Trigger
- Metrik: `eval_loss`
- Patience: 3 Evaluierungen ohne Verbesserung
- Min-Delta: 0.001

### Daten-Verfuegbarkeit fuer Curriculum-Fallback (Score 0.62–0.70)

Analyse von `jparacrawl_500k.jsonl`:
- **Datenpunkte mit Score 0.62–0.70: 1.806 Eintraege**
- Das ist eine sehr kleine Menge zusaetzlicher Daten bei der Erweiterung von `strict` (0.70) auf `expanded` (0.62).
- Der Grossteil der Daten liegt offensichtlich ausserhalb dieses Bereichs.

### Status

- Curriculum-Code in `curriculum.py` ist fertig implementiert.
- Integration in `train_hime.py` ist verdrahtet (seit 2026-04-08).
- **Nicht aktiv**: Die aktive `training_config.json` enthaelt keinen `curriculum`-Block. Der Block existiert nur in `training_config_v121_proposed.json` mit Status "proposed".

## Trainings-Logs

### Log-Dateien

**Hauptlogs** (`app/backend/logs/training/`):

| Datei | Groesse | Datum |
|---|---|---|
| `Qwen2.5-32B-Instruct.log` | 71 MB | 2026-04-05 20:34 |
| `Qwen2.5-32B-Instruct_20260405_213007.log` | 1,1 MB | 2026-04-06 02:21 |
| `Qwen2.5-32B-Instruct_20260406_022304.log` | 38 KB | 2026-04-06 03:28 |
| `Qwen2.5-32B-Instruct_20260406_032900.log` | 32 KB | 2026-04-06 04:07 |
| `Qwen2.5-32B-Instruct_20260406_040744.log` | 32 KB | 2026-04-06 04:46 |
| `Qwen2.5-32B-Instruct_20260406_044734.log` | 27 KB | 2026-04-06 05:20 |
| `Qwen2.5-32B-Instruct_20260406_065219.log` | 30 KB | 2026-04-06 08:26 |
| `Qwen2.5-32B-Instruct_20260406_204642.log` | 16 KB | 2026-04-06 20:49 |
| `Qwen2.5-32B-Instruct_20260406_204709.log` | 16 KB | 2026-04-06 21:23 |
| `auto_resume.log` | 620 B | 2026-04-09 23:12 |

### Letzter Trainings-Run

Aus dem Hauptlog (`Qwen2.5-32B-Instruct.log`):
- **Letzter Checkpoint**: `checkpoint-600` (gespeichert 2026-04-05 20:34:10)
- **Letzte Loss-Werte** (bei Step ~600): `loss=0.4649`, `eval_loss=1.0066`
- **VRAM**: 18,7 GB alloc / 33,0 GB reserved
- **Epoch**: 0.05 (sehr frueh in Epoche 1)

Die spaetere Logs (2026-04-06) zeigen kuerzere Runs mit max. 150 Steps (vermutlich Warm-Start Tests).

### Cross-Referenz mit Checkpoints

**Aktuelle Checkpoints** (`modelle/lora/Qwen2.5-32B-Instruct/checkpoint/`):
- 37 Checkpoints von `checkpoint-20` bis `checkpoint-620` (in 20er-Schritten, plus einige 50er-Schritt-Marker)
- **Hoechster Checkpoint**: `checkpoint-620`
- **Legacy-Backup**: `checkpoint-B/checkpoint-12400` (aelterer Run mit anderen Hyperparametern)

**auto_resume.log** zeigt, dass der letzte Resume-Versuch (2026-04-09) auf `checkpoint-620` zeigt.

**Diskrepanz**: Die Logs referenzierten frueher `checkpoint-14400` (aelterer Run, Pfad `C:\Projekte\Hime\`). Nach der Disk-Migration auf `N:\Projekte\NiN\Hime\` wurde offenbar ein Neustart mit frischen Checkpoints ab Step 0 durchgefuehrt. Das alte `checkpoint-12400` ist als Backup unter `checkpoint-B/` archiviert.

## Dry-Run Verfuegbarkeit

**`--dry-run` Flag: NICHT VORHANDEN**

Weder `train_generic.py` noch `train_hime.py` bieten ein `--dry-run` Flag an. Es gibt keine Moeglichkeit, eine Trainingskonfiguration ohne tatsaechliches Training zu validieren.

## Kritische Lücken

### Fehlende Pipeline-v2-Modelle im Trainings-Skript

`train_generic.py` unterstützt nur **v1-Pipeline-Modelle**:
- qwen32b, qwen14b, qwen72b, gemma27b, deepseek

**Nicht unterstützt**, aber für Pipeline v2 benötigt:
| Modell | Stage | Status |
|---|---|---|
| TranslateGemma-12B | Stage 1B | **FEHLT im Skript** |
| Qwen3.5-9B | Stage 1C | **FEHLT im Skript** |
| Qwen3.5-35B-A3B MoE | Stage 3 (Polish) | **FEHLT im Skript** |

### Skript ist nicht modular

`train_generic.py` ist ein monolithisches Skript mit hardcoded `MODEL_CONFIGS`. Es fehlt:
- Modulare Architektur (z.B. separate Config-Dateien pro Modell)
- Dynamisches Laden von Modell-Definitionen
- Unterstützung für verschiedene Frameworks (Unsloth vs. Transformers vs. GGUF-basiert)

Für Pipeline v2 müsste das Trainings-System grundlegend überarbeitet werden, um die neuen Modelle (insb. TranslateGemma mit Transformers-Safetensors und Qwen3.5 mit Unsloth) zu unterstützen.

### Hybrides Trainingssystem mit dynamisch erweiterbaren Daten fehlt

Das geplante hybride Trainingssystem ist **nicht implementiert**. Es fehlt:
- **Dynamische Datenquellen-Verwaltung** — Trainingsdaten sind statische JSONL-Dateien. Es gibt kein System, das neue Datenquellen (z.B. aus dem Flywheel, aus User-Korrekturen, aus neuen EPUB-Alignments) automatisch oder on-demand in den Trainings-Pool aufnimmt.
- **Hybrid-Architektur** — Kein Mechanismus, der verschiedene Datentypen (Parallel-Korpora, monolinguale Daten, User-Feedback, synthetische Daten) gewichtet kombiniert und dynamisch erweitert.
- **Daten-Registry** — Keine zentrale Stelle, die alle verfügbaren Trainingsquellen mit Metadaten (Qualität, Größe, Domäne, Aktualität) verwaltet und für neue Trainingsläufe zusammenstellt.
- **Inkrementelles Training** — Kein Support für das schrittweise Einbringen neuer Daten in bestehende Adapter ohne vollständigen Neustart.

Das aktuelle System kennt nur den festen Pfad `hime_training_all.jsonl` (oder per `--data-file` einen alternativen Pfad). Curriculum-Learning in `train_hime.py` filtert zwar nach Score-Schwellenwerten, ist aber ebenfalls auf die statische `jparacrawl_500k.jsonl` fixiert.

---

## Weitere Offene Punkte

1. **Kein `--dry-run` Flag** — Es fehlt die Moeglichkeit, Trainings-Setup (Datenladung, Modell-Init, Konfiguration) ohne tatsaechliches Training zu pruefen. Empfehlung: Implementieren.

2. **Curriculum nicht aktiviert** — Der Curriculum-Code ist implementiert und in `train_hime.py` verdrahtet, aber die aktive `training_config.json` enthaelt keinen `curriculum`-Block. Die vorgeschlagene Config (`training_config_v121_proposed.json`) muss noch gemergt werden.

3. **Sehr wenig Curriculum-Fallback-Daten** — Nur 1.806 Eintraege mit Score 0.62–0.70 in jparacrawl. Der Sprung von Tier `strict` (>=0.70) zu `expanded` (>=0.62) bringt minimal zusaetzliche Daten. Der Hauptgewinn kaeme erst beim Sprung zu `loose` (>=0.55).

4. **Aktueller Trainingsstand unklar** — Letzter dokumentierter Checkpoint ist `checkpoint-620` (Step 620, Loss ~0.46). Der letzte auto_resume-Eintrag (2026-04-09) zeigt ebenfalls auf `checkpoint-620`. Kein neuerer Trainings-Log vorhanden — es scheint seit 2026-04-06 kein Training mehr gelaufen zu sein.

5. **Hohe eval_loss** — Bei Step 500 liegt `eval_loss=1.0066` deutlich ueber dem `target_loss=0.4`. Die `train_loss` (~0.46) ist nahe am Ziel, aber die Generalisierung (eval_loss) zeigt Overfitting-Tendenzen.

6. **Letzter Log (20260406_204709) abgebrochen** — Dieser Run endete nach nur 1 von 150 Steps bei der Tokenisierung. Der Log zeigt 33:51 pro Step — moeglicherweise extreme Verlangsamung oder Abbruch.

7. **Literary-Dateien fuer Curriculum vorhanden** — `shuukura_jp.jsonl` und `seiyuu_radio_all_jp.jsonl` existieren, sind aber nicht identisch mit `shuukura_wn_aligned.jsonl` (das in `hime_training_all.jsonl` enthalten ist). Die Curriculum-Config referenziert die `_jp`-Varianten.
