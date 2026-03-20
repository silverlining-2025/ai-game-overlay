use tauri::Manager;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use std::sync::Mutex;

struct BackendProcess(Mutex<Option<std::process::Child>>);

/// Launch the Python backend and create the overlay window
#[tauri::command]
async fn start_companion(
    app: tauri::AppHandle,
    game: String,
    character: String,
    interval: f64,
    chattiness: Option<f64>,
    locale: Option<String>,
    api_key: Option<String>,
    gemini_key: Option<String>,
    openai_key: Option<String>,
) -> Result<(), String> {
    // Start Python backend — find the repo root by walking up from exe/cwd
    let repo_root = {
        let candidates = [
            std::env::current_exe().ok(),
            std::env::current_dir().ok(),
        ];
        let mut found = None;
        for start in candidates.into_iter().flatten() {
            let mut dir = start;
            loop {
                if dir.join("backend").is_dir() {
                    found = Some(dir);
                    break;
                }
                if !dir.pop() {
                    break;
                }
            }
            if found.is_some() {
                break;
            }
        }
        found.ok_or_else(|| "Could not find repo root (backend/ directory)".to_string())?
    };

    // Log the repo root for debugging
    eprintln!("[tauri] repo_root: {:?}", repo_root);

    let locale_val = locale.unwrap_or_else(|| "ko".into());
    let backend = std::process::Command::new("python")
        .args([
            "-X", "utf8",
            "-m", "backend.tools.web_overlay",
            "--game", &game,
            "--interval", &interval.to_string(),
            "--character", &character,
            "--chattiness", &format!("{:.1}", chattiness.unwrap_or(0.5)),
            "--locale", &locale_val,
            "--port", "8080",
            "--headless",
            "--save-training",
        ])
        .env("PYTHONIOENCODING", "utf-8")
        .env("ANTHROPIC_API_KEY", &api_key.unwrap_or_default())
        .env("GEMINI_API_KEY", &gemini_key.unwrap_or_default())
        .env("OPENAI_API_KEY", &openai_key.unwrap_or_default())
        .current_dir(&repo_root)
        .stdout(std::process::Stdio::inherit())
        .stderr(std::process::Stdio::inherit())
        .spawn()
        .map_err(|e| format!("Failed to start Python backend (cwd={:?}): {}", repo_root, e))?;

    // Store the process handle so we can kill it later
    let state = app.state::<BackendProcess>();
    *state.0.lock().unwrap() = Some(backend);

    // Check if overlay already exists
    if app.get_webview_window("overlay").is_some() {
        // Just close config
        if let Some(config_win) = app.get_webview_window("config") {
            let _ = config_win.close();
        }
        return Ok(());
    }

    // Create overlay FIRST (before closing config, so app doesn't exit)
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
                let hwnd = HWND(raw_hwnd.0 as *mut std::ffi::c_void);
                let _ = SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE);
            }
        }
    }

    // Now close config window (overlay exists, so app won't exit)
    if let Some(config_win) = app.get_webview_window("config") {
        let _ = config_win.close();
    }

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

    // Create config window FIRST (before closing overlay — prevents zero-window exit)
    if app.get_webview_window("config").is_none() {
        let _ = tauri::WebviewWindowBuilder::new(
            &app,
            "config",
            tauri::WebviewUrl::App("index.html".into()),
        )
        .title("AI Gaming Companion")
        .inner_size(500.0, 780.0)
        .center()
        .resizable(false)
        .build()
        .map_err(|e| e.to_string())?;
    } else if let Some(config) = app.get_webview_window("config") {
        let _ = config.show();
        let _ = config.set_focus();
    }

    // Now close overlay (config exists, app won't exit)
    if let Some(overlay) = app.get_webview_window("overlay") {
        let _ = overlay.close();
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
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(BackendProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            start_companion,
            stop_companion,
            quit_app,
        ])
        .setup(|app| {
            // System tray
            let show = MenuItem::with_id(app, "show", "오버레이 보기/숨기기", true, None::<&str>)?;
            let config_item = MenuItem::with_id(app, "config", "설정", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &config_item, &quit_item])?;

            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("AI Gaming Companion")
                .menu(&menu)
                .on_menu_event(|app, event| {
                    match event.id().as_ref() {
                        "show" => {
                            if let Some(overlay) = app.get_webview_window("overlay") {
                                if overlay.is_visible().unwrap_or(false) {
                                    let _ = overlay.hide();
                                } else {
                                    let _ = overlay.show();
                                }
                            }
                        }
                        "config" => {
                            if let Some(config) = app.get_webview_window("config") {
                                let _ = config.show();
                                let _ = config.set_focus();
                            }
                        }
                        "quit" => {
                            let state = app.state::<BackendProcess>();
                            if let Some(mut child) = state.0.lock().unwrap().take() {
                                let _ = child.kill();
                            }
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .build(app)?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
