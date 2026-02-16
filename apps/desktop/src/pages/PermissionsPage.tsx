import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { getBridgeBaseUrl } from "../shared/api/config";
import Button from "../shared/ui/Button";

type PermissionStatus = "granted" | "denied" | "unknown";
type InputStatus = "available" | "blocked" | "unknown";

type BridgePermissions = {
  screen_recording: PermissionStatus;
  accessibility: PermissionStatus;
  input_control: InputStatus;
  message?: string;
};

type CaptureState = {
  status: "idle" | "loading" | "ok" | "error";
  message?: string;
};

const BRIDGE_BASE = getBridgeBaseUrl();
const BRIDGE_PORT = (() => {
  const parsed = new URL(BRIDGE_BASE);
  if (parsed.port) return parsed.port;
  return parsed.protocol === "https:" ? "443" : "80";
})();

const STATUS_LABELS: Record<PermissionStatus | InputStatus, string> = {
  granted: "Включено",
  denied: "Выключено",
  unknown: "Не удалось определить",
  available: "Доступно",
  blocked: "Недоступно"
};

function normalizePermission(value: unknown): PermissionStatus {
  if (value === "granted" || value === "denied" || value === "unknown") return value;
  if (typeof value === "boolean") return value ? "granted" : "denied";
  return "unknown";
}

function normalizeInput(value: unknown, fallback: PermissionStatus): InputStatus {
  if (value === "available" || value === "blocked" || value === "unknown") return value;
  if (fallback === "granted") return "available";
  if (fallback === "denied") return "blocked";
  return "unknown";
}

async function openSystemSettings(target: "screen" | "accessibility") {
  if (typeof window === "undefined" || !("__TAURI__" in window)) {
    return;
  }
  const shell = await import("@tauri-apps/api/shell");
  const deepLink =
    target === "screen"
      ? "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
      : "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility";
  try {
    await shell.open(deepLink);
  } catch {
    await shell.open("x-apple.systempreferences:com.apple.preference.security");
  }
}

