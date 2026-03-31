# Process Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Hime from colliding with other Tauri apps (specifically Sumi) by fully isolating its ports, process group, WebView2 data directory, and enforcing a single-instance lockfile.

**Architecture:** Hime's FastAPI sidecar moves from the generic port 8000 to the Hime-specific range 18420–18519. A JSON lockfile (`hime-backend.lock`) replaces the plain `.runtime_port` file and carries both port and PID. A separate `hime.lock` file prevents dual-instance launches. The Windows Job Object (already present) gets a unique name. The Tauri WebView2 data dir is set explicitly to `%APPDATA%\dev.lfl.hime\Hime-WebView2`, and the app identifier is changed from `dev.hime.app` → `dev.lfl.hime` with an automatic one-time data migration.

**Tech Stack:** Python 3.11 / FastAPI / Pydantic-settings, Rust / Tauri 2, React 19 / TypeScript, windows-rs 0.61

---

## File Map

| File | Change |
|------|--------|
| `app/backend/app/config.py` | port default 8000 → 18420 |
| `app/backend/run.py` | `.runtime_port` (plain int) → `hime-backend.lock` (JSON {port, pid}) |
| `app/frontend/src/api/client.ts` | read `hime-backend.lock`, parse JSON, update probe range |
| `app/frontend/src-tauri/src/lib.rs` | poll `hime-backend.lock`; add single-instance lockfile; name job object; create window programmatically with `data_directory` |
| `app/frontend/src-tauri/tauri.conf.json` | identifier `dev.lfl.hime`; remove `windows` array (window created in Rust) |

---

## Task 1: Change Default Port to 18420

**Files:**
- Modify: `app/backend/app/config.py` (line 12)

- [ ] **Step 1: Update the port default**

In `app/backend/app/config.py`, change line 12 from:
```python
    port: int = 8000  # preferred port; run.py will scan upward if it's busy
```
to:
```python
    port: int = 18420  # Hime-specific range (18420-18519) — avoids collision with other local apps
```

- [ ] **Step 2: Verify the setting loads correctly**

```bash
cd C:/Projekte/Hime/app/backend
python -c "from app.config import settings; assert settings.port == 18420, f'Expected 18420, got {settings.port}'; print('OK: port =', settings.port)"
```

Expected output: `OK: port = 18420`

- [ ] **Step 3: Commit**

```bash
git add app/backend/app/config.py
git commit -m "fix(backend): move default port to Hime-specific range 18420"
```

---

## Task 2: Backend Lockfile — Python (`run.py`)

Replace the plain `.runtime_port` text file with `hime-backend.lock` containing JSON `{"port": N, "pid": N}`. The Rust health-check still polls for file existence; the frontend reads port + pid from the JSON.

**Files:**
- Modify: `app/backend/run.py`

- [ ] **Step 1: Add `import json` and rename constants**

At the top of `run.py`, `json` is not yet imported. Add it to the existing stdlib imports block (after `import os`):

```python
import json
```

Change line 58:
```python
_RUNTIME_PORT_FILE = _DATA_DIR / ".runtime_port"
```
to:
```python
_BACKEND_LOCK_FILE = _DATA_DIR / "hime-backend.lock"
```

- [ ] **Step 2: Replace write/clear helpers**

Replace the two helper functions (lines 63–68):

```python
def _write_runtime_port(port: int) -> None:
    _RUNTIME_PORT_FILE.write_text(str(port), encoding="utf-8")


def _clear_runtime_port() -> None:
    _RUNTIME_PORT_FILE.unlink(missing_ok=True)
```

with:

```python
def _write_backend_lock(port: int) -> None:
    _BACKEND_LOCK_FILE.write_text(
        json.dumps({"port": port, "pid": os.getpid()}),
        encoding="utf-8",
    )


def _clear_backend_lock() -> None:
    _BACKEND_LOCK_FILE.unlink(missing_ok=True)
```

- [ ] **Step 3: Update call sites in `__main__` block**

In the `if __name__ == "__main__":` block, change:
```python
    _write_runtime_port(port)
```
to:
```python
    _write_backend_lock(port)
```

In the `finally:` block, change:
```python
        _clear_runtime_port()
```
to:
```python
        _clear_backend_lock()
```

- [ ] **Step 4: Update the log debug line**

Change line with `_log.debug("runtime_port -> %s", ...)`:
```python
    _log.debug("backend_lock -> %s", _BACKEND_LOCK_FILE)
```

- [ ] **Step 5: Update the top-of-file comment block**

