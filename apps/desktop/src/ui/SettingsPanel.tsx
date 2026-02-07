type SettingsPanelProps = {
  modelName: string;
  onModelChange: (value: string) => void;
  openaiKey: string;
  onOpenaiKeyChange: (value: string) => void;
  keyStored: boolean;
  apiAvailable: boolean | null;
  permissions: { screen_recording?: boolean; accessibility?: boolean } | null;
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
    <div className={`settings-panel ${isStandalone ? "standalone" : ""}`} onClick={(e) => e.stopPropagation()}>
      <div className="settings-header">
        <div>
          <div className="settings-title">Настройки</div>
          <div className="settings-subtitle">Модель, ключ и режимы</div>
        </div>
        <button className="icon-button" onClick={onClose} title="Закрыть">
          ✕
        </button>
      </div>

      {message ? <div className={`settings-banner ${message.tone}`}>{message.text}</div> : null}

      <div className="settings-section">
        <div className="section-title">Модель и ключ</div>
        <div className="settings-row">
          <div className={`status-dot ${keyStored ? "on" : "off"}`} />
          <div className="settings-note">{keyStored ? "Ключ сохранён" : "Ключ не сохранён"}</div>
          <div className="settings-note">
            API: {apiAvailable === null ? "проверка…" : apiAvailable ? "подключён" : "не отвечает"}
          </div>
        </div>
        <label className="settings-field">
          <span>Модель</span>
          <input type="text" value={modelName} onChange={(e) => onModelChange(e.target.value)} placeholder="gpt-4.1-mini" />
        </label>
        <label className="settings-field">
          <span>Ключ</span>
          <input
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

      <div className="settings-section">
        <div className="section-title">Режим запуска</div>
        <select value={mode} onChange={(e) => onModeChange(e.target.value)}>
          {modeOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className="settings-section">
        <div className="section-title">Визуал</div>
        <label className="toggle">
          <input type="checkbox" checked={animatedBg} onChange={(e) => onAnimatedBgChange(e.target.checked)} />
          <span>Анимированный фон</span>
        </label>
      </div>

      <div className="settings-section">
        <div className="section-title">Разрешения macOS</div>
        <div className="settings-perm">
          <span>Запись экрана</span>
          <span className={permissions?.screen_recording ? "perm-on" : "perm-off"}>
            {permissions?.screen_recording ? "включено" : "не включено"}
          </span>
        </div>
        <div className="settings-perm">
          <span>Универсальный доступ</span>
          <span className={permissions?.accessibility ? "perm-on" : "perm-off"}>
            {permissions?.accessibility ? "включено" : "не включено"}
          </span>
        </div>
        <button className="btn ghost" onClick={onRefreshPermissions}>
          Проверить снова
        </button>
      </div>
    </div>
  );
}
