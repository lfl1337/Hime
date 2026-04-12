"""
Vault Organizer — standalone weekly Obsidian vault analysis script.

Run manually:
    uv run scripts/vault_organizer.py

Or via Windows Task Scheduler (weekly, Sunday 10:00):
    Program:   uv
    Arguments: run N:\\Projekte\\NiN\\Hime\\scripts\\vault_organizer.py

Output: {VAULT_PATH}/_Reports/vault_report_YYYY-MM-DD.md
No automatic changes — report only, user decides.
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

# ── Configuration (edit these before running) ─────────────────────────────────

VAULT_PATH = Path(os.environ.get("HIME_VAULT_PATH", r"C:\Users\lfLaw\ObsidianVault"))
REPORT_PATH = "_Reports"                               # relative to VAULT_PATH
MIN_SIMILARITY = 0.75                                  # cosine threshold for clusters
MAX_SUMMARY_LENGTH = 100                               # words per frontmatter summary
USE_MODEL = True                                       # False = structural pass only

# ── Constants ─────────────────────────────────────────────────────────────────

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]")
TAG_INLINE_RE = re.compile(r"(?:^|\s)#([\w/-]+)", re.MULTILINE)
SPECIAL_CHAR_RE = re.compile(r"[^\w\s\-_.()\[\]]")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _iter_notes(vault: Path, exclude_dirs: set[str] | None = None) -> list[Path]:
    """Return all .md files in the vault, excluding specified subdirs."""
    exclude_dirs = exclude_dirs or {"_Reports", ".obsidian"}
    notes = []
    for p in vault.rglob("*.md"):
        if any(part in exclude_dirs for part in p.parts):
            continue
        notes.append(p)
    return notes


def _note_stem_set(vault: Path, exclude_dirs: set[str] | None = None) -> set[str]:
    return {p.stem for p in _iter_notes(vault, exclude_dirs)}


def _body_after_frontmatter(text: str) -> str:
    """Strip YAML frontmatter (--- ... ---) and return remaining body."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].strip()
    return text.strip()


def _extract_wikilinks(text: str) -> list[str]:
    """Return list of link targets from [[Target]] or [[Target|Alias]] syntax."""
    return WIKILINK_RE.findall(text)


def _extract_tags_frontmatter(text: str) -> list[str]:
    """Extract tags from YAML frontmatter `tags:` field (list or inline)."""
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return []
    fm_block = fm_match.group(1)
    tags: list[str] = []
    # List form: tags: [a, b, c]
    list_match = re.search(r"^tags:\s*\[([^\]]*)\]", fm_block, re.MULTILINE)
    if list_match:
        raw = list_match.group(1)
        tags = [t.strip().strip('"').strip("'") for t in raw.split(",") if t.strip()]
    else:
        # Block form:
        # tags:
        #   - a
        #   - b
        block_match = re.search(r"^tags:\s*\n((?:\s+-\s+.+\n?)+)", fm_block, re.MULTILINE)
        if block_match:
            tags = [
                line.strip().lstrip("- ").strip()
                for line in block_match.group(1).splitlines()
                if line.strip().startswith("-")
            ]
    return tags


# ── Structural analysis ───────────────────────────────────────────────────────

def find_empty_notes(vault: Path) -> list[Path]:
    """Return notes that are 0 bytes or contain only frontmatter (no body content)."""
    empty = []
    for note in _iter_notes(vault):
        text = note.read_text(encoding="utf-8", errors="replace")
        body = _body_after_frontmatter(text)
        if not body:
            empty.append(note)
    return empty


def find_orphan_notes(vault: Path) -> list[Path]:
    """Return notes with no incoming links AND no outgoing links."""
    notes = _iter_notes(vault)
    # Build outgoing: note → set of targets it links to
    outgoing: dict[str, set[str]] = {}
    for note in notes:
        text = note.read_text(encoding="utf-8", errors="replace")
        outgoing[note.stem] = set(_extract_wikilinks(text))

    # Build incoming: note ← set of notes that link to it
    incoming: dict[str, set[str]] = defaultdict(set)
    for src, targets in outgoing.items():
        for tgt in targets:
            incoming[tgt].add(src)

    orphans = []
    for note in notes:
        has_out = bool(outgoing.get(note.stem))
        has_in = bool(incoming.get(note.stem))
        if not has_out and not has_in:
            orphans.append(note)
    return orphans


