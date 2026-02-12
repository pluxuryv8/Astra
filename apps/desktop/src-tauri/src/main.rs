#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod bridge;
#[cfg(feature = "desktop-skills")]
mod autopilot;
#[cfg(feature = "desktop-skills")]
mod skills;
mod macos_main_queue;

use std::sync::Mutex;
use tauri::{
    GlobalShortcutManager, Manager, PhysicalPosition, WindowBuilder, WindowUrl,
};

struct OverlayState {
    mode: Mutex<String>,
}

#[tauri::command]
fn open_settings_window(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_window("settings") {
        let _ = win.show();
        let _ = win.set_focus();
        return Ok(());
    }
    WindowBuilder::new(
        &app,
        "settings",
        WindowUrl::App("index.html?view=settings".into()),
    )
    .title("Astra • Настройки")
    .inner_size(980.0, 700.0)
    .min_inner_size(820.0, 520.0)
    .resizable(true)
    .decorations(true)
    .transparent(true)
    .always_on_top(false)
    .build()
    .map(|_| ())
    .map_err(|e| e.to_string())
}

fn ensure_overlay_window(app: &tauri::AppHandle) -> Result<tauri::Window, String> {
    if let Some(win) = app.get_window("overlay") {
        return Ok(win);
    }
    let window = WindowBuilder::new(
        app,
        "overlay",
        WindowUrl::App("index.html?view=overlay".into()),
    )
    .title("Astra Overlay")
    .inner_size(360.0, 64.0)
    .resizable(false)
    .decorations(false)
    .transparent(true)
    .always_on_top(true)
    .skip_taskbar(true)
    .visible(false)
    .build()
    .map_err(|e| e.to_string())?;

    if let Ok(Some(monitor)) = window.current_monitor() {
        let size = monitor.size();
        let margin = 16;
        let win_size = window.outer_size().unwrap_or_else(|_| tauri::PhysicalSize::new(360, 64));
        let x = size
            .width
            .saturating_sub(win_size.width + margin) as i32;
        let y = margin as i32;
        let _ = window.set_position(PhysicalPosition::new(x, y));
    }
    Ok(window)
}

fn show_overlay_window(app: &tauri::AppHandle) -> Result<(), String> {
    let win = ensure_overlay_window(app)?;
    win.show().map_err(|e| e.to_string())?;
    Ok(())
}

fn hide_overlay_window(app: &tauri::AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_window("overlay") {
        win.hide().map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn toggle_overlay_window(app: &tauri::AppHandle) -> Result<(), String> {
    let win = ensure_overlay_window(app)?;
    let visible = win.is_visible().unwrap_or(false);
    if visible {
        win.hide().map_err(|e| e.to_string())?;
    } else {
        win.show().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn overlay_show(app: tauri::AppHandle) -> Result<(), String> {
    show_overlay_window(&app)
}

#[tauri::command]
fn overlay_hide(app: tauri::AppHandle) -> Result<(), String> {
    hide_overlay_window(&app)
}

#[tauri::command]
fn overlay_toggle(app: tauri::AppHandle) -> Result<(), String> {
    toggle_overlay_window(&app)
}

#[tauri::command]
fn overlay_set_mode(state: tauri::State<OverlayState>, mode: String) -> Result<(), String> {
    let mut guard = state.mode.lock().map_err(|_| "overlay mode lock failed")?;
    *guard = mode;
    Ok(())
}

#[tauri::command]
fn open_main_window(app: tauri::AppHandle, tab: Option<String>) -> Result<(), String> {
    if let Some(win) = app.get_window("main") {
        let _ = win.show();
        let _ = win.set_focus();
    }
    let payload = serde_json::json!({ "tab": tab });
    let _ = app.emit_all("open_inspector_tab", payload);
    Ok(())
}

fn main() {
    bridge::start_bridge();
    tauri::Builder::default()
        .manage(OverlayState {
            mode: Mutex::new("auto".to_string()),
        })
        .invoke_handler(tauri::generate_handler![
            open_settings_window,
            check_permissions,
            overlay_show,
            overlay_hide,
            overlay_toggle,
            overlay_set_mode,
            open_main_window
        ])
        .setup(|app| {
            let handle = app.handle();
            let mut shortcut_manager = handle.global_shortcut_manager();
            let _ = shortcut_manager.register("Cmd+Shift+S", move || {
                let _ = handle.emit_all("autopilot_stop_hotkey", {});
            });
            let handle_toggle = app.handle();
            let _ = shortcut_manager.register("Cmd+Shift+O", move || {
                let _ = toggle_overlay_window(&handle_toggle);
            });
            let handle_hide = app.handle();
            let _ = shortcut_manager.register("Cmd+W", move || {
                let _ = hide_overlay_window(&handle_hide);
            });
            let handle_quit = app.handle();
            let _ = shortcut_manager.register("Cmd+Q", move || {
                handle_quit.exit(0);
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("ошибка при запуске tauri-приложения");
}

#[tauri::command]
fn check_permissions() -> Result<autopilot::permissions::PermissionsStatus, String> {
    #[cfg(feature = "desktop-skills")]
    {
        Ok(autopilot::permissions::check_permissions())
    }
    #[cfg(not(feature = "desktop-skills"))]
    {
        Err("Недоступно без desktop-skills".to_string())
    }
}