Change the comment on line 11:
```
  - The chosen port is written to .runtime_port so the frontend can read it
    instead of relying on a hardcoded value.
```
to:
```
  - The chosen port is written to hime-backend.lock (JSON {port, pid}) so
    the frontend can read it instead of relying on a hardcoded value.
```

- [ ] **Step 6: Verify lockfile is written on startup**

```bash
cd C:/Projekte/Hime/app/backend
python run.py &
sleep 3
cat hime-backend.lock
```

Expected: `{"port": 18420, "pid": <some number>}`

Kill the background process after verification: `kill %1`

- [ ] **Step 7: Commit**

```bash
git add app/backend/run.py
git commit -m "fix(backend): replace .runtime_port with hime-backend.lock (JSON port+pid)"
```

---

## Task 3: Frontend Port Discovery Update (`client.ts`)

The frontend reads `.runtime_port` as plain text. Update it to read `hime-backend.lock` as JSON, and update the probe fallback range to match the new port range.

**Files:**
- Modify: `app/frontend/src/api/client.ts`

- [ ] **Step 1: Update the header comment (line 8)**

Change:
```typescript
//   getPort() reads .runtime_port from %APPDATA%\dev.hime.app\ via
```
to:
```typescript
//   getPort() reads hime-backend.lock from %APPDATA%\dev.lfl.hime\ via
```

- [ ] **Step 2: Change filename and add JSON parsing (lines 40–55)**

Replace the entire `try` block in `getPort()` that reads the file:

```typescript
  // 1. Read from AppData dir (matches where run.py --data-dir writes it)
  try {
    const { appDataDir } = await import('@tauri-apps/api/path')
    const dir = await appDataDir()
    const content = await tryReadFile(`${dir}.runtime_port`)
    if (content) {
      const port = parseInt(content.trim(), 10)
      if (!isNaN(port)) {
        console.log(`[client] Port ${port} from appDataDir`)
        cachedPort = port
        return port
      }
    }
  } catch (err) {
    console.debug('[client] appDataDir() unavailable:', err)
  }
```

with:

```typescript
  // 1. Read from AppData dir (matches where run.py --data-dir writes it)
  try {
    const { appDataDir } = await import('@tauri-apps/api/path')
    const dir = await appDataDir()
    const content = await tryReadFile(`${dir}hime-backend.lock`)
    if (content) {
      const lock = JSON.parse(content) as { port?: number; pid?: number }
      const port = lock.port
      if (typeof port === 'number' && !isNaN(port)) {
        console.log(`[client] Port ${port} (pid ${lock.pid ?? '?'}) from hime-backend.lock`)
        cachedPort = port
        return port
      }
    }
  } catch (err) {
    console.debug('[client] hime-backend.lock unavailable:', err)
  }
```

- [ ] **Step 3: Update the probe fallback range and warning (lines 57–70)**

Replace:
```typescript
  console.warn('[client] Could not read .runtime_port — probing 8000–8010')

  // 2. Probe ports sequentially as final fallback
  for (let port = 8000; port <= 8010; port++) {
    if (await probePort(port)) {
      console.log(`[client] Backend found via probe at port ${port}`)
      cachedPort = port
      return port
    }
  }

  console.error('[client] No backend found on 8000–8010 — defaulting to 8004')
  cachedPort = 8004
  return 8004
```

with:

```typescript
  console.warn('[client] Could not read hime-backend.lock — probing 18420–18430')

  // 2. Probe ports sequentially as final fallback
  for (let port = 18420; port <= 18430; port++) {
    if (await probePort(port)) {
      console.log(`[client] Backend found via probe at port ${port}`)
      cachedPort = port
      return port
    }
  }

  console.error('[client] No backend found on 18420–18430 — defaulting to 18420')
  cachedPort = 18420
  return 18420
```

- [ ] **Step 4: Update the error fallback in `getBaseUrl` (line 87)**

Change:
```typescript
    return 'http://127.0.0.1:8004'
```
to:
```typescript
    return 'http://127.0.0.1:18420'
```

- [ ] **Step 5: Build the frontend to confirm no TypeScript errors**

```bash
cd C:/Projekte/Hime/app/frontend
npm run build 2>&1 | tail -20
```

Expected: build succeeds with no errors.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/api/client.ts
git commit -m "fix(frontend): read hime-backend.lock (JSON), update probe range to 18420-18430"
```

---

## Task 4: Rust Health-Check Filename Update (`lib.rs`)

The Rust setup loop polls for the file that signals the backend is ready. Update the filename to `hime-backend.lock`.

**Files:**
- Modify: `app/frontend/src-tauri/src/lib.rs`

- [ ] **Step 1: Update the release-mode path**

Find and replace:
```rust
            #[cfg(not(debug_assertions))]
            let runtime_port_path = app_data_dir.join(".runtime_port");
