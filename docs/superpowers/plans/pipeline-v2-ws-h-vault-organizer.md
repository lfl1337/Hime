# Vault Organizer (WS-H) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone weekly script (`scripts/vault_organizer.py`) that analyzes the Hime Obsidian vault, detects structural issues and content improvement opportunities, and writes a Markdown report — with zero integration into the main pipeline.

**Architecture:** The script runs in two passes: a pure-Python structural pass (no model, always runs) and an optional content pass (LFM2-2.6B via Transformers, skipped when `USE_MODEL=False`). Both passes write their findings into a single Markdown report saved to `{VAULT_PATH}/_Reports/vault_report_YYYY-MM-DD.md`. The script is self-contained — no imports from `app/` — and reads the vault read-only except for the report output.

**Tech Stack:** Python 3.11+, `python-frontmatter`, `scikit-learn` (TF-IDF + cosine similarity), `transformers>=5.0.0` (LFM2-2.6B), `pathlib`, `re`, `pytest` (tests with `tmp_path` fixture, no asyncio).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `scripts/vault_organizer.py` | Create | Main standalone script: config, structural pass, content pass, report writer |
| `app/backend/tests/test_vault_organizer.py` | Create | pytest tests for structural detection, report format, and USE_MODEL=False path |
| `app/backend/pyproject.toml` | Modify | Add `[vault]` optional dependency group |

---

## Task 1: Add `[vault]` optional dependencies to pyproject.toml

**Files:**
- Modify: `app/backend/pyproject.toml`

- [ ] **Step 1.1: Read current pyproject.toml**

Open `N:\Projekte\NiN\Hime\app\backend\pyproject.toml` and confirm the `[project.optional-dependencies]` section. It currently only has a `dev` group.

- [ ] **Step 1.2: Add the vault optional group**

In `app/backend/pyproject.toml`, add the `vault` group right after the `dev` group under `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
    "ruff>=0.4.0",
]
vault = [
    "python-frontmatter>=1.1.0",
    "scikit-learn>=1.4.0",
    "transformers>=5.0.0",
]
```

Note: `pathlib` is stdlib (Python 3.4+), no need to list it. `sentence-transformers` is already in the main dependencies.

- [ ] **Step 1.3: Verify the file parses correctly**

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
python -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))" && echo "OK"
```

Expected: `OK`

- [ ] **Step 1.4: Commit**

```bash
cd "N:/Projekte/NiN/Hime"
git add app/backend/pyproject.toml
git commit -m "chore(deps): add [vault] optional dependency group for vault_organizer"
```

---

## Task 2: Write failing tests for structural analysis

**Files:**
- Create: `app/backend/tests/test_vault_organizer.py`

These tests use `tmp_path` (built-in pytest fixture) and import `vault_organizer` from `scripts/`. No asyncio — pure sync tests.

- [ ] **Step 2.1: Write the test file**

Create `N:\Projekte\NiN\Hime\app\backend\tests\test_vault_organizer.py`:

```python
"""
Tests for scripts/vault_organizer.py — structural analysis and report generation.

All tests use tmp_path (pytest built-in) as the fake vault root.
Model-dependent code is tested via USE_MODEL=False path (no GPU needed in CI).
"""
import sys
import importlib
from pathlib import Path
from datetime import date

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def _load_organizer():
    """Re-import after sys.path is set (handles test isolation)."""
    if "vault_organizer" in sys.modules:
        del sys.modules["vault_organizer"]
    return importlib.import_module("vault_organizer")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_note(vault: Path, name: str, content: str) -> Path:
    """Write a markdown note to the vault root."""
    p = vault / f"{name}.md"
    p.write_text(content, encoding="utf-8")
    return p


# ── Structural: empty notes ───────────────────────────────────────────────────

def test_find_empty_notes_detects_zero_byte(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "empty", "")
    _write_note(tmp_path, "notempty", "# Hello\n\nSome content here.")
    result = vo.find_empty_notes(tmp_path)
    assert len(result) == 1
    assert result[0].stem == "empty"


