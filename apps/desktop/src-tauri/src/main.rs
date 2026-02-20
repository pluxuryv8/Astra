#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod bridge;
#[cfg(feature = "desktop-skills")]
mod autopilot;
#[cfg(feature = "desktop-skills")]
mod skills;
mod macos_main_queue;

use std::{fs, path::PathBuf, sync::Mutex};
use tauri::{Manager, PhysicalPosition, WindowBuilder, WindowUrl};

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
    .transparent(false)
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
    .inner_size(420.0, 220.0)
    .resizable(true)
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
fn read_auth_token() -> Option<String> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(data_dir) = std::env::var("ASTRA_DATA_DIR") {
        candidates.push(PathBuf::from(data_dir).join("auth.token"));
    }
    if let Ok(base_dir) = std::env::var("ASTRA_BASE_DIR") {
        candidates.push(PathBuf::from(base_dir).join(".astra").join("auth.token"));
    }
    if let Ok(home) = std::env::var("HOME") {
        candidates.push(PathBuf::from(home).join(".astra").join("auth.token"));
    }
    if let Ok(mut dir) = std::env::current_dir() {
        for _ in 0..5 {
            candidates.push(dir.join(".astra").join("auth.token"));
            if !dir.pop() {
                break;
            }
        }
    }

    for path in candidates {
        if let Ok(content) = fs::read_to_string(&path) {
            let token = content.trim();
            if !token.is_empty() {
                return Some(token.to_string());
            }
        }
    }
    None
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
        .setup(|app| {
            if let Some(main) = app.get_window("main") {
                if let Err(err) = main.maximize() {
                    eprintln!("Не удалось развернуть главное окно при старте: {err}");
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            open_settings_window,
            check_permissions,
            overlay_show,
            overlay_hide,
            overlay_toggle,
            overlay_set_mode,
            read_auth_token,
            open_main_window
        ])
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
