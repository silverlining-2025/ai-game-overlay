use tauri::Manager;

/// Create the overlay window (transparent, always-on-top, click-through, capture-excluded)
#[tauri::command]
async fn open_overlay(app: tauri::AppHandle) -> Result<(), String> {
    // Close config window
    if let Some(config_win) = app.get_webview_window("config") {
        let _ = config_win.hide();
    }

    // Check if overlay already exists
    if app.get_webview_window("overlay").is_some() {
        return Ok(());
    }

    // Create overlay window
    let overlay = tauri::WebviewWindowBuilder::new(
        &app,
        "overlay",
        tauri::WebviewUrl::App("index.html#overlay".into()),
    )
    .title("AI Companion Overlay")
    .transparent(true)
    .decorations(false)
    .always_on_top(true)
    .skip_taskbar(true)
    .resizable(false)
    .shadow(false)
    .inner_size(400.0, 180.0)
    .position(20.0, 20.0)
    .build()
    .map_err(|e| e.to_string())?;

    // Make overlay click-through by default
    let _ = overlay.set_ignore_cursor_events(true);

    // Exclude overlay from screen capture (Windows only)
    #[cfg(windows)]
    {
        use windows::Win32::UI::WindowsAndMessaging::{
            SetWindowDisplayAffinity, WDA_EXCLUDEFROMCAPTURE,
        };

        // Small delay to ensure window handle is ready
        std::thread::sleep(std::time::Duration::from_millis(100));

        if let Ok(hwnd) = overlay.hwnd() {
            unsafe {
                let _ = SetWindowDisplayAffinity(
                    std::mem::transmute(hwnd),
                    WDA_EXCLUDEFROMCAPTURE,
                );
            }
        }
    }

    Ok(())
}

/// Close overlay and show config window
#[tauri::command]
async fn close_overlay(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
        let _ = overlay.close();
    }
    if let Some(config) = app.get_webview_window("config") {
        let _ = config.show();
    }
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![open_overlay, close_overlay])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