def test_find_empty_notes_detects_frontmatter_only(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "only_fm", "---\ntags: [test]\n---\n")
    _write_note(tmp_path, "with_body", "---\ntags: [test]\n---\n\nActual content.")
    result = vo.find_empty_notes(tmp_path)
    assert len(result) == 1
    assert result[0].stem == "only_fm"


def test_find_empty_notes_skips_reports_dir(tmp_path):
    vo = _load_organizer()
    reports = tmp_path / "_Reports"
    reports.mkdir()
    _write_note(reports, "old_report", "")
    _write_note(tmp_path, "real_empty", "")
    result = vo.find_empty_notes(tmp_path)
    assert len(result) == 1
    assert result[0].stem == "real_empty"


# ── Structural: orphan notes ──────────────────────────────────────────────────

def test_find_orphan_notes_no_links(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "island", "Just text, no links at all.")
    _write_note(tmp_path, "hub", "Links to [[island]] and mentions stuff.")
    result = vo.find_orphan_notes(tmp_path)
    # "island" has an incoming link from hub, so not orphan.
    # "hub" has no incoming links AND links out — it's an orphan by incoming criterion.
    # Both need to be checked: orphan = no incoming AND no outgoing.
    assert result == []  # island has incoming link; hub has outgoing


def test_find_orphan_notes_true_orphan(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "lonely", "No links in or out.")
    _write_note(tmp_path, "connected", "Links to [[connected_b]].")
    _write_note(tmp_path, "connected_b", "Referenced by [[connected]].")
    result = vo.find_orphan_notes(tmp_path)
    assert len(result) == 1
    assert result[0].stem == "lonely"


# ── Structural: tag normalization ─────────────────────────────────────────────

def test_detect_tag_duplicates_case_insensitive(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "a", "---\ntags: [JP, Japanese]\n---\nContent.")
    _write_note(tmp_path, "b", "---\ntags: [japanese, translation]\n---\nContent.")
    groups = vo.detect_tag_duplicates(tmp_path)
    # Should find that "jp" != "japanese" (different roots), but jp/JP are duplicates
    # and japanese/Japanese/japanese are duplicates
    canonical = {frozenset(g) for g in groups}
    assert frozenset({"JP", "japanese", "Japanese"}) not in canonical  # not same word
    jp_group = next((g for g in groups if any(t.lower() == "jp" for t in g)), None)
    assert jp_group is None or len(jp_group) == 1  # "jp" appears only once total (no dup)
    ja_group = next((g for g in groups if any(t.lower() == "japanese" for t in g)), None)
    assert ja_group is not None
    assert len(ja_group) >= 2  # Japanese + japanese


def test_detect_tag_duplicates_no_false_positives(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "a", "---\ntags: [translation, rag]\n---\nContent.")
    _write_note(tmp_path, "b", "---\ntags: [pipeline, training]\n---\nContent.")
    groups = vo.detect_tag_duplicates(tmp_path)
    assert groups == []


# ── Structural: filename conventions ──────────────────────────────────────────

def test_check_filename_conventions_spaces(tmp_path):
    vo = _load_organizer()
    p = tmp_path / "note with spaces.md"
    p.write_text("content", encoding="utf-8")
    issues = vo.check_filename_conventions(tmp_path)
    names = [i["file"].name for i in issues]
    assert "note with spaces.md" in names


def test_check_filename_conventions_special_chars(tmp_path):
    vo = _load_organizer()
    p = tmp_path / "note#special!.md"
    p.write_text("content", encoding="utf-8")
    issues = vo.check_filename_conventions(tmp_path)
    names = [i["file"].name for i in issues]
    assert "note#special!.md" in names


def test_check_filename_conventions_long_name(tmp_path):
    vo = _load_organizer()
    long_name = "a" * 101 + ".md"
    p = tmp_path / long_name
    p.write_text("content", encoding="utf-8")
    issues = vo.check_filename_conventions(tmp_path)
    names = [i["file"].name for i in issues]
    assert long_name in names


