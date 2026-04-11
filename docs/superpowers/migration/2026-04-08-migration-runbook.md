# Hime Disk Migration Runbook

**Created:** 2026-04-08
**Author:** Pre-migration session (WS2 was paused at T2 to write this runbook)
**Target migration window:** within hours of this document
**Source main HEAD:** `8a3214f`
**Pre-migration baseline:** `docs/superpowers/migration/2026-04-08-pre-migration-verify.txt`

> This runbook is the survival kit for moving Hime to a new disk. Every step that
> requires manual judgment is called out explicitly. Read top-to-bottom once before
> starting the migration.

---

## TL;DR

1. Stop training and the FastAPI backend cleanly on the old disk.
2. Move the entire `Hime` directory tree (including `modelle/`, `data/`, `Conda/`, and the `.claude/` worktrees) to the new disk path.
3. Set the `HIME_*` environment variables on the new disk to point at the moved tree.
4. Run `python scripts/verify_migration.py` and confirm 23 checks, 0 failures.
5. Start the backend, then restart training. Confirm checkpoints resume correctly.
6. Run `pytest app/backend/tests/` — expect 85 passed, 1 skipped (current `main` baseline).
7. Pick WS2 back up at Task 3 in the `v1.2.1-ws2` worktree (see "Resuming WS2" section below).

---

## Pre-Migration Checklist (do these on the OLD disk before unplugging)

- [ ] **Confirm baseline.** Run `conda run -n hime python scripts/verify_migration.py`. Expect 23 checks, 0 failures (matches `docs/superpowers/migration/2026-04-08-pre-migration-verify.txt`).
- [ ] **Stop training cleanly.** Identify the training PIDs:
  ```bash
  conda run -n hime python -c "import psutil; print([p.pid for p in psutil.process_iter(['cmdline']) if any('train_hime' in str(c) for c in (p.info['cmdline'] or []))])"
  ```
  At pre-migration time the training had 6 PIDs (Qwen2.5-32B-Instruct LoRA). Use the auto-resume wrapper's signal handling — send SIGTERM to the parent process group, do NOT kill -9. The trainer will save its current step and checkpoint cleanly.
- [ ] **Verify the most recent checkpoint exists.** Look in `modelle/lora/Qwen2.5-32B-Instruct/checkpoint/`. The folder name should look like `checkpoint-<step>`. Note the step number — you will compare against it after restart.
- [ ] **Confirm `smart_stop_state.json` is fresh.** `modelle/lora/Qwen2.5-32B-Instruct/smart_stop_state.json` should have a recent `mtime`. Note the mtime.
- [ ] **Stop the FastAPI backend.** If running, kill the `python run.py` process. The lock file at `app/backend/hime-backend.lock` will be released.
- [ ] **Stop any inference servers** (llama.cpp / vllm) on ports 8001-8005 and 18420.
- [ ] **Commit and push any uncommitted work you want to keep.** As of pre-migration time, the WS2 worktree has commits `47311839` (T1 — DB migrations) and `669676b9` (T2 — config) on branch `v1.2.1-ws2`. Push to remote if you have one.
  ```bash
  git -C C:\Projekte\Hime\.claude\worktrees\v1.2.1-ws2 log --oneline -5
  git -C C:\Projekte\Hime\.claude\worktrees\v1.2.1-ws2 push origin v1.2.1-ws2  # if you have a remote
  ```
- [ ] **List all worktrees** and write down their paths so you can verify them on the new disk:
  ```bash
  git -C C:\Projekte\Hime worktree list
  ```
  Pre-migration state has: `main`, `v1.2.1-ws1`, `v1.2.1-ws4`, `v1.2.1-ws2`, plus two stale `agent-*` worktrees (do not touch).

---

## Migration Execution

### Step 1: Move the tree