def detect_tag_duplicates(vault: Path) -> list[list[str]]:
    """
    Find tags that differ only in case (e.g. 'JP', 'jp', 'Jp').
    Returns groups of duplicate tags (only groups with 2+ members).
    """
    tag_variants: dict[str, set[str]] = defaultdict(set)  # lowercase → original variants
    for note in _iter_notes(vault):
        text = note.read_text(encoding="utf-8", errors="replace")
        for tag in _extract_tags_frontmatter(text):
            tag_variants[tag.lower()].add(tag)
        # Also inline #tags in body
        body = _body_after_frontmatter(text)
        for m in TAG_INLINE_RE.finditer(body):
            tag = m.group(1)
            tag_variants[tag.lower()].add(tag)

    return [list(variants) for variants in tag_variants.values() if len(variants) >= 2]


def check_filename_conventions(vault: Path) -> list[dict[str, Any]]:
    """
    Return notes whose filenames violate conventions:
    - contains spaces
    - contains special characters (not alphanumeric, hyphen, underscore, dot, parens, brackets)
    - stem length > 100 characters
    """
    issues = []
    for note in _iter_notes(vault):
        reasons = []
        stem = note.stem
        if " " in stem:
            reasons.append("contains spaces")
        if SPECIAL_CHAR_RE.search(stem):
            reasons.append("contains special characters")
        if len(stem) > 100:
            reasons.append(f"stem length {len(stem)} > 100")
        if reasons:
            issues.append({"file": note, "reasons": reasons})
    return issues


def find_broken_wikilinks(vault: Path) -> list[dict[str, Any]]:
    """
    Return wikilinks pointing to notes that do not exist in the vault.
    Handles [[Target|Alias]] syntax by extracting the target part only.
    """
    existing = _note_stem_set(vault)
    broken = []
    for note in _iter_notes(vault):
        text = note.read_text(encoding="utf-8", errors="replace")
        for target in _extract_wikilinks(text):
            target_clean = target.strip()
            if target_clean and target_clean not in existing:
                broken.append({"source": note, "target": target_clean})
    return broken


def flag_duplicate_filenames(vault: Path, threshold: float = 0.85) -> list[tuple[str, str]]:
    """
    Flag pairs of notes whose filenames are highly similar (Levenshtein ratio >= threshold).
    Returns list of (stem_a, stem_b) pairs.
    """
    def _levenshtein_ratio(a: str, b: str) -> float:
        a, b = a.lower(), b.lower()
        if a == b:
            return 1.0
        la, lb = len(a), len(b)
        if la == 0 or lb == 0:
            return 0.0
        # DP table
        dp = list(range(lb + 1))
        for i, ca in enumerate(a, 1):
            new_dp = [i]
            for j, cb in enumerate(b, 1):
                cost = 0 if ca == cb else 1
                new_dp.append(min(new_dp[j - 1] + 1, dp[j] + 1, dp[j - 1] + cost))
            dp = new_dp
        distance = dp[lb]
        return 1 - distance / max(la, lb)

    stems = [p.stem for p in _iter_notes(vault)]
    pairs = []
    for i in range(len(stems)):
        for j in range(i + 1, len(stems)):
            if _levenshtein_ratio(stems[i], stems[j]) >= threshold:
                pairs.append((stems[i], stems[j]))
    return pairs


# ── Content analysis (no model — TF-IDF + cosine) ────────────────────────────

