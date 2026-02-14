import { useState } from "react";
import { useAppStore } from "../shared/store/appStore";
import Tabs from "../shared/ui/Tabs";
import ExportDialog from "../widgets/ExportDialog";
import SmokePanel from "../widgets/SmokePanel";
import { formatAuthDetail } from "../shared/utils/authDetail";

export default function SettingsPage() {
  const [exportOpen, setExportOpen] = useState(false);
  const grainEnabled = useAppStore((state) => state.grainEnabled);
  const setGrainEnabled = useAppStore((state) => state.setGrainEnabled);
  const density = useAppStore((state) => state.density);
  const setDensity = useAppStore((state) => state.setDensity);
  const defaultActivityOpen = useAppStore((state) => state.defaultActivityOpen);
  const setDefaultActivityOpen = useAppStore((state) => state.setDefaultActivityOpen);
  const overlayBehavior = useAppStore((state) => state.overlayBehavior);
  const setOverlayBehavior = useAppStore((state) => state.setOverlayBehavior);
  const overlayCorner = useAppStore((state) => state.overlayCorner);
  const setOverlayCorner = useAppStore((state) => state.setOverlayCorner);
  const authStatus = useAppStore((state) => state.authStatus);
  const authError = useAppStore((state) => state.authError);
  const authDiagnostics = useAppStore((state) => state.authDiagnostics);
  const lastRequestInfo = useAppStore((state) => state.lastRequestInfo);
  const connectionState = useAppStore((state) => state.connectionState);
  const connectAuth = useAppStore((state) => state.connectAuth);
  const resetAuth = useAppStore((state) => state.resetAuth);
  const authDetail = formatAuthDetail(authDiagnostics.lastErrorDetail || authError);

  return (
    <section className="page-stub settings-page">
      <div className="page-header">
        <div>
          <div className="page-title">Настройки</div>
          <div className="page-subtitle">Пользовательские предпочтения интерфейса.</div>
        </div>
      </div>

      <div className="settings-grid">
        <div className="settings-card">
          <div className="settings-label">Подключение</div>
          <div className="settings-connection">
            <div className="settings-connection-row">
              <span>Статус</span>
              <span>{authStatus === "CONNECTED" ? "Подключено" : authStatus === "CONNECTING" ? "Подключаюсь…" : authStatus === "SERVER_UNREACHABLE" ? "Сервер недоступен" : "Требуется подключение"}</span>
            </div>
            <div className="settings-connection-row">
              <span>Доступность API</span>
              <span>
                {connectionState.apiReachable == null
                  ? "—"
                  : connectionState.apiReachable
                    ? "Доступен"
                    : "Недоступен"}
              </span>
            </div>
            <div className="settings-connection-row">
              <span>Авторизация</span>
              <span>
                {connectionState.authOk == null ? "—" : connectionState.authOk ? "ОК" : "Ошибка"}
              </span>
            </div>
            <div className="settings-connection-row">
              <span>Режим</span>
              <span>{authDiagnostics.authMode || "—"}</span>
            </div>
            <div className="settings-connection-row">
              <span>Токен обязателен</span>
              <span>
                {authDiagnostics.tokenRequired == null
                  ? "—"
                  : authDiagnostics.tokenRequired
                    ? "Да"
                    : "Нет"}
              </span>
            </div>
            <div className="settings-connection-row">
              <span>Последний успех</span>
              <span>{connectionState.lastOkTs || "—"}</span>
            </div>
            {authDiagnostics.tokenRequired === false ? (
              <div className="settings-connection-row">
                <span>Комментарий</span>
                <span>Локальный режим: токен не требуется</span>
              </div>
            ) : null}
            <div className="settings-connection-row">
              <span>API</span>
              <span>{authDiagnostics.baseUrl}</span>
            </div>
            <div className="settings-connection-row">
              <span>Токен</span>
              <span>
                {authDiagnostics.tokenRequired === false
                  ? "Не требуется"
                  : authDiagnostics.tokenPresent
                    ? "Есть"
                    : "Нет"}
              </span>
            </div>
            <div className="settings-connection-row">
              <span>Последний статус</span>
              <span>{authDiagnostics.lastStatus ?? "—"}</span>
            </div>
            <div className="settings-connection-row">
              <span>Последний запрос</span>
              <span>
                {lastRequestInfo.method && lastRequestInfo.path
                  ? `${lastRequestInfo.method} ${lastRequestInfo.path}`
                  : authDiagnostics.lastRequest || "—"}
              </span>
            </div>
            <div className="settings-connection-row">
              <span>Детали</span>
              <span>{authDetail || "—"}</span>
            </div>
            <div className="settings-connection-row">
              <span>Последняя попытка</span>
              <span>{authDiagnostics.lastAttemptAt || "—"}</span>
            </div>
          </div>
          <div className="settings-connection-actions">
            <button
              type="button"
              className={authStatus === "CONNECTING" ? "toggle-button is-active" : "toggle-button"}
              onClick={() => void connectAuth("manual")}
              disabled={authStatus === "CONNECTING"}
            >
              Переподключить
            </button>
            {authDiagnostics.tokenRequired === false ? null : (
              <button type="button" className="toggle-button" onClick={() => void resetAuth()}>
                Сбросить локальный токен
              </button>
            )}
            <button
              type="button"
              className="toggle-button"
              onClick={() => {
                const lines = [
                  `API: ${authDiagnostics.baseUrl}`,
                  `Статус: ${authStatus}`,
                  `API reachable: ${connectionState.apiReachable ?? "—"}`,
                  `Auth ok: ${connectionState.authOk ?? "—"}`,
                  `Token present: ${authDiagnostics.tokenPresent ? "да" : "нет"}`,
                  `Last request: ${lastRequestInfo.method && lastRequestInfo.path ? `${lastRequestInfo.method} ${lastRequestInfo.path}` : authDiagnostics.lastRequest || "—"}`,
                  `Last status: ${authDiagnostics.lastStatus ?? "—"}`,
                  `Detail: ${authDetail || "—"}`,
                  `Last attempt: ${authDiagnostics.lastAttemptAt || "—"}`,
                  `Last ok: ${connectionState.lastOkTs || "—"}`
                ];
                void navigator.clipboard?.writeText(lines.join("\n"));
              }}
            >
              Скопировать диагностику
            </button>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-label">Диагностика</div>
          <div className="settings-hint">
            Экспортируйте диалог, запуски и системные параметры в один JSON или пакет с логами.
          </div>
          <div className="settings-control">
            <button type="button" className="toggle-button" onClick={() => setExportOpen(true)}>
              Открыть экспорт
            </button>
          </div>
        </div>

        <SmokePanel />

        <div className="settings-card">
          <div className="settings-label">Лёгкие точки / зерно</div>
          <div className="settings-control">
            <button
              type="button"
              className={grainEnabled ? "toggle-button is-active" : "toggle-button"}
              onClick={() => setGrainEnabled(!grainEnabled)}
            >
              {grainEnabled ? "Включено" : "Выключено"}
            </button>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-label">Плотность интерфейса</div>
          <Tabs
            value={density}
            onChange={(value) => setDensity(value as "low" | "medium" | "high")}
            items={[
              { value: "low", label: "Низкая" },
              { value: "medium", label: "Средняя" },
              { value: "high", label: "Высокая" }
            ]}
          />
        </div>

        <div className="settings-card">
          <div className="settings-label">Правая панель по умолчанию</div>
          <div className="settings-control">
            <button
              type="button"
              className={defaultActivityOpen ? "toggle-button is-active" : "toggle-button"}
              onClick={() => setDefaultActivityOpen(!defaultActivityOpen)}
            >
              {defaultActivityOpen ? "Открыта" : "Закрыта"}
            </button>
          </div>
        </div>

        <div className="settings-card">
          <div className="settings-label">Оверлей · Не мешать</div>
          <div className="settings-control settings-control-row">
            <button
              type="button"
              className={overlayBehavior === "mini" ? "toggle-button is-active" : "toggle-button"}
              onClick={() => setOverlayBehavior("mini")}
            >
              Автосвернуть
            </button>
            <button
              type="button"
              className={overlayBehavior === "corner" ? "toggle-button is-active" : "toggle-button"}
              onClick={() => setOverlayBehavior("corner")}
            >
              В угол
            </button>
            <button
              type="button"
              className={overlayBehavior === "hide" ? "toggle-button is-active" : "toggle-button"}
              onClick={() => setOverlayBehavior("hide")}
            >
              Скрыть
            </button>
          </div>
          {overlayBehavior === "corner" ? (
            <div className="settings-control settings-control-row">
              <button
                type="button"
                className={overlayCorner === "top-right" ? "toggle-button is-active" : "toggle-button"}
                onClick={() => setOverlayCorner("top-right")}
              >
                Правый верх
              </button>
              <button
                type="button"
                className={overlayCorner === "top-left" ? "toggle-button is-active" : "toggle-button"}
                onClick={() => setOverlayCorner("top-left")}
              >
                Левый верх
              </button>
              <button
                type="button"
                className={overlayCorner === "bottom-right" ? "toggle-button is-active" : "toggle-button"}
                onClick={() => setOverlayCorner("bottom-right")}
              >
                Правый низ
              </button>
              <button
                type="button"
                className={overlayCorner === "bottom-left" ? "toggle-button is-active" : "toggle-button"}
                onClick={() => setOverlayCorner("bottom-left")}
              >
                Левый низ
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <ExportDialog open={exportOpen} onClose={() => setExportOpen(false)} />
    </section>
  );
}