def test_check_filename_conventions_clean_name_ok(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "clean-note_v1", "content")
    issues = vo.check_filename_conventions(tmp_path)
    assert issues == []


# ── Structural: broken wikilinks ─────────────────────────────────────────────

def test_find_broken_wikilinks_detects_missing_target(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "source", "See [[NonExistentNote]] for details.")
    results = vo.find_broken_wikilinks(tmp_path)
    assert len(results) == 1
    assert results[0]["source"].stem == "source"
    assert results[0]["target"] == "NonExistentNote"


def test_find_broken_wikilinks_valid_link_ok(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "source", "See [[target_note]] for details.")
    _write_note(tmp_path, "target_note", "I exist.")
    results = vo.find_broken_wikilinks(tmp_path)
    assert results == []


def test_find_broken_wikilinks_alias_syntax(tmp_path):
    vo = _load_organizer()
    # [[Note|Alias]] format — target is "Note"
    _write_note(tmp_path, "source", "See [[RealNote|display text]].")
    _write_note(tmp_path, "RealNote", "content")
    results = vo.find_broken_wikilinks(tmp_path)
    assert results == []


# ── Structural: duplicate filenames ───────────────────────────────────────────

def test_flag_duplicate_filenames_similar(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "Pipeline Architecture", "content a")
    _write_note(tmp_path, "Pipeline-Architecture", "content b")
    pairs = vo.flag_duplicate_filenames(tmp_path)
    assert len(pairs) >= 1
    names_in_pairs = {n for pair in pairs for n in pair}
    assert "Pipeline Architecture" in names_in_pairs or "Pipeline-Architecture" in names_in_pairs


def test_flag_duplicate_filenames_different_ok(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "Gemma Notes", "content a")
    _write_note(tmp_path, "DeepSeek Notes", "content b")
    pairs = vo.flag_duplicate_filenames(tmp_path)
    assert pairs == []


# ── Content analysis (USE_MODEL=False) ───────────────────────────────────────

def test_cluster_similar_notes_no_model(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "NoteA", "The pipeline runs translation in three stages using models.")
    _write_note(tmp_path, "NoteB", "Pipeline translation stages execute three models in sequence.")
    _write_note(tmp_path, "NoteC", "Yuri romance subplot between Hina and Saki develops slowly.")
    clusters = vo.cluster_similar_notes(tmp_path, use_model=False, min_similarity=0.3)
    # NoteA and NoteB should cluster together, NoteC alone
    assert any(
        {"NoteA", "NoteB"}.issubset({n.stem for n in cluster})
        for cluster in clusters
    )


def test_suggest_missing_backlinks_no_model(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "MetricX", "MetricX is a translation quality metric.")
    _write_note(tmp_path, "Pipeline", "We use MetricX to evaluate quality but no link here.")
    suggestions = vo.suggest_missing_backlinks(tmp_path)
    # Pipeline mentions "MetricX" but doesn't link [[MetricX]]
    assert any(
        s["source"].stem == "Pipeline" and s["missing_link"] == "MetricX"
        for s in suggestions
    )


def test_find_orphan_concepts_no_model(tmp_path):
    vo = _load_organizer()
    # "BLEU" appears in 3 notes but has no own note
    _write_note(tmp_path, "Note1", "BLEU score measures translation quality.")
    _write_note(tmp_path, "Note2", "We calculate BLEU for each output.")
    _write_note(tmp_path, "Note3", "BLEU is often criticized for limitations.")
    concepts = vo.find_orphan_concepts(tmp_path, min_occurrences=3)
    terms = [c["term"] for c in concepts]
    assert "BLEU" in terms


