use serde::Serialize;
use xcap::Monitor;

#[derive(Debug, Serialize)]
pub struct PermissionsStatus {
    pub screen_recording: String,
    pub accessibility: String,
    pub input_control: String,
    pub message: String,
}

pub fn check_permissions() -> PermissionsStatus {
    let screen_recording_ok = Monitor::all().is_ok();
    let accessibility_ok = check_accessibility();
    let screen_recording = if screen_recording_ok { "granted" } else { "denied" }.to_string();
    let accessibility = if accessibility_ok { "granted" } else { "denied" }.to_string();
    let input_control = if accessibility_ok { "available" } else { "blocked" }.to_string();
    let message = if screen_recording_ok && accessibility_ok {
        "Разрешения в норме".to_string()
    } else {
        "Нужны разрешения: Запись экрана и Универсальный доступ".to_string()
    };
    PermissionsStatus {
        screen_recording,
        accessibility,
        input_control,
        message,
    }
}

fn check_accessibility() -> bool {
    // EN kept: внутренний fallback — точная проверка требует системных API.
    // Здесь проверка упрощена: если можем создать Enigo, считаем доступ разрешён.
    enigo::Enigo::new(&enigo::Settings::default()).is_ok()
}
