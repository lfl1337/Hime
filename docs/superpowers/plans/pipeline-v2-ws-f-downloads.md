# Pipeline v2 — WS-F: Modell-Downloads + Inventory Report

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download alle neuen Pipeline-v2-Modelle und erstelle ein Inventory-Report-Script das lokale Modelle, Checkpoints und Speicherverbrauch dokumentiert — ohne automatisch zu löschen.

**Architecture:** Zwei unabhängige Scripts: `download_models_v2.py` (Download-Helper mit Resume-Support) und `model_inventory_report.py` (Read-only Bericht). Beide via `uv run scripts/...`.

**Tech Stack:** Python stdlib + `huggingface_hub`, `subprocess` (für `ollama list`), `pathlib`

---

## File Structure

- Create: `scripts/download_models_v2.py`
- Create: `scripts/model_inventory_report.py`
- Modify: `app/backend/pyproject.toml` — optional dep group `[downloads]`
- Create: `app/backend/tests/test_model_inventory.py`

---

### Task 1: Download-Script Grundstruktur + Resume-Logik

**Files:**
- Create: `scripts/download_models_v2.py`

- [ ] **Step 1: Script anlegen mit Modell-Tabelle**

```python
#!/usr/bin/env python3
"""Download all Pipeline v2 models from HuggingFace.

Usage:
    uv run scripts/download_models_v2.py
    uv run scripts/download_models_v2.py --model translategemma-12b
    uv run scripts/download_models_v2.py --list
    uv run scripts/download_models_v2.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT") or Path(__file__).resolve().parent.parent)
MODELS_DIR = Path(os.environ.get("HIME_MODELS_DIR") or PROJECT_ROOT / "modelle")

# ---------------------------------------------------------------------------
# Model registry — all v2 pipeline models
# ---------------------------------------------------------------------------
MODELS: list[dict] = [
    {
        "key": "translategemma-12b",
        "hf_id": "google/translategemma-12b-it",
        "description": "Stage 1B — MT-spezialisierter Draft",
        "size_gb": 24,
        "method": "transformers",
        "local_dir": MODELS_DIR / "translategemma-12b",
    },
    {
        "key": "translategemma-27b",
        "hf_id": "google/translategemma-27b-it",
        "description": "Stage 2 — Merger",
        "size_gb": 54,
        "method": "transformers",
        "local_dir": MODELS_DIR / "translategemma-27b",
    },
    {
        "key": "qwen35-9b",
        "hf_id": "Qwen/Qwen3-9B",  # NOTE: verify on HF — spec says Qwen3.5-9B
        "description": "Stage 1C — Diversitäts-Draft",
        "size_gb": 18,
        "method": "unsloth",
        "local_dir": MODELS_DIR / "qwen35-9b",
    },
    {
        "key": "qwen35-35b",
        "hf_id": "Qwen/Qwen3-30B-A3B",  # NOTE: verify on HF — spec says Qwen3.5-35B-A3B
        "description": "Stage 3 — Polish",
        "size_gb": 20,
        "method": "unsloth",
        "local_dir": MODELS_DIR / "qwen35-35b",
    },
    {
        "key": "qwen35-2b",
        "hf_id": "Qwen/Qwen3-2B",  # NOTE: verify on HF — spec says Qwen3.5-2B
        "description": "Stage 4 — Reader Panel (15 Personas)",
        "size_gb": 1.2,
        "method": "unsloth",
        "local_dir": MODELS_DIR / "qwen35-2b",
    },
    {
        "key": "gemma4-e4b",
        "hf_id": "unsloth/gemma-4-E4B-it-GGUF",
        "description": "Stage 1D — Diversitäts-Draft (inference-only)",
        "size_gb": 3,
        "method": "gguf",
        "local_dir": MODELS_DIR / "gemma4-e4b",
        "include_pattern": "*.gguf",
    },
    {
        "key": "lfm2-24b",
        "hf_id": "LiquidAI/LFM2-24B-A2B",
        "description": "Stage 4 — Aggregator (Transformers ≥5.0.0, kein Unsloth)",
        "size_gb": 14,
        "method": "transformers",
        "local_dir": MODELS_DIR / "lfm2-24b",
    },
    {
        "key": "lfm2-2b",
        "hf_id": "LiquidAI/LFM2-2.6B",
        "description": "Vault Organizer",
        "size_gb": 2.6,
        "method": "transformers",
        "local_dir": MODELS_DIR / "lfm2-2b",
    },
]
```