def test_find_orphan_concepts_existing_note_excluded(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "Note1", "Pipeline is used everywhere.")
    _write_note(tmp_path, "Note2", "The Pipeline runs daily.")
    _write_note(tmp_path, "Note3", "Pipeline architecture is complex.")
    _write_note(tmp_path, "Pipeline", "# Pipeline\n\nThis note is about the pipeline.")
    concepts = vo.find_orphan_concepts(tmp_path, min_occurrences=3)
    terms = [c["term"] for c in concepts]
    assert "Pipeline" not in terms


# ── Report generation ─────────────────────────────────────────────────────────

def test_generate_report_creates_file(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "empty_note", "")
    report_path = vo.generate_report(
        vault_path=tmp_path,
        use_model=False,
        min_similarity=0.75,
        max_summary_length=100,
        report_subdir="_Reports",
    )
    assert report_path.exists()
    today = date.today().strftime("%Y-%m-%d")
    assert report_path.name == f"vault_report_{today}.md"


def test_generate_report_contains_required_sections(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "normal", "Some content [[broken_link]].")
    report_path = vo.generate_report(
        vault_path=tmp_path,
        use_model=False,
        min_similarity=0.75,
        max_summary_length=100,
        report_subdir="_Reports",
    )
    content = report_path.read_text(encoding="utf-8")
    assert "## Strukturelle Probleme" in content
    assert "## Tag-Normalisierung" in content
    assert "## Inhaltliche Vorschläge" in content
    assert "## Neue Frontmatter Summaries" in content


def test_generate_report_header_has_date(tmp_path):
    vo = _load_organizer()
    report_path = vo.generate_report(
        vault_path=tmp_path,
        use_model=False,
        min_similarity=0.75,
        max_summary_length=100,
        report_subdir="_Reports",
    )
    content = report_path.read_text(encoding="utf-8")
    today = date.today().strftime("%Y-%m-%d")
    assert f"# Vault Report — {today}" in content


def test_generate_report_lists_empty_notes(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "ghost", "")
    report_path = vo.generate_report(
        vault_path=tmp_path,
        use_model=False,
        min_similarity=0.75,
        max_summary_length=100,
        report_subdir="_Reports",
    )
    content = report_path.read_text(encoding="utf-8")
    assert "ghost" in content


def test_generate_report_lists_broken_links(tmp_path):
    vo = _load_organizer()
    _write_note(tmp_path, "source_note", "See [[MissingTarget]] for info.")
    report_path = vo.generate_report(
        vault_path=tmp_path,
        use_model=False,
        min_similarity=0.75,
        max_summary_length=100,
        report_subdir="_Reports",
    )
    content = report_path.read_text(encoding="utf-8")
    assert "MissingTarget" in content


def test_generate_report_not_in_its_own_analysis(tmp_path):
    """The report file itself must not appear in orphan/empty/broken-link analysis."""
    vo = _load_organizer()
    _write_note(tmp_path, "normal", "Normal content.")
    report_path = vo.generate_report(
        vault_path=tmp_path,
        use_model=False,
        min_similarity=0.75,
        max_summary_length=100,
        report_subdir="_Reports",
    )
    content = report_path.read_text(encoding="utf-8")
    assert report_path.name not in content or content.count(report_path.name) == 0
```

- [ ] **Step 2.2: Run tests to confirm they all FAIL (ImportError)**

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
python -m pytest tests/test_vault_organizer.py -v 2>&1 | head -30
```

Expected output: `ModuleNotFoundError: No module named 'vault_organizer'`

- [ ] **Step 2.3: Commit the failing tests**

```bash
cd "N:/Projekte/NiN/Hime"
git add app/backend/tests/test_vault_organizer.py
git commit -m "test(vault-organizer): add failing test suite for WS-H structural+report analysis"
```

---

## Task 3: Implement structural analysis functions

**Files:**
- Create: `scripts/vault_organizer.py` (structural functions only, no model code yet)

- [ ] **Step 3.1: Create the script with config block and structural functions**

Create `N:\Projekte\NiN\Hime\scripts\vault_organizer.py`:

