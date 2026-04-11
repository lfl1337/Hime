"""
hime_data.py — training data registry CLI.

Commands:
  register <path> --id <id> --kind <kind> --source <name> [--quality-field <field>]
  list
  export [--min-score <float>] --out <path>

Registry: data/registry.jsonl at the repo root.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _registry_path(repo_root: Path) -> Path:
    return repo_root / "data" / "registry.jsonl"


def _load_registry(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _save_registry(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
        encoding="utf-8",
    )


def _measure_jsonl(file_path: Path, quality_field: str | None) -> tuple[int, list[float]]:
    """Return (line_count, [min_score, max_score]) for a JSONL file."""
    count = 0
    min_s: float | None = None
    max_s: float | None = None
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            count += 1
            if quality_field:
                try:
                    obj = json.loads(line)
                    val = obj.get(quality_field)
                    if isinstance(val, (int, float)):
                        v = float(val)
                        if min_s is None or v < min_s:
                            min_s = v
                        if max_s is None or v > max_s:
                            max_s = v
                except Exception:
                    continue
    score_range: list[float] = []
    if min_s is not None and max_s is not None:
        score_range = [round(min_s, 6), round(max_s, 6)]
    return count, score_range


def cmd_register(args: argparse.Namespace, repo_root: Path) -> int:
    file_path = (repo_root / args.path).resolve()
    if not file_path.exists():
        print(f"error: file not found: {file_path}", file=sys.stderr)
        return 2

    registry = _registry_path(repo_root)
    entries = _load_registry(registry)
    if any(e["id"] == args.id for e in entries):
        print(f"error: id already exists in registry: {args.id}", file=sys.stderr)
        return 3

    count, score_range = _measure_jsonl(file_path, args.quality_field or None)
    entry = {
        "id": args.id,
        "path": str(file_path.relative_to(repo_root)).replace("\\", "/"),
        "kind": args.kind,
        "source": args.source,
        "lines": count,
        "quality_field": args.quality_field or "",
        "quality_range": score_range,
        "added": datetime.now(timezone.utc).isoformat(),
        "notes": args.notes or "",
    }
    entries.append(entry)
    _save_registry(registry, entries)
    print(f"[OK] registered {args.id}: {count} lines, score_range={score_range}")
    return 0


def cmd_list(args: argparse.Namespace, repo_root: Path) -> int:
    registry = _registry_path(repo_root)
    entries = _load_registry(registry)
    if not entries:
        print("(empty)")
        return 0
    print(f"{'id':<32} {'kind':<22} {'lines':>10}  path")
    print("-" * 80)
    for e in entries:
        print(f"{e['id']:<32} {e['kind']:<22} {e['lines']:>10}  {e['path']}")
    return 0


def cmd_export(args: argparse.Namespace, repo_root: Path) -> int:
    registry = _registry_path(repo_root)
    entries = _load_registry(registry)
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with out_path.open("w", encoding="utf-8") as out_f:
        for entry in entries:
            src = (repo_root / entry["path"]).resolve()
            if not src.exists():
                print(f"[warn] source missing, skipped: {src}", file=sys.stderr)
                continue
            qf = entry.get("quality_field") or ""
            with src.open("r", encoding="utf-8") as in_f:
                for line in in_f:
                    line = line.rstrip("\n")
                    if not line.strip():
                        continue
                    if args.min_score is not None and qf:
                        try:
                            obj = json.loads(line)
                            val = obj.get(qf)
                            if not isinstance(val, (int, float)) or val < args.min_score:
                                continue
                        except Exception:
                            continue
                    out_f.write(line + "\n")
                    written += 1
    print(f"[OK] exported {written} lines -> {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hime-data")
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("register", help="Register a JSONL training file")
    reg.add_argument("path", help="repo-relative path to JSONL file")
    reg.add_argument("--id", required=True)
    reg.add_argument("--kind", required=True,
                     choices=["parallel_corpus", "curated_lightnovel", "literary_aligned", "synthetic"])
    reg.add_argument("--source", required=True)
    reg.add_argument("--quality-field", default="")
    reg.add_argument("--notes", default="")

    sub.add_parser("list", help="List registered training files")

    exp = sub.add_parser("export", help="Export filtered JSONL")
    exp.add_argument("--min-score", type=float, default=None)
    exp.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    # repo_root: prefer HIME_PROJECT_ROOT env var; fall back to current working directory
    repo_root = Path(
        os.environ.get("HIME_PROJECT_ROOT", "")
        or str(Path.cwd())
    )

    if args.command == "register":
        return cmd_register(args, repo_root)
    if args.command == "list":
        return cmd_list(args, repo_root)
    if args.command == "export":
        return cmd_export(args, repo_root)
    return 1


if __name__ == "__main__":
    sys.exit(main())
