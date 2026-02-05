#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod bridge;
#[cfg(feature = "desktop-skills")]
mod autopilot;
#[cfg(feature = "desktop-skills")]
mod skills;

use tauri::{GlobalShortcutManager, Manager};

const KEYCHAIN_SERVICE: &str = "randarc-astra";
const KEYCHAIN_ACCOUNT_API: &str = "astra-api-key";

#[tauri::command]
fn set_api_key(api_key: String) -> Result<(), String> {
    // EN kept: фиксированные service/account для keychain
    let entry = keyring::Entry::new(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT_API).map_err(|e| e.to_string())?;
    entry.set_password(&api_key).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn get_api_key() -> Result<Option<String>, String> {
    // EN kept: фиксированные service/account для keychain
    let entry = keyring::Entry::new(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT_API).map_err(|e| e.to_string())?;
    match entry.get_password() {
        Ok(value) => Ok(Some(value)),
        Err(_) => Ok(None),
    }
}

fn main() {
    bridge::start_bridge();
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![set_api_key, get_api_key, check_permissions])
        .setup(|app| {
            let handle = app.handle();
            let mut shortcut_manager = handle.global_shortcut_manager();
            let _ = shortcut_manager.register("Cmd+Shift+S", move || {
                let _ = handle.emit_all("autopilot_stop_hotkey", {});
            });
            let handle_toggle = app.handle();
            let _ = shortcut_manager.register("Cmd+Shift+O", move || {
                let _ = handle_toggle.emit_all("toggle_hud_mode", {});
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