```python
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

import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

# ── Configuration (edit these before running) ─────────────────────────────────

VAULT_PATH = Path(r"C:\Users\lfLaw\ObsidianVault")   # ← adjust to your vault
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
        name = note.name
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


def suggest_missing_backlinks(vault: Path) -> list[dict[str, Any]]:
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
    model=None,
    tokenizer=None,
    max_summary_length: int = 100,
) -> list[dict[str, Any]]:
    """
    Find notes without a `summary:` frontmatter field.
    If model/tokenizer provided: generate summaries via LFM2-2.6B.
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
```

- [ ] **Step 3.2: Run only the structural tests (skip content/report for now)**

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
python -m pytest tests/test_vault_organizer.py -v -k "empty or orphan or tag or filename or broken or duplicate" 2>&1
```

Expected: All structural tests PASS.

- [ ] **Step 3.3: Run the full test suite to see what still fails**

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
python -m pytest tests/test_vault_organizer.py -v 2>&1
```

Expected: Structural tests pass. Content + report tests may still fail. Note which ones fail and why before continuing.

- [ ] **Step 3.4: Commit the structural implementation**

```bash
cd "N:/Projekte/NiN/Hime"
git add scripts/vault_organizer.py
git commit -m "feat(vault-organizer): implement structural analysis pass (find_empty, orphans, tags, filenames, broken links, duplicates)"
```

---

## Task 4: Make all tests green — content analysis + report generation

**Files:**
- Modify: `scripts/vault_organizer.py` (content functions are already written in Task 3 — verify tests now pass)

- [ ] **Step 4.1: Install vault dependencies into the test environment**

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
uv pip install "python-frontmatter>=1.1.0" "scikit-learn>=1.4.0"
```

Expected: `Resolved ... installed` without errors.

- [ ] **Step 4.2: Run the full test suite**

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
python -m pytest tests/test_vault_organizer.py -v 2>&1
```

Expected: All tests PASS. If any fail, check the error message and fix the relevant function in `scripts/vault_organizer.py`.

Common failure modes to watch for:
- `test_cluster_similar_notes_no_model` — if scikit-learn not installed: install it (Step 4.1)
- `test_suggest_missing_backlinks_no_model` — word boundary regex not matching: check `suggest_missing_backlinks()` uses `\b` correctly
- `test_find_orphan_concepts_existing_note_excluded` — if "Pipeline" concept still appears: ensure stem lookup is case-sensitive match
- `test_generate_report_not_in_its_own_analysis` — if report path appears in content: ensure `_iter_notes` excludes `_Reports` dir

- [ ] **Step 4.3: Fix the report self-reference test if needed**

The `test_generate_report_not_in_its_own_analysis` test verifies that the report file itself is never analyzed. The `_iter_notes` function excludes `_Reports` by default. If the test fails, confirm `_iter_notes` is called with `exclude_dirs={"_Reports", ".obsidian"}` in all analysis functions. The implementation in Task 3 already passes `exclude_dirs` implicitly via the default — verify the default is set correctly.

If the test still fails after confirming the default, patch `_iter_notes` with an explicit exclude:

```python
# In generate_report(), call analysis functions with explicit exclude
empty = find_empty_notes(vault_path)  # already excludes _Reports via _iter_notes default
```

No change needed if the default `exclude_dirs={"_Reports", ".obsidian"}` is already in `_iter_notes`.

- [ ] **Step 4.4: Run tests again to confirm all green**

```bash
cd "N:/Projekte/NiN/Hime/app/backend"
python -m pytest tests/test_vault_organizer.py -v 2>&1
```

