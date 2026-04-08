# V1.2.1 Workstream Handoffs

## WS4 — Security & Migration Cleanup
- ✅ EPUB `import_epub()` validates path against EPUB_WATCH_DIR by default (WS4 T2 commit d2da91b + b6658a8)
- ✅ 11 standalone scripts no longer reference `C:\Projekte\Hime` (WS4 T4-T6 commits c378d5f + 0f20037)
- ✅ Tauri `lib.rs` dev-mode lock path is HIME_PROJECT_ROOT-driven with binary-relative fallback (WS4 T3 commit fa110da)
- ✅ `paths.py` has EMBEDDINGS_DIR and RAG_DIR (WS4 T1 commit ea3ad12 + 8255c5c)
- ✅ `scripts/verify_migration.py` available for post-migration validation (WS4 T9 + T10 commits 5ec1ff0 + 0e4c0e1)
- ⚠️ **Latent v1.2.0 bug discovered and fixed during WS4 T2:** `epub_service.py` `_validate_epub_path()` used `Path()` without importing `pathlib.Path`. Every call from `scan_watch_folder()` was crashing silently inside its `try/except Exception`. **This means `scan_watch_folder()` has been rejecting every EPUB since v1.2.0 merged — auto-import on startup has been broken.** After merging WS4 to main, the user should run a manual rescan of the EPUB watch folder to pick up any previously-rejected imports. 21 EPUBs currently sit in `data/epubs/`.
- ⚠️ **Conda env dev deps installed:** `pytest-asyncio` and `aiosqlite` were listed in `pyproject.toml` but not installed. WS4 T2 installed them via pip. This affects ALL worktrees that use the `hime` env.
- ⚠️ **Tauri dev-mode fallback uses `current_exe()`**, which points to the cargo target dir (not the source tree). Devs MUST set `HIME_PROJECT_ROOT` before running `npm run tauri dev`. Add to setup docs.
- ⚠️ **`Path(settings.<x>)` indirections** in `training_monitor.py` and `training_runner.py` (14 occurrences) were NOT refactored — the v1.2.0 audit accepted them as acceptable indirection through `config.settings`. If disk migration requires direct `paths.py` imports everywhere, a follow-up pass would need to touch these.
- ⚠️ **Cargo.lock and `gen/schemas/*.json` may show as modified** in the worktree after a `cargo check` run. These are build artifacts and should not be committed. WS4 T11 cargo check (Step 7) may leave them dirty — they can be safely discarded with `git restore`.