- [ ] **Step 2: Download-Funktion implementieren**

```python
def _is_downloaded(model: dict) -> bool:
    """Check if model already fully downloaded (config.json present)."""
    local = model["local_dir"]
    if model["method"] == "gguf":
        return any(local.glob("*.gguf")) if local.exists() else False
    return (local / "config.json").exists()


def download_model(model: dict, dry_run: bool = False) -> None:
    """Download a single model from HuggingFace."""
    from huggingface_hub import snapshot_download

    key = model["key"]
    hf_id = model["hf_id"]
    local_dir = model["local_dir"]

    if _is_downloaded(model):
        print(f"  [SKIP] {key} — bereits vorhanden in {local_dir}")
        return

    print(f"  [DOWN] {key} ({model['size_gb']}GB) — {hf_id}")
    if dry_run:
        print(f"         → würde nach {local_dir} laden")
        return

    local_dir.mkdir(parents=True, exist_ok=True)
    kwargs: dict = {
        "repo_id": hf_id,
        "local_dir": str(local_dir),
        "resume_download": True,
    }
    if "include_pattern" in model:
        kwargs["allow_patterns"] = [model["include_pattern"]]

    snapshot_download(**kwargs)
    print(f"  [OK]   {key} — fertig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Pipeline v2 models")
    parser.add_argument("--model", help="Nur ein spezifisches Modell laden (key)")
    parser.add_argument("--list", action="store_true", help="Verfügbare Modelle auflisten")
    parser.add_argument("--dry-run", action="store_true", help="Nur zeigen was geladen würde")
    args = parser.parse_args()

    if args.list:
        print("\nVerfügbare Modelle:")
        for m in MODELS:
            status = "[OK]" if _is_downloaded(m) else "[--]"
            print(f"  {status} {m['key']:20s} {m['size_gb']:5.1f}GB  {m['description']}")
        return

    targets = [m for m in MODELS if m["key"] == args.model] if args.model else MODELS
    if args.model and not targets:
        print(f"Unbekanntes Modell: {args.model}")
        print("Verfügbare Keys:", [m["key"] for m in MODELS])
        sys.exit(1)

    total_gb = sum(m["size_gb"] for m in targets if not _is_downloaded(m))
    print(f"\nLade {len(targets)} Modell(e) — ~{total_gb:.1f}GB noch nicht vorhanden\n")
    for model in targets:
        download_model(model, dry_run=args.dry_run)
    print("\nFertig.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Script ausführbar machen + dry-run testen**

```bash
cd N:\Projekte\NiN\Hime
uv run scripts/download_models_v2.py --list
uv run scripts/download_models_v2.py --dry-run
```

Expected output: Liste aller 8 Modelle mit [--] Status, dann dry-run zeigt was geladen würde ohne tatsächlich zu laden.

- [ ] **Step 4: Commit**

```bash
git add scripts/download_models_v2.py
git commit -m "feat(scripts): add download_models_v2.py with resume support"
```

---

### Task 2: Inventory Report Script

**Files:**
- Create: `scripts/model_inventory_report.py`
- Create: `app/backend/tests/test_model_inventory.py`

- [ ] **Step 1: Failing test schreiben**

```python
# app/backend/tests/test_model_inventory.py
"""Tests for model_inventory_report.py helper functions."""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# We import the helper functions directly — not the main() entry point
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent / "scripts"))
import model_inventory_report as inv