```
with:
```rust
            #[cfg(not(debug_assertions))]
            let runtime_port_path = app_data_dir.join("hime-backend.lock");
```

- [ ] **Step 2: Update the dev-mode path**

Find and replace:
```rust
            #[cfg(debug_assertions)]
            let runtime_port_path = std::path::PathBuf::from(
                r"C:\Projekte\Hime\app\backend\.runtime_port",
            );
```
with:
```rust
            #[cfg(debug_assertions)]
            let runtime_port_path = std::path::PathBuf::from(
                r"C:\Projekte\Hime\app\backend\hime-backend.lock",
            );
```

- [ ] **Step 3: Compile to check for errors**

```bash
cd C:/Projekte/Hime/app/frontend/src-tauri
cargo check 2>&1 | tail -20
```

Expected: `Finished` with no errors. (Warnings about unused variables are OK at this stage.)

- [ ] **Step 4: Commit**

```bash
git add app/frontend/src-tauri/src/lib.rs
git commit -m "fix(tauri): poll hime-backend.lock instead of .runtime_port"
```

---

## Task 5: Single-Instance Lockfile (`lib.rs`)

Prevent two Hime instances from running simultaneously. On startup, check `hime.lock` for a live PID; on shutdown, delete it.

**Files:**
- Modify: `app/frontend/src-tauri/src/lib.rs`

- [ ] **Step 1: Add `HimeLockPath` state struct above `pub fn run()`**

After the `type LogFile = ...` line and the `fn log_line(...)` function, add:

```rust
/// Stores the path to the single-instance lockfile so the window-destroy
/// handler can delete it on clean shutdown.
struct HimeLockPath(std::path::PathBuf);
```

- [ ] **Step 2: Add `is_process_alive` helper below `HimeLockPath`**

```rust
/// Returns true if a process with the given PID is currently running.
#[cfg(target_os = "windows")]
fn is_process_alive(pid: u32) -> bool {
    use windows::Win32::Foundation::CloseHandle;
    use windows::Win32::System::Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION};
    unsafe {
        match OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid) {
            Ok(handle) => {
                let _ = CloseHandle(handle);
                true
            }
            Err(_) => false,
        }
    }
}

#[cfg(not(target_os = "windows"))]
fn is_process_alive(_pid: u32) -> bool {
    false // Hime is Windows-only; stub for non-Windows compilation
}
```

- [ ] **Step 3: Add the lockfile check in `setup`, right after `logs_dir` is created**

Insert the following block after `fs::create_dir_all(&logs_dir).ok();` and before the `log_line` call:

```rust
            // ── Single-instance lockfile ──────────────────────────────────
            let hime_lock_path = app_data_dir.join("hime.lock");
            if hime_lock_path.exists() {
                let stale = if let Ok(content) = fs::read_to_string(&hime_lock_path) {
                    match content.trim().parse::<u32>() {
                        Ok(pid) if is_process_alive(pid) => {
                            app.dialog()
                                .message(
                                    "Hime läuft bereits.\n\n\
                                     Bitte schließe die andere Instanz und versuche es erneut.",
                                )
                                .title("Hime — Bereits geöffnet")
                                .blocking_show();
                            std::process::exit(0);
                        }
                        _ => true, // dead PID or unparseable → stale file
                    }
                } else {
                    true // unreadable → stale
                };
                if stale {
                    let _ = fs::remove_file(&hime_lock_path);
                }
            }
            let _ = fs::write(&hime_lock_path, std::process::id().to_string());
            app.manage(HimeLockPath(hime_lock_path));
```

- [ ] **Step 4: Clean up the lockfile in `on_window_event`**

In the `on_window_event` closure, add lockfile cleanup BEFORE the existing child-kill block:

```rust
        if let tauri::WindowEvent::Destroyed = event {
            // Remove single-instance lockfile so the next launch is unblocked
            if let Some(lock) = window.app_handle().try_state::<HimeLockPath>() {
                let _ = std::fs::remove_file(&lock.0);
            }

            type ChildMutex =
                Mutex<Option<tauri_plugin_shell::process::CommandChild>>;
            if let Some(mutex) = window.app_handle().try_state::<ChildMutex>() {
                if let Ok(mut guard) = mutex.lock() {
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                    }
                }
            }
        }
