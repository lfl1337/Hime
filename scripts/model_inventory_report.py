#!/usr/bin/env python3
"""Read-only inventory report for all local models.

Produces a Markdown report -- does NOT delete anything.

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
        f"# Hime Model Inventory Report -- {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "> **Read-only** -- keine automatischen Loeschungen. Luca entscheidet.",
        "",
    ]

    lines += ["## Ollama Modelle", "", "```", _ollama_list(), "```", ""]

    lines += ["## HuggingFace Cache", ""]
    hf = scan_dir(HF_CACHE)
    if not hf["exists"]:
        lines.append(f"Cache nicht gefunden: `{HF_CACHE}`")
    else:
        lines.append(f"Pfad: `{HF_CACHE}`  ")
        lines.append(f"Gesamt: **{format_size(hf['total_bytes'])}**")
        lines.append("")
        lines.append("| Verzeichnis | Groesse |")
        lines.append("|---|---|")
        for item in hf["items"]:
            lines.append(f"| `{item['name']}` | {format_size(item['bytes'])} |")
    lines.append("")

    lines += ["## Qwen2.5-32B Checkpoints", ""]
    if not LORA_DIR.exists():
        lines.append(f"Verzeichnis nicht gefunden: `{LORA_DIR}`")
    else:
        for subdir in sorted(LORA_DIR.iterdir()):
            if subdir.is_dir():
                s = scan_dir(subdir)
                lines.append(f"- `{subdir.name}/` -- {format_size(s['total_bytes'])}")
        adapter_path = LORA_DIR / "adapter"
        if adapter_path.exists():
            adapter = scan_dir(adapter_path)
            lines.append(f"- `adapter/` -- {format_size(adapter['total_bytes'])} (aktiv)")
    lines.append("")

    lines += ["## Lokale Modelle (modelle/)", ""]
    models_scan = scan_dir(MODELS_DIR)
    if not models_scan["exists"]:
        lines.append(f"Verzeichnis nicht gefunden: `{MODELS_DIR}`")
    else:
        lines.append(f"Gesamt: **{format_size(models_scan['total_bytes'])}**")
        lines.append("")
        lines.append("| Verzeichnis | Groesse |")
        lines.append("|---|---|")
        for item in models_scan["items"]:
            lines.append(f"| `{item['name']}` | {format_size(item['bytes'])} |")
    lines.append("")

    total = models_scan["total_bytes"] + hf["total_bytes"]
    lines += [
        "## Gesamtverbrauch",
        "",
        "| Quelle | Groesse |",
        "|---|---|",
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
