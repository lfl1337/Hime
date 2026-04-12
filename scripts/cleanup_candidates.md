# Cleanup Candidates — Training Data / Curriculum

> Last updated: 2026-04-12
> Context: Pre-Qwen3.5-9B training audit

---

## 1. Curriculum loader bypass (train_hime.py + training_config.json)

**What was done:**  
`curriculum.enabled` set to `false` in `training_config.json`.  
Legacy data path changed from `hime_training_all.jsonl` → `hime_training_filtered.jsonl`.

**Why:**  
Both literary files that were registered in `literary_files` had `output: ""` on 100% of entries — they were monolingual JP-only files accidentally added to the training loader:
- `seiyuu_radio_all_jp.jsonl` (52 entries): 14 unübersetzte LN-Bände, keine EN-Übersetzung
- `shuukura_jp.jsonl` (182 entries): status=needs_translation, alle Outputs leer

Every training run before 2026-04-12 trained on these blank EN targets (silently, no warning).

**What to restore when Bertalign output lands:**  
1. Replace `shuukura_jp.jsonl` with Bertalign-aligned pairs (8 EPUB-Bände, JP+EN)
2. Decide whether `seiyuu_radio_all_jp.jsonl` gets aligned or stays RAG-only
3. Re-enable curriculum: set `"enabled": true` in `training_config.json`
4. Revert data path in `train_hime.py`: `hime_training_filtered.jsonl` → `hime_training_all.jsonl`  
   (or keep filtered and add literary via the loader — whichever is cleaner)
5. Re-test `CurriculumCallback` tier promotion logic with real literary data

---

## 2. hime_training_all.jsonl — 66 orphaned shuukura entries

**What:** `hime_training_all.jsonl` contains 66 entries without a `score` field (embedded shuukura entries). They have non-empty output but were always silently dropped by `_filter_jparacrawl`.

**Action:** Keep file as-is. Once curriculum is repaired, decide whether to strip these 66 lines or retain them with a synthetic score field.

---

## 3. Files kept in data/training/ for future RAG session

These files are NOT to be deleted — they are inputs for the upcoming Bertalign alignment session:
- `data/training/seiyuu_radio_all_jp.jsonl` — 14 LN-Bände, JP-only → monolingaler RAG-Store input
- `data/training/shuukura_jp.jsonl` — 8 EPUB-Bände, JP-only → Bertalign alignment input
- `data/training/shuukura_wn_aligned.jsonl` — possibly already aligned? Needs review before RAG session

---

## Current confirmed training state (2026-04-12)

| File                              | Entries | Score field | Non-empty output | Used in training |
|-----------------------------------|---------|-------------|-----------------|-----------------|
| hime_training_filtered.jsonl      | 104,866 | all ≥ 0.70  | 100%            | YES (current)   |
| hime_training_all.jsonl           | 104,932 | 104,866 ≥ 0.70 + 66 None | 104,866 + 66 | no              |
| seiyuu_radio_all_jp.jsonl         | 52      | none        | 0%              | no (removed)    |
| shuukura_jp.jsonl                 | 182     | none        | 0%              | no (removed)    |
