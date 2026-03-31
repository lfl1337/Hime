use std::fs::{self, OpenOptions};
use std::io::Write;
use std::sync::{Arc, Mutex};
use tauri::{path::BaseDirectory, Emitter, Manager};
use tauri_plugin_dialog::DialogExt;

// ShellExt trait is only needed in release (sidecar) mode.
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::ShellExt;

// Shared log file handle — written by the sidecar stream task.
type LogFile = Arc<Mutex<Option<std::fs::File>>>;

fn log_line(log: &LogFile, line: &str) {
    if let Ok(mut guard) = log.lock() {
        if let Some(f) = guard.as_mut() {
            let _ = writeln!(f, "{line}");
            let _ = f.flush();
        }
    }
}

/// Stores the path to the single-instance lockfile so the window-destroy
/// handler can delete it on clean shutdown.
struct HimeLockPath(std::path::PathBuf);

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

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // ── Resolve runtime paths ──────────────────────────────────────
            let app_data_dir = app
                .path()
                .resolve("", BaseDirectory::AppData)
                .expect("Failed to resolve AppData dir");

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

            let logs_dir = app_data_dir.join("logs");
            fs::create_dir_all(&app_data_dir).ok();
            fs::create_dir_all(&logs_dir).ok();

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

            let log_path = logs_dir.join("backend.log");
            let log_path_str = log_path.to_string_lossy().to_string();
            let data_dir_str = app_data_dir.to_string_lossy().to_string();

            // ── Open log file (append — keeps history across restarts) ─────
            let log: LogFile = Arc::new(Mutex::new(
                OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(&log_path)
                    .ok(),
            ));

            log_line(&log, &format!("[hime] === startup === data_dir={data_dir_str}"));

            // ── RELEASE: spawn sidecar; DEV: connect to already-running backend
            #[cfg(not(debug_assertions))]
            {
                let spawn_result = app
                    .shell()
                    .sidecar("hime-backend")
                    .map(|cmd| cmd.args(["--data-dir", &data_dir_str]))
                    .and_then(|cmd| cmd.spawn());

                let (mut rx, child) = match spawn_result {
                    Ok(pair) => pair,
                    Err(e) => {
                        let msg = format!(
                            "Hime backend could not be started.\n\nError: {e}\n\nLog file:\n{log_path_str}"
                        );
                        log_line(&log, &format!("[hime] SPAWN ERROR: {e}"));
                        app.dialog()
                            .message(&msg)
                            .title("Hime — Startup Error")
                            .blocking_show();
                        return Err(e.into());
                    }
                };

                // Store child handle so on_window_event can kill it on close.
                let child_pid = child.pid();
                app.manage(Mutex::new(Some(child)));

                // Create a Windows Job Object so all child processes (backend + training)
                // are killed automatically when hime.exe exits.
                #[cfg(target_os = "windows")]
                {
                    use windows::Win32::System::JobObjects::{
                        AssignProcessToJobObject, CreateJobObjectW,
                        JobObjectExtendedLimitInformation, SetInformationJobObject,
                        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
                    };
                    use windows::Win32::System::Threading::{OpenProcess, PROCESS_ALL_ACCESS};

                    struct JobHandle(windows::Win32::Foundation::HANDLE);
                    unsafe impl Send for JobHandle {}
                    unsafe impl Sync for JobHandle {}

                    unsafe {
                        // Name the job object so it appears in Process Explorer
                        // and cannot be confused with job objects from other apps.
                        let job_name_str =
                            format!("HimeProcessGroup_{}\0", std::process::id());
                        let job_name_wide: Vec<u16> =
                            job_name_str.encode_utf16().collect();
                        // CreateJobObjectW second param is Option<PCWSTR> in windows-rs 0.61.
                        let job_pcwstr =
                            windows::core::PCWSTR(job_name_wide.as_ptr());
                        if let Ok(job) = CreateJobObjectW(None, Some(job_pcwstr)) {
                            let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
                            info.BasicLimitInformation.LimitFlags =
                                JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                            let _ = SetInformationJobObject(
                                job,
                                JobObjectExtendedLimitInformation,
                                &info as *const _ as *const std::ffi::c_void,
                                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                            );
                            if let Ok(proc_handle) =
                                OpenProcess(PROCESS_ALL_ACCESS, false, child_pid)
                            {
                                let _ = AssignProcessToJobObject(job, proc_handle);
                            }
                            // Keep the job handle alive — dropping it closes the job
                            app.manage(JobHandle(job));
                        }
                    }
                }

                // Stream sidecar stdout/stderr → log file
                let log_for_stream = Arc::clone(&log);
                tauri::async_runtime::spawn(async move {
                    use tauri_plugin_shell::process::CommandEvent;
                    while let Some(event) = rx.recv().await {
                        let line = match &event {
                            CommandEvent::Stdout(b) => {
                                format!("[OUT] {}", String::from_utf8_lossy(b).trim_end())
                            }
                            CommandEvent::Stderr(b) => {
                                format!("[ERR] {}", String::from_utf8_lossy(b).trim_end())
                            }
                            CommandEvent::Terminated(s) => format!("[EXIT] {s:?}"),
                            _ => continue,
                        };
                        eprintln!("{line}");
                        log_line(&log_for_stream, &line);
                        if matches!(event, CommandEvent::Terminated(_)) {
                            break;
                        }
                    }
                });
            }

            // Dev: no sidecar — register None so on_window_event try_state still works.
            #[cfg(debug_assertions)]
            {
                type Child = tauri_plugin_shell::process::CommandChild;
                app.manage(Mutex::new(None::<Child>));
                log_line(&log, "[hime] dev mode — sidecar skipped, connecting to external backend");
            }

            // ── Health check: wait up to 10 s for .runtime_port to appear ──
            // Release: backend writes the file to AppData.
            // Dev: backend writes it to app/backend/ in the source tree.
            let app_handle = app.handle().clone();

            #[cfg(not(debug_assertions))]
            let runtime_port_path = app_data_dir.join("hime-backend.lock");

            #[cfg(debug_assertions)]
            let runtime_port_path = std::path::PathBuf::from(
                r"C:\Projekte\Hime\app\backend\hime-backend.lock",
            );

            let log_path_for_check = log_path_str.clone();

            std::thread::spawn(move || {
                use std::time::Duration;
                let mut healthy = false;
                for _ in 0..20 {
                    // 20 × 500 ms = 10 s
                    std::thread::sleep(Duration::from_millis(500));
                    if runtime_port_path.exists() {
                        healthy = true;
                        break;
                    }
                }
                if healthy {
                    let _ = app_handle.emit("backend-ready", ());
                } else {
                    app_handle
                        .dialog()
                        .message(format!(
                            "Hime backend did not start within 10 seconds.\n\n\
                             The backend log may contain more details:\n\
                             {log_path_for_check}"
                        ))
                        .title("Hime — Startup Error")
                        .blocking_show();
                }
            });

            // 12-hour idle warning
            let log_for_idle = Arc::clone(&log);
            std::thread::spawn(move || {
                let start = std::time::Instant::now();
                loop {
                    std::thread::sleep(std::time::Duration::from_secs(3600)); // 1 h
                    let hours = start.elapsed().as_secs() / 3600;
                    if hours >= 12 {
                        log_line(
                            &log_for_idle,
                            "[hime] WARNING: App has been running for 12+ hours. Consider restarting to free memory.",
                        );
                        break;
                    }
                }
            });

            // ── Create main window with isolated WebView2 data directory ──
            {
                use tauri::{WebviewUrl, WebviewWindowBuilder};
                let webview_data = app_data_dir.join("Hime-WebView2");

                let win_builder = WebviewWindowBuilder::new(
                    app.handle(),
                    "main",
                    WebviewUrl::App("index.html".into()),
                )
                .title("Hime")
                .inner_size(1280.0, 800.0)
                .min_inner_size(900.0, 600.0)
                .resizable(true)
                .data_directory(webview_data);

                #[cfg(debug_assertions)]
                let win_builder = win_builder.devtools(true);

                win_builder.build().expect("Failed to create main window");
            }

            Ok(())
        })
        .on_window_event(|window, event| {
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
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