```

- [ ] **Step 5: Compile**

```bash
cd C:/Projekte/Hime/app/frontend/src-tauri
cargo check 2>&1 | tail -30
```

Expected: `Finished` with no errors.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src-tauri/src/lib.rs
git commit -m "fix(tauri): add single-instance lockfile (hime.lock) to prevent duplicate launches"
```

---

## Task 6: Name the Windows Job Object (`lib.rs`)

The Job Object is already created with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` (which is correct). Give it a unique name so it can be identified in tools like Process Explorer and to avoid name collisions with other apps that also use unnamed job objects.

**Files:**
- Modify: `app/frontend/src-tauri/src/lib.rs`

- [ ] **Step 1: Replace anonymous `CreateJobObjectW` with named call**

Find this block inside `#[cfg(target_os = "windows")]`:
```rust
                    unsafe {
                        if let Ok(job) = CreateJobObjectW(None, None) {
```

Replace it with:

```rust
                    unsafe {
                        // Name the job object so it appears in Process Explorer
                        // and cannot be confused with job objects from other apps.
                        let job_name_str =
                            format!("HimeProcessGroup_{}\0", std::process::id());
                        let job_name_wide: Vec<u16> =
                            job_name_str.encode_utf16().collect();
                        // CreateJobObjectW second param: pass PCWSTR directly.
                        // If your windows-rs version wraps it in Option, use Some(...).
                        let job_pcwstr =
                            windows::core::PCWSTR(job_name_wide.as_ptr());
                        if let Ok(job) = CreateJobObjectW(None, job_pcwstr) {
```

> **Note:** In windows-rs 0.61 the second parameter of `CreateJobObjectW` may be
> `PCWSTR` or `Option<PCWSTR>`. If `cargo check` emits a type error, wrap in
> `Some(job_pcwstr)`. Either way, `job_name_wide` must remain alive until after
> the `CreateJobObjectW` call returns (it is on the stack, so this is automatic).

- [ ] **Step 2: Compile**

```bash
cd C:/Projekte/Hime/app/frontend/src-tauri
cargo check 2>&1 | tail -20
```

Expected: `Finished` with no errors. If you see a type error about the second arg, wrap `job_pcwstr` in `Some(...)`.

- [ ] **Step 3: Commit**

```bash
git add app/frontend/src-tauri/src/lib.rs
git commit -m "fix(tauri): name Windows Job Object HimeProcessGroup_{PID} for uniqueness"
```

---

## Task 7: WebView2 Data Isolation + Identifier Change

Two sub-goals in one coordinated task (they must ship together since the identifier change affects `app_data_dir`):

1. Change `identifier` in `tauri.conf.json` from `dev.hime.app` → `dev.lfl.hime`
2. Create the main window programmatically in Rust with an explicit `data_directory` so WebView2 caches are isolated from other Tauri apps
3. Add a one-time data migration so existing users don't lose their database and settings

> **Breaking change note:** The identifier change moves `%APPDATA%\dev.hime.app` to `%APPDATA%\dev.lfl.hime`. The migration code below handles this automatically on first launch.

**Files:**
- Modify: `app/frontend/src-tauri/tauri.conf.json`
- Modify: `app/frontend/src-tauri/src/lib.rs`

- [ ] **Step 1: Update the identifier in `tauri.conf.json`**

Change line 3:
```json
  "identifier": "dev.hime.app",
```
to:
```json
  "identifier": "dev.lfl.hime",
```

- [ ] **Step 2: Remove the `windows` array from `tauri.conf.json`**

Remove the entire `"windows": [...]` block from `"app"` so it reads:
```json
  "app": {
    "security": {
      "csp": null
    }
  },
```

The window will be created in Rust with the proper `data_directory`.

- [ ] **Step 3: Add migration + programmatic window creation to `lib.rs`**

In the `setup` closure, immediately after `let app_data_dir = ...` is resolved (before `let logs_dir = ...`), add the migration block:

```rust
            // ── One-time data migration: dev.hime.app → dev.lfl.hime ──────
            // After the identifier rename, app_data_dir now points to
            // %APPDATA%\dev.lfl.hime. Migrate the old directory if it exists
            // and the new one does not yet.
            #[cfg(target_os = "windows")]
            {
                let old_dir = std::path::PathBuf::from(
                    std::env::var("APPDATA").unwrap_or_default(),
                )
                .join("dev.hime.app");
                if old_dir.exists() && !app_data_dir.exists() {
                    match fs::rename(&old_dir, &app_data_dir) {
                        Ok(()) => {
                            // Can't call log_line yet (file not opened), print to stderr
                            eprintln!(
                                "[hime] migrated data dir: dev.hime.app → dev.lfl.hime"
                            );
                        }
                        Err(e) => {
                            eprintln!("[hime] migration failed (non-fatal): {e}");
                            // App will start fresh in the new location
                        }
                    }
                }
            }
```

