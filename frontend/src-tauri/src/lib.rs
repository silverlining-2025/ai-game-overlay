use tauri::Manager;
use std::sync::Mutex;

struct BackendProcess(Mutex<Option<std::process::Child>>);

/// Launch the Python backend and create the overlay window
#[tauri::command]
async fn start_companion(
    app: tauri::AppHandle,
    game: String,
    character: String,
    interval: f64,
) -> Result<(), String> {
    // Start Python backend — find the repo root (parent of frontend/)
    let repo_root = {
        let mut dir = std::env::current_exe()
            .unwrap_or_else(|_| std::env::current_dir().unwrap_or_default());
        // Walk up until we find "backend" directory
        loop {
            if dir.join("backend").is_dir() {
                break dir;
            }
            if !dir.pop() {
                // Fallback: try common dev path
                break std::path::PathBuf::from(r"C:\Dev\ai-game-overlay");
            }
        }
    };

    let backend = std::process::Command::new("python")
        .args([
            "-m", "backend.tools.web_overlay",
            "--game", &game,
            "--interval", &interval.to_string(),
            "--character", &character,
            "--port", "8080",
            "--headless",
            "--save-training",
        ])
        .current_dir(&repo_root)
        .spawn()
        .map_err(|e| format!("Failed to start Python backend: {}", e))?;

    // Store the process handle so we can kill it later
    let state = app.state::<BackendProcess>();
    *state.0.lock().unwrap() = Some(backend);

    // Hide config window
    if let Some(config_win) = app.get_webview_window("config") {
        let _ = config_win.hide();
    }

    // Check if overlay already exists
    if app.get_webview_window("overlay").is_some() {
        return Ok(());
    }

    // Create overlay window — NOT click-through so user can interact
    let overlay = tauri::WebviewWindowBuilder::new(
        &app,
        "overlay",
        tauri::WebviewUrl::App("index.html#overlay".into()),
    )
    .title("AI Companion Overlay")
    .transparent(true)
    .decorations(false)
    .always_on_top(true)
    .skip_taskbar(false)  // Show in taskbar so user can find it
    .resizable(false)
    .shadow(false)
    .inner_size(620.0, 320.0)
    .position(40.0, 40.0)
    .build()
    .map_err(|e| e.to_string())?;

    // Exclude overlay from screen capture (Windows only)
    #[cfg(windows)]
    {
        use windows::Win32::Foundation::HWND;
        use windows::Win32::UI::WindowsAndMessaging::{
            SetWindowDisplayAffinity, WDA_EXCLUDEFROMCAPTURE,
        };

        std::thread::sleep(std::time::Duration::from_millis(100));

        if let Ok(raw_hwnd) = overlay.hwnd() {
            unsafe {
                let hwnd: HWND = std::mem::transmute(raw_hwnd);
                let _ = SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE);
            }
        }
    }

    // Don't set click-through — let user interact with quit/config buttons
    let _ = overlay;

    Ok(())
}

/// Stop the backend and close overlay, show config
#[tauri::command]
async fn stop_companion(app: tauri::AppHandle) -> Result<(), String> {
    // Kill Python backend
    let state = app.state::<BackendProcess>();
    if let Some(mut child) = state.0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }

    // Close overlay
    if let Some(overlay) = app.get_webview_window("overlay") {
        let _ = overlay.close();
    }

    // Show config window — recreate if it was destroyed
    if let Some(config) = app.get_webview_window("config") {
        let _ = config.show();
        let _ = config.set_focus();
    } else {
        // Recreate config window
        let _ = tauri::WebviewWindowBuilder::new(
            &app,
            "config",
            tauri::WebviewUrl::App("index.html".into()),
        )
        .title("AI Gaming Companion")
        .inner_size(480.0, 640.0)
        .center()
        .resizable(false)
        .build()
        .map_err(|e| e.to_string())?;
    }

    Ok(())
}

/// Quit everything
#[tauri::command]
async fn quit_app(app: tauri::AppHandle) -> Result<(), String> {
    // Kill Python backend
    let state = app.state::<BackendProcess>();
    if let Some(mut child) = state.0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }

    // Exit app
    app.exit(0);
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .manage(BackendProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            start_companion,
            stop_companion,
            quit_app,
        ])
        .on_window_event(|window, event| {
            // When config window is closed, quit everything
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if window.label() == "config" {
                    let app = window.app_handle();
                    let state = app.state::<BackendProcess>();
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                    app.exit(0);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