Move the entire `C:\Projekte\Hime\` directory to the new location. Whatever you call it, the new path is referred to as `<NEW_ROOT>` below.

**Critical:** Do NOT split the tree. The `Conda/` env, `modelle/`, `data/`, `app/`, `.claude/`, and `scripts/` directories must all live together under `<NEW_ROOT>` because the file paths embedded in `Conda/envs/hime/Lib/site-packages/...` and the conda env itself will break otherwise.

If you can't keep the conda env on the new disk (e.g., the new disk is too small), you will need to recreate it from scratch on the new disk:
```bash
conda env create -n hime -f environment.yml  # if you have one
# OR
conda create -n hime python=3.11
conda activate hime
pip install -r app/backend/requirements.txt  # or pyproject.toml deps
```
Be aware: a conda env recreation may pull in different versions of `transformers`/`torch` than the live training was using. Compare against `docs/superpowers/migration/2026-04-08-pre-migration-verify.txt` does NOT cover this. **If you must recreate, freeze the old env first** with `conda run -n hime pip freeze > old_env_freeze.txt` so you can pin exact versions on the new install.

### Step 2: Update git worktree paths

Worktrees record absolute paths in `.git/worktrees/*/gitdir`. After moving, repair them:

```bash
cd <NEW_ROOT>
git worktree repair
git worktree list
```

`git worktree repair` is the canonical fix and should re-link all worktrees to the new paths automatically.

### Step 3: Set environment variables

Set these in your shell profile, system environment variables panel, or a `.env` loader. **All nine** should point under `<NEW_ROOT>`:

```bash
HIME_PROJECT_ROOT=<NEW_ROOT>
HIME_DATA_DIR=<NEW_ROOT>\data
HIME_MODELS_DIR=<NEW_ROOT>\modelle
HIME_LOGS_DIR=<NEW_ROOT>\app\backend\logs
HIME_EPUB_WATCH_DIR=<NEW_ROOT>\data\epubs
HIME_TRAINING_DATA_DIR=<NEW_ROOT>\data\training
HIME_SCRIPTS_DIR=<NEW_ROOT>\scripts
HIME_EMBEDDINGS_DIR=<NEW_ROOT>\modelle\embeddings
HIME_RAG_DIR=<NEW_ROOT>\data\rag
```

You can also leave them unset and let `paths.py` auto-detect from `Path(__file__).resolve().parents[4]` — this works when the project root is detectable from the running script's location. **Setting them explicitly is safer** because it avoids surprises if you ever invoke a script from outside the tree.

### Step 4: Update `.env` (if used)

Copy your old `app/backend/.env` to the new path. If the old `.env` had any absolute paths (e.g., `HIME_DATA_DIR=C:\Projekte\Hime\data`), update them to the new root.

### Step 5: Run the verifier

```bash
cd <NEW_ROOT>
conda run -n hime python scripts/verify_migration.py
```

**Expected output (with HIME_* set):**
- 16 `[OK]` checks
- 7 `[WARN]` checks (only `EMBEDDINGS_DIR` and `RAG_DIR` for path missing — they don't exist until first use)
- 0 `[FAIL]` checks
- `Total: 23 checks, 0 failures`

**Expected output (with HIME_* unset, defaults active):**
- 14 `[OK]` checks
- 9 `[WARN]` checks (all 9 env vars say "unset - using default", plus EMBEDDINGS_DIR/RAG_DIR if they don't exist yet — wait, that's 11 WARNs in this case)
- 0 `[FAIL]` checks
- `Total: 23 checks, 0 failures`

If you see any `[FAIL]`, jump to the **Troubleshooting** section below.

### Step 6: Restart training

```bash
cd <NEW_ROOT>
conda run -n hime python scripts/train_with_resume.py --model-name Qwen2.5-32B-Instruct
```

The auto-resume wrapper will scan `modelle/lora/Qwen2.5-32B-Instruct/checkpoint/`, find the most recent valid checkpoint, and continue from there. Verify in the logs that the resumed step matches the step number you noted in the pre-migration checklist.

If `train_with_resume.py` exits non-zero or doesn't find the checkpoint, investigate before retrying — do NOT use `--from-scratch` or any flag that would discard the checkpoint without a deliberate decision.

### Step 7: Restart the backend

```bash
cd <NEW_ROOT>\app\backend
conda run -n hime python run.py
```

It should bind to `127.0.0.1:18420` (or the next free port in 18420-18430). Look for the lock file at `<NEW_ROOT>\app\backend\hime-backend.lock`.

### Step 8: Run the test suite

```bash
cd <NEW_ROOT>
conda run -n hime python -m pytest app/backend/tests/ -q
```

**Expected on `main`:** 85 passed, 1 skipped.
**Expected on `v1.2.1-ws2`:** 90 passed, 1 skipped (the WS2 T1 migrations added 5 tests).

### Step 9: EPUB watch folder rescan

Per `2026-04-08-v1.2.1-handoff-to-ws2-ws3.md`, the v1.2.0 EPUB auto-import was silently broken until WS4 fixed `epub_service._validate_epub_path`. After migration, manually trigger a rescan to pick up any EPUBs that were rejected during the regression window:

```bash
curl -X POST http://127.0.0.1:18420/api/v1/epub/scan
```

(Verify the exact endpoint path against `app/backend/app/routers/epub.py` — if it differs, use the correct path.)

---

## Troubleshooting

The verifier reports failures in clear categories. Map each `[FAIL]` to the section below.

### `[FAIL] env:HIME_*`

These checks always WARN (never FAIL) — if you see FAIL on env, you've hit a bug in the verifier itself. Re-read `scripts/verify_migration.py:46-63` and look for changes.

### `[FAIL] import:app.core.paths`

Python can't import `app.core.paths`. Most likely causes:
- The `Conda/envs/hime/` directory was not moved to `<NEW_ROOT>`. Re-check Step 1.
- The conda env itself is broken (rare). Try `conda run -n hime python -c "import sys; print(sys.executable)"` — should print the new disk path.
- `sys.path.insert(0, str(PROJECT_ROOT / "app" / "backend"))` at the top of `verify_migration.py` couldn't find `app/backend`. Confirm the directory exists at `<NEW_ROOT>\app\backend`.

### `[FAIL] path:PROJECT_ROOT` (or DATA_DIR, MODELS_DIR, etc.)

The path doesn't exist on disk. Most likely causes:
- The directory wasn't moved. Verify with `dir <NEW_ROOT>\data` (or whichever path failed).
- The `HIME_*` env var points at the wrong place. Re-read Step 3 and confirm the env var matches the actual moved location.
- Typo in the env var (Windows backslashes vs forward slashes — both should work, but mixing them in a single path can confuse `Path()`).

`LOGS_DIR`, `EMBEDDINGS_DIR`, `RAG_DIR`, and `TRAINING_DATA_DIR` always WARN if missing — these are created on first use. Don't worry about WARNs on these four.

### `[FAIL] training_config.json`

`scripts/training_config.json` is missing or unparseable. Causes:
- File wasn't moved (rare — it's tiny and lives under `scripts/`).
- File got corrupted during the move. Restore from a backup or from git: `git -C <NEW_ROOT> checkout scripts/training_config.json`.

### `[FAIL] scripts hardcoded paths`

Some script under `scripts/` contains a literal `C:\Projekte\Hime` or `C:/Projekte/Hime` outside of comments. WS4 already cleaned all known instances — if this fires post-migration, something accidentally re-introduced one. Find the offending file from the FAIL message and grep:

```bash
grep -n "C:[\\\\/]Projekte[\\\\/]Hime" <NEW_ROOT>\scripts\<filename>.py
```

Fix by replacing the literal with `Path(os.environ.get("HIME_PROJECT_ROOT") or Path(__file__).resolve().parent.parent)` or equivalent.

### `[FAIL] lib.rs hardcoded path`

`app/frontend/src-tauri/src/lib.rs` contains a literal old path. WS4 already removed this. If it returns post-migration, check whether the move accidentally restored an older version. Fix by editing `lib.rs` to resolve the path from `HIME_PROJECT_ROOT` env var (see WS4 changes for the pattern).

### `[FAIL] train_with_resume.py --dry-run` (exit non-zero or timeout)

The dry-run probe failed. Causes:
- The script can't find its imports. Most likely the conda env wasn't moved correctly — see `import:app.core.paths` troubleshooting.
- The script hit a path that no longer exists. Check the stderr in the FAIL message.
- Timeout: the dry-run took >15 seconds, which usually means the script hung on a network lookup or filesystem operation. Check for blocked HuggingFace download attempts (the script should NOT need network access in dry-run mode — if it does, something is wrong).
- If you can't fix it immediately and need to verify the rest of the system, set `HIME_SKIP_TRAINING_PROBE=1` to skip this check temporarily, then come back to it.

### Verifier hangs

Press Ctrl-C, then re-run with `HIME_SKIP_TRAINING_PROBE=1` to bypass the train_with_resume probe (it has a 15s timeout but on a slow new disk it might still take longer). If the verifier itself hangs (not the probe), investigate `app/backend/app/core/paths.py` — it shouldn't hang on import.

---

## Resuming WS2 (after migration is verified)

WS2 was paused at the end of T2. State at pause time:

| Item | Value |
|---|---|
| Worktree | `<OLD_ROOT>\.claude\worktrees\v1.2.1-ws2` |
| Branch | `v1.2.1-ws2` |
| Last commit | `669676b942fafd12b5dcfb7552508ecad4cecef0` (T2: config + .env.example) |
| Tasks completed | T1 (DB migrations), T2 (config) |
| Tasks deferred | T3 (deps), T4 (Lexicon), T5 (/lexicon router) — all blocked on jamdict-data |
| Next live task | T6 (ReaderPanel + 6 persona prompt templates) |
| Test baseline | 90 passed, 1 skipped on `v1.2.1-ws2` (vs. 85+1 on `main`) |

After migration:

1. `cd <NEW_ROOT>\.claude\worktrees\v1.2.1-ws2`
2. Confirm branch and HEAD: `git status && git log --oneline -3`
3. Run baseline: `conda run -n hime python -m pytest app/backend/tests/ -q` → expect 90 passed, 1 skipped
4. Decide whether to attempt T3 (jamdict-data) again — see workarounds below — or skip straight to T6 and come back to T3-T5 later.
5. The plan file is `docs/superpowers/plans/2026-04-08-v1.2.1-ws2-pipeline-extensions.md`. Tasks T6-T21 follow the same structure as T1-T2 and are independent of the lexicon block (the pipeline integration in T20 already has graceful degradation if `lexicon_anchor` is empty).

The two milestone gates from the original session still apply:
- After T10 (GlossaryService), report and wait
- After T18 (RAG retriever), report and wait — before T20 touches `pipeline/runner.py`

---

## jamdict-data Workaround Options (for when WS2 T3 is reopened)

The bug: `jamdict-data` (versions 1.0 and 1.5 — only two on PyPI) fails to install on Windows. Its `setup.py` tries to unpack `jamdict.db.xz` → `jamdict.db` during metadata generation, and Windows file locking on the `.xz` file prevents the unpacking from completing. The error is `WinError 32: The process cannot access the file because it is being used by another process`. Reproducible on both versions, regardless of `--no-cache-dir`.

### Option 1: Manual bypass (recommended for first attempt post-migration)

Pre-extract the database file so `setup.py` finds it already in place and skips its broken extraction logic.

```bash
# 1. Download the source tarball without installing
cd %TEMP%
conda run -n hime pip download --no-deps --no-build-isolation jamdict-data==1.5
# 2. Extract
mkdir jamdict-data-src
tar -xzf jamdict_data-1.5.tar.gz -C jamdict-data-src
cd jamdict-data-src\jamdict_data-1.5
# 3. Pre-decompress the .xz to .db using 7zip or python's lzma
conda run -n hime python -c "import lzma; open('jamdict_data/jamdict.db','wb').write(lzma.open('jamdict_data/jamdict.db.xz','rb').read())"
# 4. Install from the patched directory
conda run -n hime pip install --no-build-isolation .
```

If `setup.py` skips its extraction step because the `.db` file already exists, the install will succeed. If it still tries to re-unpack (and fails), proceed to Option 2.

**Risk:** This produces a non-reproducible install. Document the steps in the .env or in this runbook so a future migration can repeat them.

### Option 2: Patch the setup.py

Clone the source manually, fix the bug in `setup.py`, install from the patched source.

```bash
# 1. Clone or download the source as in Option 1
# 2. Open jamdict-data-src/jamdict_data-1.5/setup.py
# 3. Find the unpack logic (search for "Unpacking database from")
# 4. Wrap the .xz read in a `with lzma.open(...) as f:` block to ensure
#    the file handle is closed before the unlink (or before pip's metadata
#    generator tries to re-process the directory).
# 5. pip install --no-build-isolation .
```

A possible fix (untested — verify against the actual `setup.py` content first):

```python
# Before (broken):
xz_path = 'jamdict_data/jamdict.db.xz'
db_path = 'jamdict_data/jamdict.db'
data = lzma.open(xz_path).read()
open(db_path, 'wb').write(data)

# After (fixed):
import lzma
xz_path = 'jamdict_data/jamdict.db.xz'
db_path = 'jamdict_data/jamdict.db'
with lzma.open(xz_path, 'rb') as src, open(db_path, 'wb') as dst:
    dst.write(src.read())
```

Consider submitting the fix upstream as a PR — the maintainer may not realize Windows users hit this.

### Option 3: Skip jamdict, accept reduced LexiconService

Implement T4 with MeCab only (tokenization + POS tags + base form lookup, no JMdict glosses). Update the test plan:

- Remove `test_known_word_has_glosses` (cannot pass without a real dictionary).
- Keep `test_translate_returns_lexicon_result`, `test_unknown_token_listed`, `test_literal_translation_is_string`, `test_confidence_in_range`, `test_empty_input_returns_empty_result`.
- The `LexiconResult.literal_translation` becomes a space-joined list of base forms, which is less useful as a "literal translation anchor" but still gives the consensus merger a per-token segmentation it can compare against the model outputs for completeness.

This is a real plan deviation. Do not adopt without confirming with the user.

### Option 4: Use a different JMdict source

Download JMdict XML directly from EDRDG (`https://www.edrdg.org/jmdict/edict_doc.html`), parse it ourselves into a SQLite store under `data/lexicon/jmdict.db`, and replace the `jamdict` calls in `LexiconService` with our own lookup function. Significant scope creep — adds a parser, a builder script, and a runtime query helper. Not recommended unless Options 1 and 2 both fail.

### Option 5: Defer T3-T5 indefinitely

Skip the lexicon stack from v1.2.1 entirely. T20's pipeline integration already gracefully degrades if `lexicon_anchor` is empty — no other WS2 task hard-depends on the lexicon. The only loss is one of three "completeness anchors" in Stage 1; the consensus merger still has the three Stage 1 model outputs to work with.

**Honest assessment:** The lexicon anchor is a "nice to have" not a "must have." If Options 1 and 2 fail and you don't want to invest in Option 4, deferring is the right call.

---

## Files this runbook references

- `docs/superpowers/migration/2026-04-08-pre-migration-verify.txt` — known-good baseline
- `docs/superpowers/plans/2026-04-08-v1.2.1-handoff-to-ws2-ws3.md` — pre-WS2 handoff context
- `docs/superpowers/plans/2026-04-08-v1.2.1-ws2-pipeline-extensions.md` — WS2 plan with all 21 tasks
- `scripts/verify_migration.py` — the validator
- `scripts/train_with_resume.py` — auto-resume wrapper for training
- `app/backend/app/core/paths.py` — central path resolution
- `V121_HANDOFF.md` (repo root) — WS1+WS4 handoff details

---

## After successful migration, update this runbook

When the migration is complete and verified:

1. Append a "Migration log" section with: date, new root path, any deviations from this runbook, and the final verifier output.
2. If you found and fixed any new issues, add a "Lessons learned" subsection so the next migration is easier.
3. Commit this file to the repo so it's preserved.
