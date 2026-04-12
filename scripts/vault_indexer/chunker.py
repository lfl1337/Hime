# scripts/vault_indexer/chunker.py
"""Liest .md-Dateien aus dem Hime-Vault und zerlegt sie in indexierbare Chunks."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VaultChunk:
    file_path: str       # relativ zu VAULT_PATH
    chunk_index: int
    text: str            # für Embedding
    title: str = ""
    type: str = "note"
    project: str = ""
    tags: list[str] = field(default_factory=list)


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_YAML_FIELD_RE  = re.compile(r'^(\w+):\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
_YAML_LIST_RE   = re.compile(r'^\s+-\s+"?([^"\n]+)"?', re.MULTILINE)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extrahiert YAML-Frontmatter und gibt (meta, body) zurück."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    yaml_block = m.group(1)
    body = text[m.end():]
    meta: dict = {}
    for key, val in _YAML_FIELD_RE.findall(yaml_block):
        meta[key.strip()] = val.strip()
    # Tags als Liste parsen
    if "tags:" in yaml_block:
        tags_section = yaml_block.split("tags:")[1].split("\n\n")[0]
        meta["tags"] = _YAML_LIST_RE.findall(tags_section)
    return meta, body


def _split_body(body: str, max_chars: int = 1500) -> list[str]:
    """
    Teilt den Body in Chunks auf. Paragraphen-Grenzen (doppeltes Newline)
    werden bevorzugt. Paragraphen über max_chars werden hart gesplittet.
    """
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", body) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = (current + "\n\n" + para).strip() if current else para
    if current:
        chunks.append(current.strip())
    return chunks or [""]


def file_to_chunks(path: Path, vault_root: Path) -> list[VaultChunk]:
    """Liest eine .md-Datei und gibt eine Liste von VaultChunks zurück."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []

    meta, body = _parse_frontmatter(text)
    rel_path = str(path.relative_to(vault_root))

    title   = meta.get("name", meta.get("title", path.stem))
    vtype   = meta.get("type", "note")
    project = meta.get("project", "")
    tags    = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    raw_chunks = _split_body(body)
    return [
        VaultChunk(
            file_path=rel_path,
            chunk_index=i,
            text=f"{title}\n\n{chunk}",
            title=title,
            type=vtype,
            project=project,
            tags=tags,
        )
        for i, chunk in enumerate(raw_chunks)
        if chunk.strip()
    ]
