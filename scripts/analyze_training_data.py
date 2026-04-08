"""
Hime - Trainingsdaten Analyse Script
Analysiert alle JP/EN Paare via Qwen2.5-72B (LM Studio Local Server)
mit Checkpoint Support - jederzeit stoppen und weitermachen.

Verwendung:
    python analyze_training_data.py

Stoppen:  Ctrl+C  → speichert Checkpoint automatisch
Weitermachen: einfach nochmal starten
"""

import json, time, os, random
from pathlib import Path
from tqdm import tqdm
import requests

# ─── Konfiguration ────────────────────────────────────────────
PROJECT_ROOT   = Path(os.environ.get("HIME_PROJECT_ROOT") or Path(__file__).resolve().parent.parent)
TRAINING_DIR   = PROJECT_ROOT / "data" / "training"
ANALYSIS_DIR   = PROJECT_ROOT / "data" / "analysis"
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

LM_STUDIO_URL  = "http://localhost:1234/v1/chat/completions"
MODEL          = "qwen2.5-32b-instruct"
BATCH_SIZE     = 10       # Paare pro Request
MIN_SCORE      = 6        # Paare unter diesem Score werden gefiltert
REQUEST_DELAY  = 0.2      # Sekunden zwischen Requests

# Input Dateien
INPUT_FILES = [
    TRAINING_DIR / "jparacrawl_500k.jsonl",
    TRAINING_DIR / "shuukura_wn_aligned.jsonl",
]

# Output Dateien
CHECKPOINT_FILE = ANALYSIS_DIR / "checkpoint.json"
RESULTS_FILE    = ANALYSIS_DIR / "analysis_results.jsonl"
FILTERED_FILE   = TRAINING_DIR / "hime_training_filtered.jsonl"
# ──────────────────────────────────────────────────────────────


SYSTEM_PROMPT = """You are a Japanese-English translation quality evaluator specializing in light novels and yuri fiction.
Your task is to evaluate Japanese-English translation pairs and score them.

For each pair, evaluate:
1. Translation accuracy (does EN match JP meaning?)
2. Fluency (is the English natural and readable?)
3. Style preservation (does it sound like a light novel?)
4. Completeness (is anything missing?)

Respond ONLY with a JSON array. No other text.
Example:
[
  {"id": 0, "score": 8, "reason": "Accurate and fluent"},
  {"id": 1, "score": 3, "reason": "Missing key phrases"}
]
Scores: 1-10 (1=terrible, 6=acceptable, 8=good, 10=perfect)"""