Expected output:
```
tests/test_vault_organizer.py::test_find_empty_notes_detects_zero_byte PASSED
tests/test_vault_organizer.py::test_find_empty_notes_detects_frontmatter_only PASSED
tests/test_vault_organizer.py::test_find_empty_notes_skips_reports_dir PASSED
tests/test_vault_organizer.py::test_find_orphan_notes_no_links PASSED
tests/test_vault_organizer.py::test_find_orphan_notes_true_orphan PASSED
tests/test_vault_organizer.py::test_detect_tag_duplicates_case_insensitive PASSED
tests/test_vault_organizer.py::test_detect_tag_duplicates_no_false_positives PASSED
tests/test_vault_organizer.py::test_check_filename_conventions_spaces PASSED
tests/test_vault_organizer.py::test_check_filename_conventions_special_chars PASSED
tests/test_vault_organizer.py::test_check_filename_conventions_long_name PASSED
tests/test_vault_organizer.py::test_check_filename_conventions_clean_name_ok PASSED
tests/test_vault_organizer.py::test_find_broken_wikilinks_detects_missing_target PASSED
tests/test_vault_organizer.py::test_find_broken_wikilinks_valid_link_ok PASSED
tests/test_vault_organizer.py::test_find_broken_wikilinks_alias_syntax PASSED
tests/test_vault_organizer.py::test_flag_duplicate_filenames_similar PASSED
tests/test_vault_organizer.py::test_flag_duplicate_filenames_different_ok PASSED
tests/test_vault_organizer.py::test_cluster_similar_notes_no_model PASSED
tests/test_vault_organizer.py::test_suggest_missing_backlinks_no_model PASSED
tests/test_vault_organizer.py::test_find_orphan_concepts_no_model PASSED
tests/test_vault_organizer.py::test_find_orphan_concepts_existing_note_excluded PASSED
tests/test_vault_organizer.py::test_generate_report_creates_file PASSED
tests/test_vault_organizer.py::test_generate_report_contains_required_sections PASSED
tests/test_vault_organizer.py::test_generate_report_header_has_date PASSED
tests/test_vault_organizer.py::test_generate_report_lists_empty_notes PASSED
tests/test_vault_organizer.py::test_generate_report_lists_broken_links PASSED
tests/test_vault_organizer.py::test_generate_report_not_in_its_own_analysis PASSED

26 passed in X.XXs
```

- [ ] **Step 4.5: Commit**

```bash
cd "N:/Projekte/NiN/Hime"
git add scripts/vault_organizer.py app/backend/tests/test_vault_organizer.py app/backend/pyproject.toml
git commit -m "feat(vault-organizer): all 26 tests green — structural + content + report generation"
```

---

## Task 5: Manual smoke test against the real vault

**Files:** No code changes — verification only.

- [ ] **Step 5.1: Set the correct VAULT_PATH in the script**

Edit the config block at the top of `scripts/vault_organizer.py`. Set `VAULT_PATH` to the actual Obsidian vault path and `USE_MODEL = False` for a fast first run:

```python
VAULT_PATH = Path(r"N:\Projekte\NiN\Hime\obsidian-vault")  # adjust to actual path
USE_MODEL = False
```

To find the actual vault path, check `app/backend/app/core/paths.py` for `OBSIDIAN_VAULT_DIR`, or look for a `.obsidian` directory:

```bash
find "N:/Projekte/NiN/Hime" -name ".obsidian" -type d 2>/dev/null | head -5
```

- [ ] **Step 5.2: Run the script**

```bash
cd "N:/Projekte/NiN/Hime"
uv run scripts/vault_organizer.py
```

Expected output:
```
[vault_organizer] Analyzing vault: N:\...
[vault_organizer] USE_MODEL=False
[vault_organizer] Report written to: N:\..._Reports\vault_report_2026-04-10.md
```

- [ ] **Step 5.3: Open the report in Obsidian or a text editor**

Verify:
- `# Vault Report — 2026-04-10` at top
- Four sections present: `## Strukturelle Probleme`, `## Tag-Normalisierung`, `## Inhaltliche Vorschläge`, `## Neue Frontmatter Summaries`
- No crash, no traceback
- Report file does not appear in its own findings

- [ ] **Step 5.4: Commit if script needed any path fixes**

If you changed `VAULT_PATH` or fixed any runtime bug:

```bash
cd "N:/Projekte/NiN/Hime"
git add scripts/vault_organizer.py
git commit -m "fix(vault-organizer): adjust VAULT_PATH for local disk layout"
```

---

## Task 6: Windows Task Scheduler setup

**Files:** No code changes — Windows configuration only.

- [ ] **Step 6.1: Confirm `uv` is on the system PATH**

```powershell
where uv
```

Expected: `C:\Users\lfLaw\.local\bin\uv.exe` or similar. If not found, install uv globally first.

- [ ] **Step 6.2: Create the scheduled task via PowerShell**

Open PowerShell as Administrator and run:

```powershell
$action = New-ScheduledTaskAction `
    -Execute "uv" `
    -Argument "run N:\Projekte\NiN\Hime\scripts\vault_organizer.py" `
    -WorkingDirectory "N:\Projekte\NiN\Hime"

$trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Sunday `
    -At "10:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RunOnlyIfNetworkAvailable:$false `
    -StartWhenAvailable:$true

Register-ScheduledTask `
    -TaskName "Hime Vault Organizer" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force
```

- [ ] **Step 6.3: Verify the task was registered**

```powershell
Get-ScheduledTask -TaskName "Hime Vault Organizer" | Select-Object TaskName, State
```

Expected:
```
TaskName              State
--------              -----
Hime Vault Organizer  Ready
```

- [ ] **Step 6.4: Trigger a manual test run via Task Scheduler**

```powershell
Start-ScheduledTask -TaskName "Hime Vault Organizer"
Start-Sleep -Seconds 5
Get-ScheduledTaskInfo -TaskName "Hime Vault Organizer" | Select-Object LastTaskResult, LastRunTime
```

Expected: `LastTaskResult` = `0` (success).

- [ ] **Step 6.5: Document the setup in the script header**

The Windows Task Scheduler details are already documented in the `scripts/vault_organizer.py` module docstring (written in Task 3). Verify it reads:

```
Or via Windows Task Scheduler (weekly, Sunday 10:00):
    Program:   uv
    Arguments: run N:\\Projekte\\NiN\\Hime\\scripts\\vault_organizer.py
```

No code change needed if it's already there.

---

## Spec Coverage Self-Review

| Spec Requirement | Task |
|---|---|
| Standalone script, no pipeline import | Task 3 — no `app/` imports |
| Config block at top (VAULT_PATH, etc.) | Task 3 — first 10 lines of script |
| Find empty notes (0 bytes or frontmatter only) | Task 3 — `find_empty_notes()` |
| Find orphan notes (no links in or out) | Task 3 — `find_orphan_notes()` |
| Tag normalization (case-insensitive dedup) | Task 3 — `detect_tag_duplicates()` |
| Filename conventions (spaces, special chars, >100) | Task 3 — `check_filename_conventions()` |
| Broken wikilinks | Task 3 — `find_broken_wikilinks()` |
| Duplicate notes by Levenshtein filename similarity | Task 3 — `flag_duplicate_filenames()` |
| Cluster similar notes (TF-IDF or bge-m3) | Task 3 — `cluster_similar_notes()` |
| Suggest missing backlinks | Task 3 — `suggest_missing_backlinks()` |
| Frontmatter summaries via LFM2-2.6B | Task 3 — `generate_frontmatter_summaries()` |
| Orphan concepts (3+ notes, no own note) | Task 3 — `find_orphan_concepts()` |
| Report: `_Reports/vault_report_YYYY-MM-DD.md` | Task 3 — `generate_report()` |
| Report sections: Strukturelle / Tag / Inhaltlich / Summaries | Task 3 — report builder |
| No automatic changes | Task 3 — report only, no vault writes |
| `[vault]` optional deps in pyproject.toml | Task 1 |
| Tests with tmp_path, no asyncio | Task 2 |
| Mock model path (USE_MODEL=False) | Task 2 — all content tests use `use_model=False` |
| Windows Task Scheduler setup | Task 6 |

All spec requirements covered. No gaps found.