def test_format_size():
    assert inv.format_size(0) == "0 B"
    assert inv.format_size(1024) == "1.0 KB"
    assert inv.format_size(1024 ** 3) == "1.0 GB"
    assert inv.format_size(1024 ** 3 * 32) == "32.0 GB"


def test_scan_dir_empty(tmp_path):
    result = inv.scan_dir(tmp_path / "nonexistent")
    assert result == {"exists": False, "total_bytes": 0, "items": []}


def test_scan_dir_with_files(tmp_path):
    (tmp_path / "model.bin").write_bytes(b"x" * 1024)
    (tmp_path / "config.json").write_bytes(b"{}")
    result = inv.scan_dir(tmp_path)
    assert result["exists"] is True
    assert result["total_bytes"] == 1026
    assert len(result["items"]) == 2


def test_report_contains_sections(tmp_path, monkeypatch):
    monkeypatch.setattr(inv, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(inv, "MODELS_DIR", tmp_path / "modelle")
    monkeypatch.setattr(inv, "HF_CACHE", tmp_path / "hf_cache")
    (tmp_path / "modelle").mkdir(parents=True)
    (tmp_path / "hf_cache").mkdir(parents=True)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="NAME\ngemma:latest 3.2 GB\n")
        report = inv.build_report()

    assert "## Ollama Modelle" in report
    assert "## HuggingFace Cache" in report
    assert "## Qwen2.5-32B Checkpoints" in report
    assert "## Gesamtverbrauch" in report
```

- [ ] **Step 2: Test ausführen — sicherstellen dass es scheitert**

```bash
cd N:\Projekte\NiN\Hime\app\backend
uv run pytest tests/test_model_inventory.py -v
```

Expected: ImportError oder ModuleNotFoundError (script existiert noch nicht).

- [ ] **Step 3: Inventory Script implementieren**

```python
#!/usr/bin/env python3
"""Read-only inventory report for all local models.

Produces a Markdown report — does NOT delete anything.
Luca decides what to clean up.

Usage:
    uv run scripts/model_inventory_report.py
    uv run scripts/model_inventory_report.py --output report.md
"""
from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("HIME_PROJECT_ROOT") or Path(__file__).resolve().parent.parent)
MODELS_DIR = Path(os.environ.get("HIME_MODELS_DIR") or PROJECT_ROOT / "modelle")
HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"
LORA_DIR = MODELS_DIR / "lora" / "Qwen2.5-32B-Instruct"


def format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


def scan_dir(path: Path) -> dict:
    if not path.exists():
        return {"exists": False, "total_bytes": 0, "items": []}
    items = []
    total = 0
    for p in sorted(path.iterdir()):
        if p.is_file():
            size = p.stat().st_size
            total += size
            items.append({"name": p.name, "bytes": size})
        elif p.is_dir():
            sub = scan_dir(p)
            total += sub["total_bytes"]
            items.append({"name": p.name + "/", "bytes": sub["total_bytes"], "is_dir": True})
    return {"exists": True, "total_bytes": total, "items": items}


def _ollama_list() -> str:
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        return result.stdout if result.returncode == 0 else f"(Fehler: {result.stderr.strip()})"
    except FileNotFoundError:
        return "(ollama nicht gefunden)"
    except subprocess.TimeoutExpired:
        return "(Timeout)"