def _tfidf_cosine_matrix(texts: list[str]):
    """Return a cosine similarity matrix using TF-IDF vectors."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    vectorizer = TfidfVectorizer(min_df=1, stop_words=None)
    tfidf = vectorizer.fit_transform(texts)
    return cosine_similarity(tfidf)


def cluster_similar_notes(
    vault: Path,
    use_model: bool = True,
    min_similarity: float = 0.75,
) -> list[list[Path]]:
    """
    Group notes by content similarity.
    use_model=True  → bge-m3 embeddings (cosine on dense vectors).
    use_model=False → TF-IDF + cosine (no GPU needed, good enough for clustering).
    Returns list of clusters (each cluster is a list of Path objects, size >= 2).
    """
    notes = _iter_notes(vault)
    if len(notes) < 2:
        return []

    bodies = []
    for note in notes:
        text = note.read_text(encoding="utf-8", errors="replace")
        bodies.append(_body_after_frontmatter(text) or note.stem)

    if use_model:
        # Reuse bge-m3 pattern from app/backend/app/rag/embeddings.py
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            model_obj = SentenceTransformer("BAAI/bge-m3")
            embeddings = model_obj.encode(bodies, normalize_embeddings=True)
            from sklearn.metrics.pairwise import cosine_similarity
            sim_matrix = cosine_similarity(embeddings)
        except ImportError:
            sim_matrix = _tfidf_cosine_matrix(bodies)
    else:
        sim_matrix = _tfidf_cosine_matrix(bodies)

    n = len(notes)
    visited = set()
    clusters = []
    for i in range(n):
        if i in visited:
            continue
        cluster = [notes[i]]
        visited.add(i)
        for j in range(i + 1, n):
            if j not in visited and sim_matrix[i][j] >= min_similarity:
                cluster.append(notes[j])
                visited.add(j)
        if len(cluster) >= 2:
            clusters.append(cluster)
    return clusters


def suggest_missing_backlinks(vault: Path, use_model: bool = False) -> list[dict[str, Any]]:
    """
    Find cases where Note A mentions a keyword that exactly matches Note B's stem,
    but Note A does not link [[NoteB]].
    Returns list of {"source": Path, "missing_link": str} dicts.
    """
    notes = _iter_notes(vault)
    stems = {note.stem: note for note in notes}
    suggestions = []
    for note in notes:
        text = note.read_text(encoding="utf-8", errors="replace")
        body = _body_after_frontmatter(text)
        existing_links = set(_extract_wikilinks(text))
        for stem, target_path in stems.items():
            if stem == note.stem:
                continue
            if stem in existing_links:
                continue
            # Check if stem appears as a word boundary match in the body
            pattern = r"\b" + re.escape(stem) + r"\b"
            if re.search(pattern, body):
                suggestions.append({"source": note, "missing_link": stem})
    return suggestions


def find_orphan_concepts(
    vault: Path,
    min_occurrences: int = 3,
) -> list[dict[str, Any]]:
    """
    Find multi-word or capitalized terms appearing in min_occurrences+ notes
    that do NOT have their own note.
    Returns list of {"term": str, "count": int, "notes": list[Path]}.
    """
    notes = _iter_notes(vault)
    existing_stems = _note_stem_set(vault)
    # Match capitalized words (simple heuristic for named concepts)
    concept_re = re.compile(r"\b([A-Z][a-zA-Z]{2,})\b")
    term_notes: dict[str, list[Path]] = defaultdict(list)
    for note in notes:
        text = note.read_text(encoding="utf-8", errors="replace")
        body = _body_after_frontmatter(text)
        found_in_note = set(concept_re.findall(body))
        for term in found_in_note:
            term_notes[term].append(note)

    orphan_concepts = []
    for term, note_list in term_notes.items():
        if len(note_list) >= min_occurrences and term not in existing_stems:
            orphan_concepts.append({"term": term, "count": len(note_list), "notes": note_list})
    return sorted(orphan_concepts, key=lambda x: x["count"], reverse=True)


# ── LFM2-2.6B summaries (USE_MODEL=True only) ────────────────────────────────

def _load_lfm2():
    """Lazy-load LFM2-2.6B. Returns (model, tokenizer) tuple."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    model_id = "LiquidAI/LFM2-2.6B"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        device_map="auto",
        torch_dtype="bfloat16",
    )
    return model, tokenizer


def _generate_summary(model, tokenizer, text: str, max_words: int = 100) -> str:
    """Generate a 1-2 sentence summary using LFM2-2.6B."""
    prompt = (
        f"Summarize the following note in 1-2 sentences ({max_words} words max):\n\n"
        f"{text[:2000]}\n\nSummary:"
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    max_new_tokens = max_words * 2  # rough token budget
    with __import__("torch").no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
        )
    generated = outputs[0][inputs["input_ids"].shape[1]:]
    summary = tokenizer.decode(generated, skip_special_tokens=True).strip()
    # Trim to first 2 sentences
    sentences = re.split(r"(?<=[.!?])\s+", summary)
    return " ".join(sentences[:2])