- [ ] **Step 4: Create the main window programmatically with `data_directory`**

At the END of the `setup` closure, just before `Ok(())`, add:

```rust
            // ── Create main window with isolated WebView2 data directory ──
            {
                use tauri::{WebviewUrl, WebviewWindowBuilder};
                let webview_data = app_data_dir.join("Hime-WebView2");
                WebviewWindowBuilder::new(
                    app.handle(),
                    "main",
                    WebviewUrl::App("index.html".into()),
                )
                .title("Hime")
                .inner_size(1280.0, 800.0)
                .min_inner_size(900.0, 600.0)
                .resizable(true)
                .data_directory(webview_data)
                .build()
                .expect("Failed to create main window");
            }
```

- [ ] **Step 5: Compile**

```bash
cd C:/Projekte/Hime/app/frontend/src-tauri
cargo check 2>&1 | tail -30
```

Expected: `Finished` with no errors.

If you see: `method 'data_directory' not found` — check which Tauri version is in `Cargo.toml`. In Tauri 2 this method is on `WebviewWindowBuilder`. If you see `WebviewWindowBuilder::new` failing on types, verify the first arg is `app.handle()` (returns `&AppHandle`).

- [ ] **Step 6: Full build**

```bash
cd C:/Projekte/Hime/app/frontend
npm run tauri build 2>&1 | tail -40
```

Expected: binary produced without errors.

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src-tauri/tauri.conf.json app/frontend/src-tauri/src/lib.rs
git commit -m "fix(tauri): isolate WebView2 data dir, rename identifier to dev.lfl.hime, add migration"
```

---

## Task 8: End-to-End Verification

Verify that Hime and Sumi run side-by-side without interference.

**Files:** none (manual verification)

- [ ] **Step 1: Start Hime (production build)**

```
hime.exe
```

Confirm in `%APPDATA%\dev.lfl.hime\`:
- `hime.lock` exists and contains Hime's PID
- `hime-backend.lock` exists and contains `{"port": 18420, "pid": ...}`
- `Hime-WebView2\` directory exists

- [ ] **Step 2: Attempt to start a second Hime instance**

Launch `hime.exe` again. Expected: dialog "Hime — Bereits geöffnet" appears. Second instance exits. First instance continues running normally.

- [ ] **Step 3: Start Sumi**

Launch Sumi while Hime is running. Both apps must:
- Open their own windows without errors
- Operate independently
- Not steal each other's backend port

Verify Sumi still uses its own port (e.g. 8000 or whatever it was on). Hime is on 18420.

- [ ] **Step 4: Close Hime, verify cleanup**

Close Hime. Confirm:
- `hime.lock` is deleted
- `hime-backend.lock` is deleted (run.py `finally` block)
- No `hime-backend-x86_64-pc-windows-msvc.exe` or `python.exe` processes remain (Job Object killed them)

- [ ] **Step 5: Reopen Hime — must start cleanly**

Hime must start without "already running" dialog.

- [ ] **Step 6: Verify Task Manager shows Job Object**

Open Task Manager → Details tab → right-click a column header → "Select columns" → enable "Job". Hime's processes should show the same job name `HimeProcessGroup_<PID>`.

- [ ] **Step 7: Final commit + version bump**

```bash
cd C:/Projekte/Hime
python scripts/bump_version.py patch
git push && git push --tags
```

---

## Self-Review Checklist

| Spec requirement | Task |
|-----------------|------|
| Port range 18420–18430 | Task 1 + Task 3 (probe range) |
| Lockfile with port+PID | Task 2 (Python) + Task 4 (Rust filename) |
| Frontend reads port from lockfile | Task 3 |
| WebView2 data isolation | Task 7 |
| Unique identifier `dev.lfl.hime` | Task 7 |
| Named Job Object `HimeProcessGroup_{PID}` | Task 6 |
| `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` | Already in code ✓ |
| Single-instance lockfile `hime.lock` | Task 5 |
| SQLite path unique | Already `{data_dir}/hime.db` ✓ |
| IPC / named pipes | No Windows named pipes or mutexes found; Tauri IPC uses label "main" (unique per app) ✓ |
| Verification steps | Task 8 |