def build_report() -> str:
    lines: list[str] = [
        f"# Hime Model Inventory Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "> **Read-only** — keine automatischen Löschungen. Luca entscheidet.",
        "",
    ]

    # --- Ollama ---
    lines += ["## Ollama Modelle", "", "```", _ollama_list(), "```", ""]

    # --- HuggingFace Cache ---
    lines += ["## HuggingFace Cache", ""]
    hf = scan_dir(HF_CACHE)
    if not hf["exists"]:
        lines.append(f"Cache nicht gefunden: `{HF_CACHE}`")
    else:
        lines.append(f"Pfad: `{HF_CACHE}`  ")
        lines.append(f"Gesamt: **{format_size(hf['total_bytes'])}**")
        lines.append("")
        lines.append("| Verzeichnis | Größe |")
        lines.append("|---|---|")
        for item in hf["items"]:
            lines.append(f"| `{item['name']}` | {format_size(item['bytes'])} |")
    lines.append("")

    # --- Qwen2.5-32B Checkpoints ---
    lines += ["## Qwen2.5-32B Checkpoints", ""]
    if not LORA_DIR.exists():
        lines.append(f"Verzeichnis nicht gefunden: `{LORA_DIR}`")
    else:
        for subdir in sorted(LORA_DIR.iterdir()):
            if subdir.is_dir():
                s = scan_dir(subdir)
                lines.append(f"- `{subdir.name}/` — {format_size(s['total_bytes'])}")
        adapter = scan_dir(LORA_DIR / "adapter")
        lines.append(f"- `adapter/` — {format_size(adapter['total_bytes'])} (aktiv)")
    lines.append("")

    # --- lokale Modelle in MODELS_DIR ---
    lines += ["## Lokale Modelle (modelle/)", ""]
    models_scan = scan_dir(MODELS_DIR)
    if not models_scan["exists"]:
        lines.append(f"Verzeichnis nicht gefunden: `{MODELS_DIR}`")
    else:
        lines.append(f"Gesamt: **{format_size(models_scan['total_bytes'])}**")
        lines.append("")
        lines.append("| Verzeichnis | Größe |")
        lines.append("|---|---|")
        for item in models_scan["items"]:
            lines.append(f"| `{item['name']}` | {format_size(item['bytes'])} |")
    lines.append("")

    # --- Gesamtverbrauch ---
    total = models_scan["total_bytes"] + hf["total_bytes"]
    lines += [
        "## Gesamtverbrauch",
        "",
        f"| Quelle | Größe |",
        f"|---|---|",
        f"| HuggingFace Cache | {format_size(hf['total_bytes'])} |",
        f"| Lokale Modelle (modelle/) | {format_size(models_scan['total_bytes'])} |",
        f"| **Gesamt** | **{format_size(total)}** |",
        "",
    ]

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Model inventory report")
    parser.add_argument("--output", help="Output-Datei (default: stdout)")
    args = parser.parse_args()

    report = build_report()

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report gespeichert: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Tests ausführen — grün**

```bash
cd N:\Projekte\NiN\Hime\app\backend
uv run pytest tests/test_model_inventory.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Script manuell testen**

```bash
cd N:\Projekte\NiN\Hime
uv run scripts/model_inventory_report.py
```

Expected: Vollständiger Markdown-Report in stdout, alle Sektionen vorhanden, kein Crash.

- [ ] **Step 6: Commit**

```bash
git add scripts/model_inventory_report.py app/backend/tests/test_model_inventory.py
git commit -m "feat(scripts): add model_inventory_report.py (read-only disk audit)"
```

---

### Task 3: pyproject.toml optional dep group

**Files:**
- Modify: `app/backend/pyproject.toml`

- [ ] **Step 1: Optional dep group hinzufügen**

In `pyproject.toml` unter `[project.optional-dependencies]` (oder anlegen falls nicht vorhanden):

```toml
[project.optional-dependencies]
downloads = [
    "huggingface_hub>=0.24.0",
]
```

- [ ] **Step 2: Verify**

```bash
cd N:\Projekte\NiN\Hime\app\backend
uv pip install -e ".[downloads]" --dry-run
```

Expected: zeigt `huggingface_hub` als zu installierendes Package (oder bereits vorhanden).

- [ ] **Step 3: Commit**

```bash
git add app/backend/pyproject.toml
git commit -m "chore(deps): add optional [downloads] group for model download scripts"
```
