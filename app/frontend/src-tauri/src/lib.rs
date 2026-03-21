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

            let logs_dir = app_data_dir.join("logs");
            fs::create_dir_all(&logs_dir).ok();

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
                app.manage(Mutex::new(Some(child)));

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
            let runtime_port_path = app_data_dir.join(".runtime_port");

            #[cfg(debug_assertions)]
            let runtime_port_path = std::path::PathBuf::from(
                r"C:\Projekte\Hime\app\backend\.runtime_port",
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

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
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
