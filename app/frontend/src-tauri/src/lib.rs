use tauri::{path::BaseDirectory, Manager};
use tauri_plugin_shell::ShellExt;

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // Resolve %APPDATA%\dev.hime.app\ and ensure it exists
            let app_data_dir = app
                .path()
                .resolve("", BaseDirectory::AppData)
                .expect("Failed to resolve AppData dir");
            std::fs::create_dir_all(&app_data_dir).ok();
            let data_dir_str = app_data_dir.to_string_lossy().to_string();

            // Spawn the Python backend sidecar, passing the data dir
            let sidecar = app
                .shell()
                .sidecar("hime-backend")
                .expect("hime-backend sidecar not configured in tauri.conf.json")
                .args(["--data-dir", &data_dir_str]);

            let (mut rx, child) = sidecar.spawn().expect("Failed to spawn hime-backend");

            // Store child handle so on_window_event can kill it on close
            app.manage(std::sync::Mutex::new(Some(child)));

            // Forward sidecar stdout/stderr to the Tauri process console
            tauri::async_runtime::spawn(async move {
                use tauri_plugin_shell::process::CommandEvent;
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            print!("[backend] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprint!("[backend:err] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Terminated(status) => {
                            eprintln!("[backend] process exited: {:?}", status);
                            break;
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                type ChildMutex = std::sync::Mutex<
                    Option<tauri_plugin_shell::process::CommandChild>,
                >;
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
