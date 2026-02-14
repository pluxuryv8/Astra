type SettingsPanelProps = {
  modelName: string;
  onModelChange: (value: string) => void;
  openaiKey: string;
  onOpenaiKeyChange: (value: string) => void;
  keyStored: boolean;
  apiAvailable: boolean | null;
  permissions: { screen_recording?: "granted" | "denied" | "unknown"; accessibility?: "granted" | "denied" | "unknown" } | null;
  mode: string;
  modeOptions: { value: string; label: string }[];
  onModeChange: (value: string) => void;
  animatedBg: boolean;
  onAnimatedBgChange: (value: boolean) => void;
  onSave: () => void;
  saving: boolean;
  message?: { text: string; tone: "success" | "error" | "info" } | null;
  onClose: () => void;
  onRefreshPermissions: () => void;
  isStandalone?: boolean;
};

export default function SettingsPanel({
  modelName,
  onModelChange,
  openaiKey,
  onOpenaiKeyChange,
  keyStored,
  apiAvailable,
  permissions,
  mode,
  modeOptions,
  onModeChange,
  animatedBg,
  onAnimatedBgChange,
  onSave,
  saving,
  message,
  onClose,
  onRefreshPermissions,
  isStandalone
}: SettingsPanelProps) {
  return (
    <div className={`panel settings-panel ${isStandalone ? "standalone" : ""}`}>
      <div className="panel-header">
        <div>
          <div className="panel-title">Settings</div>
          <div className="panel-subtitle">Модель, ключ, режимы</div>
        </div>
        <button className="btn ghost small" onClick={onClose} title="Закрыть">
          ✕
        </button>
      </div>

      {message ? <div className={`banner ${message.tone}`}>{message.text}</div> : null}

      <div className="panel-section">
        <div className="section-title">Модель и ключ</div>
        <div className="status-row compact">
          <span className={`pill ${keyStored ? "ok" : "warn"}`}>{keyStored ? "Ключ сохранён" : "Ключ не задан"}</span>
          <span className="status-chip">API: {apiAvailable === null ? "проверка" : apiAvailable ? "OK" : "нет"}</span>
        </div>
        <label className="field">
          <span>Модель</span>
          <input className="input" type="text" value={modelName} onChange={(e) => onModelChange(e.target.value)} />
        </label>
        <label className="field">
          <span>Ключ</span>
          <input
            className="input"
            type="password"
            value={openaiKey}
            onChange={(e) => onOpenaiKeyChange(e.target.value)}
            placeholder="sk-..."
          />
        </label>
        <button className="btn primary" onClick={onSave} disabled={saving}>
          {saving ? "Сохранение…" : "Сохранить"}
        </button>
      </div>

      <div className="panel-section">
        <div className="section-title">Режим запуска</div>
        <select value={mode} onChange={(e) => onModeChange(e.target.value)}>
          {modeOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="panel-section">
        <div className="section-title">Визуал</div>
        <label className="checkbox">
          <input type="checkbox" checked={animatedBg} onChange={(e) => onAnimatedBgChange(e.target.checked)} />
          Анимированный фон
        </label>
      </div>

      <div className="panel-section">
        <div className="section-title">Разрешения macOS</div>
        <div className="settings-perm">
          <span>Запись экрана</span>
          <span className={permissions?.screen_recording === "granted" ? "perm-on" : "perm-off"}>
            {permissions?.screen_recording === "granted" ? "включено" : "не включено"}
          </span>
        </div>
        <div className="settings-perm">
          <span>Универсальный доступ</span>
          <span className={permissions?.accessibility === "granted" ? "perm-on" : "perm-off"}>
            {permissions?.accessibility === "granted" ? "включено" : "не включено"}
          </span>
        </div>
        <button className="btn ghost" onClick={onRefreshPermissions}>
          Проверить снова
        </button>
      </div>
    </div>
  );
}