def load_checkpoint() -> dict:
    """Lädt Checkpoint falls vorhanden."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return {"processed_files": {}, "total_processed": 0, "total_kept": 0}


def save_checkpoint(checkpoint: dict):
    """Speichert aktuellen Fortschritt."""
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f, indent=2)


def load_all_pairs() -> list:
    """Lädt alle Trainingspaare aus allen Input Dateien."""
    all_pairs = []
    for filepath in INPUT_FILES:
        if not filepath.exists():
            print(f"[!] Nicht gefunden: {filepath.name}")
            continue
        count = 0
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if (entry.get("input") and len(entry["input"]) > 50 and
                    entry.get("output") and len(entry["output"]) > 50):
                    entry["_source_file"] = filepath.name
                    all_pairs.append(entry)
                    count += 1
        print(f"[OK] {filepath.name}: {count:,} Paare geladen")
    return all_pairs


def analyze_batch(batch: list, batch_idx: int) -> list:
    """
    Schickt einen Batch an Qwen2.5-72B zur Analyse.
    Gibt Liste von Scores zurück.
    """
    # Prompt bauen
    pairs_text = ""
    for i, pair in enumerate(batch):
        jp = pair["input"][:500]   # Auf 500 Zeichen kürzen für Speed
        en = pair["output"][:500]
        pairs_text += f'\nPair {i}:\nJP: {jp}\nEN: {en}\n'

    user_message = f"Evaluate these {len(batch)} translation pairs:\n{pairs_text}"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    try:
        resp = requests.post(LM_STUDIO_URL, json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()

        # JSON aus Antwort extrahieren
        # Manchmal kommt es mit ```json ... ``` verpackt
        content = content.replace("```json", "").replace("```", "").strip()

        scores = json.loads(content)
        return scores

    except json.JSONDecodeError:
        # Wenn JSON Parsing fehlschlägt → alle mit Score 7 markieren (neutral)
        print(f"[!] JSON Parse Fehler bei Batch {batch_idx}, verwende Score 7")
        return [{"id": i, "score": 7, "reason": "parse_error"} for i in range(len(batch))]
    except Exception as e:
        print(f"[!] Fehler bei Batch {batch_idx}: {e}")
        return [{"id": i, "score": 7, "reason": "request_error"} for i in range(len(batch))]


def run_analysis():
    """Hauptfunktion - analysiert alle Paare mit Checkpoint Support."""
    print("=" * 60)
    print("  Hime - Trainingsdaten Analyse")
    print(f"  Modell: {MODEL}")
    print(f"  Min Score: {MIN_SCORE}/10")
    print("=" * 60)

    # Checkpoint laden
    checkpoint = load_checkpoint()
    already_processed = checkpoint.get("total_processed", 0)

    if already_processed > 0:
        print(f"\n[i] Checkpoint gefunden: {already_processed:,} Paare bereits verarbeitet")
        print(f"[i] Mache weiter wo aufgehört ...")

    # Alle Paare laden
    print("\n[..] Lade Trainingsdaten ...")
    all_pairs = load_all_pairs()
    print(f"[OK] Gesamt: {len(all_pairs):,} Paare")

    # Bereits verarbeitete überspringen
    pairs_to_process = all_pairs[already_processed:]
    print(f"[i]  Noch zu verarbeiten: {len(pairs_to_process):,} Paare")

    if not pairs_to_process:
        print("\n[OK] Alle Paare bereits analysiert!")
        create_filtered_dataset(checkpoint)
        return

    # Results File öffnen (append mode für Checkpoint Support)
    results_file = open(RESULTS_FILE, 'a', encoding='utf-8')

    kept = checkpoint.get("total_kept", 0)
    processed = already_processed

    # Geschwindigkeitsschätzung
    total_batches = len(pairs_to_process) // BATCH_SIZE
    print(f"\n[i] Batches: {total_batches:,} (je {BATCH_SIZE} Paare)")
    print(f"[i] Geschätzte Zeit: {total_batches * 3 / 3600:.1f} Stunden")
    print(f"\n[i] Stoppen: Ctrl+C (Checkpoint wird gespeichert)\n")

    try:
        pbar = tqdm(
            range(0, len(pairs_to_process), BATCH_SIZE),
            desc="Analyse",
            unit="batch"
        )

        for batch_start in pbar:
            batch = pairs_to_process[batch_start:batch_start + BATCH_SIZE]
            if not batch:
                break

            # Batch analysieren
            scores = analyze_batch(batch, batch_start // BATCH_SIZE)

            # Ergebnisse speichern
            score_map = {s["id"]: s for s in scores}

            for i, pair in enumerate(batch):
                score_info = score_map.get(i, {"score": 7, "reason": "missing"})
                try:
                    score = int(score_info.get("score", 7))
                except (ValueError, TypeError):
                    score = 7

                result = {
                    **pair,
                    "_score": score,
                    "_reason": score_info.get("reason", ""),
                    "_keep": score >= MIN_SCORE
                }

                results_file.write(json.dumps(result, ensure_ascii=False) + '\n')

                if score >= MIN_SCORE:
                    kept += 1

            processed += len(batch)

            # Checkpoint alle 1000 Paare speichern
            if processed % 1000 == 0:
                results_file.flush()
                checkpoint["total_processed"] = processed
                checkpoint["total_kept"] = kept
                save_checkpoint(checkpoint)

            # Fortschritt anzeigen
            pbar.set_postfix({
                "behalten": f"{kept:,}",
                "verworfen": f"{processed - already_processed - kept:,}",
                "rate": f"{kept/(processed-already_processed)*100:.0f}%"
            })

            time.sleep(REQUEST_DELAY)

    except KeyboardInterrupt:
        print(f"\n\n[i] Gestoppt! Speichere Checkpoint ...")

    finally:
        results_file.close()
        checkpoint["total_processed"] = processed
        checkpoint["total_kept"] = kept
        save_checkpoint(checkpoint)
        print(f"[OK] Checkpoint gespeichert: {processed:,} verarbeitet, {kept:,} behalten")

    # Finales Dataset erstellen wenn alles durch
    if processed >= len(all_pairs):
        create_filtered_dataset(checkpoint)


def create_filtered_dataset(checkpoint: dict):
    """Erstellt das finale gefilterte Dataset aus den Analyse-Ergebnissen."""
    print(f"\n[..] Erstelle gefiltertes Dataset ...")

    if not RESULTS_FILE.exists():
        print("[!] Keine Ergebnisse gefunden!")
        return

    kept_entries = []
    total = 0
    kept = 0

    with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            total += 1
            if entry.get("_keep", False):
                # Analyse-Metadaten entfernen für Training
                clean = {k: v for k, v in entry.items() if not k.startswith("_")}
                kept_entries.append(clean)
                kept += 1

    with open(FILTERED_FILE, 'w', encoding='utf-8') as f:
        for entry in kept_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f"\n{'='*60}")
    print(f"  Analyse abgeschlossen!")
    print(f"  Gesamt analysiert:  {total:,}")
    print(f"  Behalten (≥{MIN_SCORE}/10):  {kept:,} ({kept/total*100:.1f}%)")
    print(f"  Verworfen:          {total-kept:,}")
    print(f"  Output: {FILTERED_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_analysis()
