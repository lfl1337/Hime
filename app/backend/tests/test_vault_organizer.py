"""
Tests for scripts/vault_organizer.py — structural analysis and report generation.

All tests use tmp_path (pytest built-in) as the fake vault root.
Model-dependent code is tested via USE_MODEL=False path (no GPU needed in CI).
sys.path is set by conftest.py — do NOT add duplicate path code here.
"""
import importlib
import sys
from datetime import date
from pathlib import Path


def _load_organizer():
    """Re-import to get a fresh module (handles test isolation)."""
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