export default function PermissionsPage() {
  const [loading, setLoading] = useState(true);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [httpStatus, setHttpStatus] = useState<number | null>(null);
  const [permissions, setPermissions] = useState<BridgePermissions | null>(null);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [capture, setCapture] = useState<CaptureState>({ status: "idle" });

  const bridgeOk = permissions !== null && !bridgeError;

  const screenStatus = useMemo(
    () => normalizePermission(permissions?.screen_recording),
    [permissions?.screen_recording]
  );

  const accessibilityStatus = useMemo(
    () => normalizePermission(permissions?.accessibility),
    [permissions?.accessibility]
  );

  const inputStatus = useMemo(
    () => normalizeInput(permissions?.input_control, accessibilityStatus),
    [permissions?.input_control, accessibilityStatus]
  );

  const loadPermissions = useCallback(async () => {
    setLoading(true);
    setBridgeError(null);
    setHttpStatus(null);
    try {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 4000);
      const res = await fetch(`${BRIDGE_BASE}/autopilot/permissions`, { signal: controller.signal });
      window.clearTimeout(timeout);
      setHttpStatus(res.status);
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        setBridgeError(text || `Bridge вернул ${res.status}`);
        setPermissions(null);
      } else {
        const data = (await res.json()) as BridgePermissions;
        const normalized: BridgePermissions = {
          screen_recording: normalizePermission(data.screen_recording),
          accessibility: normalizePermission(data.accessibility),
          input_control: normalizeInput(data.input_control, normalizePermission(data.accessibility)),
          message: data.message
        };
        setPermissions(normalized);
      }
    } catch (err) {
      setBridgeError(
        err instanceof Error && err.name === "AbortError"
          ? "Bridge не отвечает (таймаут)"
          : "Не удалось подключиться к bridge"
      );
      setPermissions(null);
    } finally {
      setLoading(false);
      setCheckedAt(new Date().toISOString());
    }
  }, []);

  const handleCaptureCheck = async () => {
    setCapture({ status: "loading", message: "Проверяю захват экрана…" });
    try {
      const res = await fetch(`${BRIDGE_BASE}/autopilot/capture`, {
        method: "POST",
        headers: { "Content-Type": "text/plain" },
        body: JSON.stringify({ max_width: 640, quality: 40 })
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        setCapture({ status: "error", message: text || `Ошибка capture (${res.status})` });
        return;
      }
      const payload = (await res.json()) as { width?: number; height?: number };
      setCapture({
        status: "ok",
        message: payload.width && payload.height ? `Скриншот получен (${payload.width}×${payload.height})` : "Скриншот получен"
      });
    } catch (err) {
      setCapture({
        status: "error",
        message: err instanceof Error ? err.message : "Не удалось получить скриншот"
      });
    }
  };

  useEffect(() => {
    void loadPermissions();
  }, [loadPermissions]);

  return (
    <section className="permissions-page">
      <div className="page-header">
        <div>
          <div className="page-title">Права доступа</div>
          <div className="page-subtitle">
            Проверка Bridge, записи экрана и универсального доступа на macOS.
          </div>
        </div>
        <Button type="button" variant="outline" onClick={() => void loadPermissions()} disabled={loading}>
          <RefreshCw size={16} />
          Повторить проверку
        </Button>
      </div>

      <div className="permissions-grid">
        <div className="permissions-card">
          <div className="permissions-card-header">
            <div>
              <div className="permissions-card-title">Bridge</div>
              <div className="permissions-card-subtitle">
                Локальный мост между UI и управлением компьютером.
              </div>
            </div>
            <span className={`perm-pill ${bridgeOk ? "is-ok" : "is-error"}`}>
              {bridgeOk ? "Доступен" : "Недоступен"}
            </span>
          </div>
          <div className="permissions-meta">
            Адрес: {BRIDGE_BASE}
            {httpStatus ? ` · HTTP ${httpStatus}` : ""}
          </div>
          {bridgeError ? <div className="permissions-error">{bridgeError}</div> : null}
          <div className="permissions-help">
            Если bridge недоступен — запусти <code>astra dev</code> и убедись, что порт {BRIDGE_PORT} слушает.
          </div>
        </div>

        <div className="permissions-card">
          <div className="permissions-card-header">
            <div>
              <div className="permissions-card-title">Запись экрана</div>
              <div className="permissions-card-subtitle">Нужна, чтобы делать скриншоты.</div>
            </div>
            <span className={`perm-pill ${screenStatus === "granted" ? "is-ok" : screenStatus === "denied" ? "is-error" : "is-warn"}`}>
              {STATUS_LABELS[screenStatus]}
            </span>
          </div>
          <div className="permissions-help">
            System Settings → Privacy & Security → Screen Recording → включить Randarc‑Astra (или Terminal).
          </div>
          <div className="permissions-actions">
            <Button type="button" variant="outline" onClick={() => void openSystemSettings("screen")}>
              <ExternalLink size={16} />
              Открыть настройки
            </Button>
            <Button type="button" variant="ghost" onClick={() => void handleCaptureCheck()} disabled={!bridgeOk || capture.status === "loading"}>
              Проверить скриншот
            </Button>
          </div>
          {capture.status !== "idle" ? (
            <div className={`permissions-capture ${capture.status}`}>{capture.message}</div>
          ) : null}
        </div>

        <div className="permissions-card">
          <div className="permissions-card-header">
            <div>
              <div className="permissions-card-title">Универсальный доступ</div>
              <div className="permissions-card-subtitle">Нужен для управления мышью и клавиатурой.</div>
            </div>
            <span className={`perm-pill ${accessibilityStatus === "granted" ? "is-ok" : accessibilityStatus === "denied" ? "is-error" : "is-warn"}`}>
              {STATUS_LABELS[accessibilityStatus]}
            </span>
          </div>
          <div className="permissions-help">
            System Settings → Privacy & Security → Accessibility → включить Randarc‑Astra (или Terminal).
          </div>
          <div className="permissions-actions">
            <Button type="button" variant="outline" onClick={() => void openSystemSettings("accessibility")}>
              <ExternalLink size={16} />
              Открыть настройки
            </Button>
          </div>
        </div>

        <div className="permissions-card">
          <div className="permissions-card-header">
            <div>
              <div className="permissions-card-title">Ввод</div>
              <div className="permissions-card-subtitle">Проверка доступа к симуляции ввода.</div>
            </div>
            <span className={`perm-pill ${inputStatus === "available" ? "is-ok" : inputStatus === "blocked" ? "is-error" : "is-warn"}`}>
              {STATUS_LABELS[inputStatus]}
            </span>
          </div>
          <div className="permissions-help">
            Если доступ недоступен — включите Универсальный доступ и повторите проверку.
          </div>
        </div>
      </div>

      <div className="permissions-footer">
        <div>Последняя проверка: {checkedAt ? new Date(checkedAt).toLocaleString() : "—"}</div>
        {permissions?.message ? <div className="permissions-message">{permissions.message}</div> : null}
      </div>
    </section>
  );
}