def generate_frontmatter_summaries(
    vault: Path,
    use_model: bool = False,
    model=None,
    tokenizer=None,
    max_summary_length: int = 100,
) -> list[dict[str, Any]]:
    """
    Find notes without a `summary:` frontmatter field.
    If use_model=True and model/tokenizer provided: generate summaries via LFM2-2.6B.
    Otherwise: return notes needing summaries with empty summary field.
    Returns list of {"note": Path, "summary": str} dicts.
    """
    results = []
    for note in _iter_notes(vault):
        text = note.read_text(encoding="utf-8", errors="replace")
        fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        if fm_match and "summary:" in fm_match.group(1):
            continue  # already has summary
        body = _body_after_frontmatter(text)
        if not body:
            continue
        if model is not None and tokenizer is not None:
            summary = _generate_summary(model, tokenizer, body, max_summary_length)
        else:
            summary = ""
        results.append({"note": note, "summary": summary})
    return results


# ── Report generation ─────────────────────────────────────────────────────────

def generate_report(
    vault_path: Path,
    use_model: bool = True,
    min_similarity: float = MIN_SIMILARITY,
    max_summary_length: int = MAX_SUMMARY_LENGTH,
    report_subdir: str = REPORT_PATH,
) -> Path:
    """
    Run all analysis passes and write the report.
    Returns the Path of the written report file.
    """
    today = date.today().strftime("%Y-%m-%d")

    # ── Structural pass (always runs, no model) ───────────────────────────────
    empty = find_empty_notes(vault_path)
    orphans = find_orphan_notes(vault_path)
    tag_groups = detect_tag_duplicates(vault_path)
    filename_issues = check_filename_conventions(vault_path)
    broken_links = find_broken_wikilinks(vault_path)
    dup_names = flag_duplicate_filenames(vault_path)

    # ── Content pass ─────────────────────────────────────────────────────────
    lfm2_model = None
    lfm2_tokenizer = None
    if use_model:
        lfm2_model, lfm2_tokenizer = _load_lfm2()

    clusters = cluster_similar_notes(vault_path, use_model=use_model, min_similarity=min_similarity)
    backlink_suggestions = suggest_missing_backlinks(vault_path)
    orphan_concepts = find_orphan_concepts(vault_path)
    summaries = generate_frontmatter_summaries(
        vault_path,
        use_model=use_model,
        model=lfm2_model,
        tokenizer=lfm2_tokenizer,
        max_summary_length=max_summary_length,
    )

    # Unload model from memory
    if lfm2_model is not None:
        del lfm2_model
        del lfm2_tokenizer

    # ── Build report Markdown ─────────────────────────────────────────────────
    lines: list[str] = []
    lines.append(f"# Vault Report — {today}")
    lines.append("")
    lines.append(f"> Generated by `vault_organizer.py` | Model: {'LFM2-2.6B' if use_model else 'disabled'}")
    lines.append("")

    # Section 1: Strukturelle Probleme
    lines.append("## Strukturelle Probleme")
    lines.append("")

    if empty:
        lines.append(f"### Leere Notes ({len(empty)})")
        for p in empty:
            lines.append(f"- `{p.name}`")
        lines.append("")
    else:
        lines.append("Keine leeren Notes gefunden.")
        lines.append("")

    if orphans:
        lines.append(f"### Orphan Notes ({len(orphans)}) — keine Links rein oder raus")
        for p in orphans:
            lines.append(f"- `{p.name}`")
        lines.append("")
    else:
        lines.append("Keine Orphan Notes gefunden.")
        lines.append("")

    if broken_links:
        lines.append(f"### Broken Wikilinks ({len(broken_links)})")
        for b in broken_links:
            lines.append(f"- `{b['source'].name}` → `[[{b['target']}]]` (existiert nicht)")
        lines.append("")
    else:
        lines.append("Keine Broken Links gefunden.")
        lines.append("")

    if filename_issues:
        lines.append(f"### Dateinamen-Probleme ({len(filename_issues)})")
        for issue in filename_issues:
            reasons_str = ", ".join(issue["reasons"])
            lines.append(f"- `{issue['file'].name}` — {reasons_str}")
        lines.append("")

    if dup_names:
        lines.append(f"### Mögliche Duplikate nach Dateiname ({len(dup_names)} Paare)")
        for a, b in dup_names:
            lines.append(f"- `{a}` ↔ `{b}`")
        lines.append("")

    # Section 2: Tag-Normalisierung
    lines.append("## Tag-Normalisierung")
    lines.append("")
    if tag_groups:
        lines.append(f"{len(tag_groups)} Tag-Gruppen mit Varianten gefunden:")
        lines.append("")
        for group in tag_groups:
            variants = " + ".join(f"`#{t}`" for t in group)
            suggestion = group[0].lower()
            lines.append(f"- {variants} → `#{suggestion}` (Empfehlung)")
    else:
        lines.append("Keine Tag-Duplikate gefunden.")
    lines.append("")

    # Section 3: Inhaltliche Vorschläge
    lines.append("## Inhaltliche Vorschläge")
    if not use_model:
        lines.append("")
        lines.append("> *Modell deaktiviert (`USE_MODEL=False`). Nur TF-IDF-Clustering aktiv.*")
    lines.append("")

    if clusters:
        lines.append(f"### Ähnliche Notes — mögliche Zusammenführung ({len(clusters)} Gruppen)")
        lines.append("")
        for cluster in clusters:
            names = ", ".join(f"`{p.stem}`" for p in cluster)
            lines.append(f"- {names}")
        lines.append("")

    if backlink_suggestions:
        lines.append(f"### Fehlende Backlinks ({len(backlink_suggestions)} Vorschläge)")
        lines.append("")
        for s in backlink_suggestions[:20]:  # cap at 20 to keep report readable
            lines.append(f"- `{s['source'].stem}` erwähnt `{s['missing_link']}` ohne `[[{s['missing_link']}]]`")
        if len(backlink_suggestions) > 20:
            lines.append(f"- *(+{len(backlink_suggestions) - 20} weitere)*")
        lines.append("")

    if orphan_concepts:
        lines.append(f"### Verwaiste Konzepte ({len(orphan_concepts)}) — häufig erwähnt, keine eigene Note")
        lines.append("")
        for c in orphan_concepts[:15]:
            lines.append(f"- **{c['term']}** ({c['count']}× erwähnt)")
        lines.append("")

    # Section 4: Neue Frontmatter Summaries
    lines.append("## Neue Frontmatter Summaries")
    lines.append("")
    if summaries:
        lines.append(f"{len(summaries)} Notes ohne `summary:` Feld:")
        lines.append("")
        for s in summaries:
            lines.append(f"### `{s['note'].stem}`")
            if s["summary"]:
                lines.append("")
                lines.append(s["summary"])
            else:
                lines.append("")
                lines.append("*(kein Summary generiert — USE_MODEL=False)*")
            lines.append("")
    else:
        lines.append("Alle Notes haben bereits ein `summary:` Feld.")
    lines.append("")

    # ── Write report ──────────────────────────────────────────────────────────
    report_dir = vault_path / report_subdir
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"vault_report_{today}.md"
    report_file.write_text("\n".join(lines), encoding="utf-8")
    return report_file


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    vault = Path(VAULT_PATH)
    if not vault.exists():
        print(f"[vault_organizer] ERROR: VAULT_PATH does not exist: {vault}", file=sys.stderr)
        sys.exit(1)

    print(f"[vault_organizer] Analyzing vault: {vault}")
    print(f"[vault_organizer] USE_MODEL={USE_MODEL}")

    report = generate_report(
        vault_path=vault,
        use_model=USE_MODEL,
        min_similarity=MIN_SIMILARITY,
        max_summary_length=MAX_SUMMARY_LENGTH,
        report_subdir=REPORT_PATH,
    )
    print(f"[vault_organizer] Report written to: {report}")


if __name__ == "__main__":
    main()

# Windows Task Scheduler:
# schtasks /create /tn "HimeVaultOrganizer" /tr "uv run --project N:\Projekte\NiN\Hime\app\backend N:\Projekte\NiN\Hime\scripts\vault_organizer.py" /sc weekly /d SUN /st 10:00
