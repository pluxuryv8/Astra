import React, { useEffect, useMemo, useState } from "react";
import {
  apiBase,
  listProjects,
  createProject,
  updateProject,
  createRun,
  createPlan,
  startRun,
  cancelRun,
  getSnapshot,
  initAuth,
  checkApiStatus,
  getSessionToken,
  checkPermissions,
  storeOpenAIKeyLocal,
  getLocalOpenAIStatus,
  approve,
  reject
} from "./api";
import { ru } from "./i18n/ru";
import { listen } from "@tauri-apps/api/event";
import { appWindow, LogicalPosition, LogicalSize } from "@tauri-apps/api/window";

const t = ru;

// EN kept: типы событий — публичный контракт API
const EVENT_TYPES = [
  "run_created",
  "plan_created",
  "run_started",
  "run_done",
  "run_failed",
  "run_canceled",
  "run_paused",
  "run_resumed",
  "task_queued",
  "task_started",
  "task_progress",
  "task_failed",
  "task_retried",
  "task_done",
  "source_found",
  "source_fetched",
  "fact_extracted",
  "artifact_created",
  "conflict_detected",
  "verification_done",
  "approval_requested",
  "approval_approved",
  "approval_rejected",
  "autopilot_state",
  "autopilot_action"
];

// EN kept: значения режимов — публичный контракт API
const MODE_OPTIONS = [
  { value: "plan_only", label: t.modes.plan_only },
  { value: "research", label: t.modes.research },
  { value: "execute_confirm", label: t.modes.execute_confirm },
  { value: "autopilot_safe", label: t.modes.autopilot_safe }
];

const HUD_WINDOW_MODE = "astra_window_mode";
const HUD_WINDOW_SIZE = "astra_window_size";
const HUD_OVERLAY_SIZE = "astra_overlay_size";
const HUD_OVERLAY_POS = "astra_overlay_pos";
const SETTINGS_VIEW = "settings";

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function statusLabel(status?: string | null) {
  if (!status || status === "created") return "Ожидание";
  if (status === "running") return "В работе";
  if (status === "paused") return "Пауза";
  if (status === "done") return "Готово";
  if (status === "failed") return "Ошибка";
  if (status === "canceled") return "Отменено";
  return status;
}

function HeaderOverlay({
  onClose,
  onHide,
  onMinimize,
  onStop,
  showStop
}: {
  onClose: () => void;
  onHide: () => void;
  onMinimize: () => void;
  onStop: () => void;
  showStop: boolean;
}) {
  return (
    <div className="overlay-topbar">
      <div className="overlay-topbar-inner">
        <button className="overlay-btn close" onClick={onClose} title="Закрыть">✕</button>
        <button className="overlay-btn" onClick={onHide} title="Скрыть">Скрыть</button>
        <button className="overlay-btn" onClick={onMinimize} title="Свернуть">Свернуть</button>
        <button className={`overlay-btn ${showStop ? "danger" : "muted"}`} onClick={onStop} disabled={!showStop} title="Стоп">
          Стоп
        </button>
      </div>
    </div>
  );
}

function PromptInput({
  value,
  disabled,
  onChange,
  onSubmit,
  status
}: {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  status?: string | null;
}) {
  return (
    <section className="hud-idle">
      <div className="hud-idle-title">ASTRA</div>
      <div className="hud-idle-subtitle">Чем займёмся?</div>
      <div className="hud-input-row">
        <input
          className="hud-input"
          type="text"
          placeholder="Коротко: что нужно сделать"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onSubmit();
            }
          }}
        />
        <button className="send-button" title="Запустить" onClick={onSubmit} disabled={disabled}>
          ➤
        </button>
      </div>
      {status ? <div className="hud-status-line">{status}</div> : null}
    </section>
  );
}

function StatusLine({ title, subtitle, status }: { title: string; subtitle?: string; status: string }) {
  return (
    <section className="hud-status">
      <div className="hud-status-title">{title}</div>
      {subtitle ? <div className="hud-status-subtitle">{subtitle}</div> : null}
      <div className="hud-status-chip">{status}</div>
    </section>
  );
}

function TaskList({ steps }: { steps: any[] }) {
  if (!steps.length) {
    return (
      <section className="hud-section">
        <div className="hud-section-title">Задачи</div>
        <div className="hud-meta">План пока пустой</div>
      </section>
    );
  }
  return (
    <section className="hud-section">
      <div className="hud-section-title">Задачи</div>
      <ul className="hud-list scrollable">
        {steps.map((step) => (
          <li key={step.id} className="hud-list-item">
            <div className="hud-list-title">
              {step.step_index + 1}. {step.title}
            </div>
            <div className={`hud-list-sub status-${step.status}`}>{statusLabel(step.status)}</div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ConfirmCard({ approval, onApprove, onReject }: { approval: any; onApprove: () => void; onReject: () => void }) {
  if (!approval) return null;
  return (
    <section className="hud-section hud-approval">
      <div className="hud-section-title">Подтверждение</div>
      <div className="hud-value">{approval.title}</div>
      {approval.description ? <div className="hud-meta">{approval.description}</div> : null}
      <div className="hud-row">
        <button className="primary" onClick={onApprove}>Разрешить</button>
        <button className="danger" onClick={onReject}>Отказать</button>
      </div>
    </section>
  );
}

function ResultCard({ status }: { status: string }) {
  return (
    <section className="hud-section">
      <div className="hud-section-title">Итог</div>
      <div className="hud-value">{status}</div>
    </section>
  );
}

export default function App() {
  const isSettingsView = new URLSearchParams(window.location.search).get("view") === SETTINGS_VIEW;
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProject, setSelectedProject] = useState<any | null>(null);
  const [run, setRun] = useState<any | null>(null);
  const [plan, setPlan] = useState<any[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [autopilotState, setAutopilotState] = useState<any | null>(null);
  const [queryText, setQueryText] = useState("");
  const [mode, setMode] = useState("execute_confirm");
  const [status, setStatus] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [permissions, setPermissions] = useState<any | null>(null);
  const [openaiKey, setOpenaiKeyValue] = useState("");
  const [apiKeyReady, setApiKeyReady] = useState(false);
  const [keyStored, setKeyStored] = useState(false);
  const [savingVault, setSavingVault] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<{ text: string; tone: "success" | "error" | "info" } | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [apiAvailable, setApiAvailable] = useState<boolean | null>(null);
  const [modelName, setModelName] = useState("gpt-4.1-mini");
  const [loopDelayMs, setLoopDelayMs] = useState(650);
  const [maxActions, setMaxActions] = useState(6);
  const [maxCycles, setMaxCycles] = useState(30);
  const [windowMode, setWindowMode] = useState<"window" | "overlay">("window");
  const settingsSizeRef = React.useRef<{ width: number; height: number } | null>(null);
  const settingsPrevModeRef = React.useRef<"window" | "overlay" | null>(null);

  const eventSourceRef = React.useRef<EventSource | null>(null);
  const refreshLock = React.useRef(false);

  useEffect(() => {
    if (isSettingsView) {
      setSettingsOpen(true);
    }
    initAuth()
      .then(async () => {
        await loadProjects();
        const last = localStorage.getItem("astra_last_run_id");
        if (last) {
          await refreshSnapshot(last);
          openEventStream(last);
        }
      })
      .catch((err) => setStatus(err.message || t.errors.authInit));
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (settingsOpen || isSettingsView) {
          closeSettingsWindow();
        } else {
          appWindow.hide();
        }
      }
      if (event.metaKey && event.key === ",") {
        event.preventDefault();
        setSettingsOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [settingsOpen, isSettingsView]);

  useEffect(() => {
    const checkApi = async () => {
      const ok = await checkApiStatus();
      setApiAvailable(ok);
    };
    if (settingsOpen || isSettingsView) {
      checkApi();
    }
  }, [settingsOpen, isSettingsView]);

  useEffect(() => {
    const checkLocalKey = async () => {
      try {
        const res = await getLocalOpenAIStatus();
        setKeyStored(res.stored);
      } catch {
        setKeyStored(false);
      }
    };
    if (settingsOpen || isSettingsView) {
      checkLocalKey();
    }
  }, [settingsOpen, isSettingsView]);

  useEffect(() => {
    if (!settingsMessage) return;
    const timer = setTimeout(() => setSettingsMessage(null), 5000);
    return () => clearTimeout(timer);
  }, [settingsMessage]);

  useEffect(() => {
    if (isSettingsView) return;
    const resizeForSettings = async () => {
      if (settingsOpen) {
        const size = await appWindow.innerSize();
        settingsSizeRef.current = { width: size.width, height: size.height };
        const targetWidth = Math.max(size.width, 900);
        const targetHeight = Math.max(size.height, 640);
        if (windowMode === "overlay") {
          settingsPrevModeRef.current = "overlay";
          await applyWindowMode(false, { width: targetWidth, height: targetHeight });
          await sleep(120);
          await appWindow.setSize(new LogicalSize(targetWidth, targetHeight));
        } else {
          await appWindow.setMinSize(new LogicalSize(760, 520));
          await sleep(80);
          await appWindow.setSize(new LogicalSize(targetWidth, targetHeight));
          await sleep(80);
          await appWindow.setSize(new LogicalSize(targetWidth, targetHeight));
        }
      } else if (settingsSizeRef.current) {
        const prev = settingsSizeRef.current;
        settingsSizeRef.current = null;
        if (settingsPrevModeRef.current === "overlay") {
          settingsPrevModeRef.current = null;
          await applyOverlayMode(false);
          await sleep(80);
          await appWindow.setSize(new LogicalSize(prev.width, prev.height));
        } else {
          await appWindow.setMinSize(windowMode === "overlay" ? new LogicalSize(420, 200) : new LogicalSize(520, 320));
          await sleep(80);
          await appWindow.setSize(new LogicalSize(prev.width, prev.height));
        }
      }
    };
    resizeForSettings();
  }, [settingsOpen, windowMode, isSettingsView]);

  useEffect(() => {
    if (!selectedProject && projects.length > 0) {
      setSelectedProject(projects[0]);
    }
  }, [projects, selectedProject]);

  useEffect(() => {
    if (!selectedProject) return;
    const settings = selectedProject.settings || {};
    const llm = settings.llm || {};
    const autopilot = settings.autopilot || {};
    setModelName(llm.model || "gpt-4.1-mini");
    setLoopDelayMs(Number(autopilot.loop_delay_ms ?? 650));
    setMaxActions(Number(autopilot.max_actions ?? 6));
    setMaxCycles(Number(autopilot.max_cycles ?? 30));
  }, [selectedProject]);

  useEffect(() => {
    checkPermissions()
      .then(setPermissions)
      .catch(() => setPermissions(null));
  }, []);

  useEffect(() => {
    if (isSettingsView) return;
    const unlistenStop = listen("autopilot_stop_hotkey", async () => {
      if (run) {
        await cancelRun(run.id);
        await refreshSnapshot(run.id);
      }
    });
    const unlistenToggle = listen("toggle_hud_mode", async () => {
      await toggleOverlayMode();
    });
    const unlistenHide = listen("overlay_hide_hotkey", async () => {
      await appWindow.hide();
    });
    return () => {
      unlistenStop.then((fn) => fn());
      unlistenToggle.then((fn) => fn());
      unlistenHide.then((fn) => fn());
    };
  }, [run, windowMode, isSettingsView]);

  useEffect(() => {
    if (isSettingsView) return;
    const saved = (localStorage.getItem(HUD_WINDOW_MODE) as "window" | "overlay") || "window";
    if (saved === "overlay") {
      applyOverlayMode();
    } else {
      applyWindowMode();
    }
    const unlistenResize = appWindow.onResized(async () => {
      const size = await appWindow.innerSize();
      if (windowMode === "overlay") {
        localStorage.setItem(HUD_OVERLAY_SIZE, JSON.stringify({ width: size.width, height: size.height }));
      } else {
        localStorage.setItem(HUD_WINDOW_SIZE, JSON.stringify({ width: size.width, height: size.height }));
      }
    });
    const unlistenMove = appWindow.onMoved(async () => {
      if (windowMode !== "overlay") return;
      const pos = await appWindow.outerPosition();
      localStorage.setItem(HUD_OVERLAY_POS, JSON.stringify({ x: pos.x, y: pos.y }));
    });
    return () => {
      unlistenResize.then((fn) => fn());
      unlistenMove.then((fn) => fn());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSettingsView]);

  async function applyWindowMode(persist = true, overrideSize?: { width: number; height: number }) {
    const sizeRaw = localStorage.getItem(HUD_WINDOW_SIZE);
    const size = overrideSize || (sizeRaw ? JSON.parse(sizeRaw) : { width: 640, height: 420 });
    await appWindow.setDecorations(true);
    await appWindow.setAlwaysOnTop(false);
    await appWindow.setFullscreen(false);
    await appWindow.setResizable(true);
    await appWindow.setMinSize(new LogicalSize(520, 320));
    await sleep(60);
    await appWindow.setSize(new LogicalSize(size.width, size.height));
    await sleep(60);
    await appWindow.setSize(new LogicalSize(size.width, size.height));
    if (persist) {
      localStorage.setItem(HUD_WINDOW_MODE, "window");
    }
    setWindowMode("window");
  }

  async function applyOverlayMode(persist = true) {
    const sizeRaw = localStorage.getItem(HUD_OVERLAY_SIZE);
    const posRaw = localStorage.getItem(HUD_OVERLAY_POS);
    const size = sizeRaw ? JSON.parse(sizeRaw) : { width: 460, height: 260 };
    const pos = posRaw ? JSON.parse(posRaw) : null;
    await appWindow.setDecorations(false);
    await appWindow.setAlwaysOnTop(true);
    await appWindow.setFullscreen(false);
    await appWindow.setResizable(true);
    await appWindow.setMinSize(new LogicalSize(420, 220));
    await sleep(60);
    await appWindow.setSize(new LogicalSize(size.width, size.height));
    await sleep(60);
    await appWindow.setSize(new LogicalSize(size.width, size.height));
    if (pos) {
      await appWindow.setPosition(new LogicalPosition(pos.x, pos.y));
    }
    if (persist) {
      localStorage.setItem(HUD_WINDOW_MODE, "overlay");
    }
    setWindowMode("overlay");
  }

  async function toggleOverlayMode() {
    if (windowMode === "overlay") {
      await applyWindowMode();
    } else {
      await applyOverlayMode();
    }
  }

  function closeSettingsWindow() {
    if (isSettingsView) {
      appWindow.close();
      return;
    }
    setSettingsOpen(false);
  }

  async function loadProjects() {
    const data = await listProjects();
    if (data.length === 0) {
      const created = await createProject({ name: "Основной", tags: ["default"], settings: {} });
      setProjects([created]);
      setSelectedProject(created);
      return;
    }
    setProjects(data);
  }

  async function applySettingsToProject(projectId: string) {
    const settings = {
      llm: {
        provider: "openai",
        base_url: "https://api.openai.com/v1",
        model: modelName.trim() || "gpt-4.1-mini",
      },
      autopilot: {
        loop_delay_ms: Math.max(200, Number(loopDelayMs) || 650),
        max_actions: Math.max(1, Number(maxActions) || 6),
        max_cycles: Math.max(1, Number(maxCycles) || 30),
      }
    };
    await updateProject(projectId, { settings });
  }

  async function ensureApiKey(): Promise<boolean> {
    if (apiKeyReady) return true;
    try {
      const res = await getLocalOpenAIStatus();
      if (!res.stored) {
        setStatus("Ключ не найден. Открой настройки и сохрани его.");
        return false;
      }
      setApiKeyReady(true);
      return true;
    } catch (err: any) {
      setStatus(err?.message || "Не удалось проверить ключ. Открой настройки.");
      return false;
    }
  }

  async function handleSaveProvider() {
    if (!openaiKey) {
      setStatus("Введите ключ");
      setSettingsMessage({ text: "Введите ключ", tone: "error" });
      return;
    }
    try {
      setSavingVault(true);
      await storeOpenAIKeyLocal(openaiKey);
      setKeyStored(true);
      if (selectedProject) {
        await applySettingsToProject(selectedProject.id);
        setApiKeyReady(true);
        setSettingsMessage({ text: "Ключ сохранён", tone: "success" });
      } else {
        setSettingsMessage({ text: "Ключ сохранён. Запусти API для активации.", tone: "info" });
      }
      setOpenaiKeyValue("");
      setStatus("Ключ сохранён");
    } catch (err: any) {
      setStatus(err.message || t.onboarding.vaultError);
      setSettingsMessage({ text: err.message || t.onboarding.vaultError, tone: "error" });
    } finally {
      setSavingVault(false);
    }
  }

  async function handleRunCommand() {
    if (!selectedProject || !queryText.trim()) return;
    const ok = await ensureApiKey();
    if (!ok) return;
    const newRun = await createRun(selectedProject.id, { query_text: queryText, mode });
    setRun(newRun);
    localStorage.setItem("astra_last_run_id", newRun.id);
    setPlan([]);
    setApprovals([]);
    await createPlan(newRun.id);
    await refreshSnapshot(newRun.id);
    await startRun(newRun.id);
    openEventStream(newRun.id);
  }

  async function handleCancelRun() {
    if (!run) return;
    await cancelRun(run.id);
    await refreshSnapshot(run.id);
  }


  async function handleApprove(approvalId: string) {
    await approve(approvalId);
    if (run) await refreshSnapshot(run.id);
  }

  async function handleReject(approvalId: string) {
    await reject(approvalId);
    if (run) await refreshSnapshot(run.id);
  }

  async function refreshSnapshot(runId?: string) {
    const id = runId || run?.id;
    if (!id) return;
    const snapshot = await getSnapshot(id);
    setRun(snapshot.run);
    setPlan(snapshot.plan || []);
    setApprovals(snapshot.approvals || []);
  }

  function openEventStream(runId: string) {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    const token = getSessionToken();
    const es = new EventSource(`${apiBase()}/runs/${runId}/events?token=${token}`);
    EVENT_TYPES.forEach((type) => {
      es.addEventListener(type, (evt) => handleEvent(type, evt as MessageEvent));
    });
    es.onerror = () => {
      setStatus("Поток событий отключён");
    };
    eventSourceRef.current = es;
  }

  async function handleEvent(type: string, evt: MessageEvent) {
    try {
      const payload = JSON.parse(evt.data);
      if (type === "autopilot_state") {
        setAutopilotState(payload);
      }
      if (!refreshLock.current) {
        refreshLock.current = true;
        await refreshSnapshot(payload.run_id || run?.id);
        refreshLock.current = false;
      }
      if (type === "run_done" || type === "run_failed" || type === "run_canceled") {
        setStatus(statusLabel(type.replace("run_", "")));
      }
    } catch (err: any) {
      setStatus(err.message || "Не удалось прочитать событие");
    }
  }

  const pendingApprovals = useMemo(() => approvals.filter((a) => a.status === "pending"), [approvals]);
  const runStatus = run?.status || "idle";
  const isActive = ["running", "paused"].includes(runStatus);
  const isDone = ["done", "failed", "canceled"].includes(runStatus);
  const uiMode = isActive ? "active" : isDone ? "done" : "idle";
  const activeStep = plan.find((step) => step.status === "running") || plan[0];
  const summary = autopilotState?.step_summary || activeStep?.title || "—";
  const runStatusLabel = statusLabel(runStatus);

  const keyStatusLabel = apiKeyReady
    ? "Ключ активен"
    : keyStored
      ? "Ключ сохранён"
      : "Ключ не сохранён";

  const settingsPanel = (
    <aside className={`hud-settings ${isSettingsView || settingsOpen ? "open" : ""} ${isSettingsView ? "settings-window" : ""}`} onClick={(e) => e.stopPropagation()}>
      <div className="hud-settings-header">
        <div className="hud-settings-title">
          <div className="hud-section-title">Настройки</div>
          <div className="hud-meta">Ключи, разрешения и режимы</div>
        </div>
        <button className="icon-close" onClick={closeSettingsWindow} title="Закрыть">✕</button>
      </div>

      {settingsMessage && (
        <div className={`settings-banner ${settingsMessage.tone}`}>
          {settingsMessage.text}
        </div>
      )}

      <section className="settings-card">
        <div className="settings-card-title">Подключение</div>
        <div className="settings-status-row">
          <div className={`status-dot ${apiKeyReady ? "on" : keyStored ? "warm" : "off"}`} />
          <div className="hud-meta">{keyStatusLabel}</div>
          <div className="hud-meta">
            API: {apiAvailable === null ? "проверка…" : apiAvailable ? "подключён" : "не отвечает"}
          </div>
        </div>
        {apiAvailable === false && (
          <div className="hud-meta">Запусти API, чтобы активировать ключ.</div>
        )}
        <label className="hud-field">
          <span>Модель</span>
          <input
            type="text"
            placeholder="gpt-4.1-mini"
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
          />
        </label>
        <label className="hud-field">
          <span>Ключ</span>
          <input
            type="password"
            placeholder={t.onboarding.openaiKeyPlaceholder}
            value={openaiKey}
            onChange={(e) => setOpenaiKeyValue(e.target.value)}
          />
        </label>
        <div className="settings-actions">
          <button className="primary" disabled={savingVault || !openaiKey.trim()} onClick={handleSaveProvider}>
            {savingVault ? t.onboarding.saving : "Сохранить"}
          </button>
        </div>
        <div className="hud-meta">Файл ключа: config/local.secrets.json</div>
      </section>

      <section className="settings-card">
        <div className="settings-card-title">Разрешения macOS</div>
        <div className="settings-perms">
          <div className="settings-perm">
            <span>Screen Recording</span>
            <span className={permissions?.screen_recording ? "perm-on" : "perm-off"}>
              {permissions?.screen_recording ? "включено" : "не включено"}
            </span>
          </div>
          <div className="settings-perm">
            <span>Accessibility</span>
            <span className={permissions?.accessibility ? "perm-on" : "perm-off"}>
              {permissions?.accessibility ? "включено" : "не включено"}
            </span>
          </div>
        </div>
        <div className="hud-row">
          <button onClick={async () => setPermissions(await checkPermissions())}>{t.onboarding.permissionsCheck}</button>
        </div>
      </section>

      <button className="settings-advanced-toggle" onClick={() => setAdvancedOpen((prev) => !prev)}>
        {advancedOpen ? "Скрыть расширенные" : "Расширенные настройки"}
      </button>

      {advancedOpen && (
        <div className="settings-advanced">
          <section className="settings-card">
            <div className="settings-card-title">Режим</div>
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              {MODE_OPTIONS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </section>

          <section className="settings-card">
            <div className="settings-card-title">Автопилот</div>
            <label className="hud-field">
              <span>Интервал цикла (мс)</span>
              <input type="number" min={200} max={3000} value={loopDelayMs} onChange={(e) => setLoopDelayMs(Number(e.target.value))} />
            </label>
            <label className="hud-field">
              <span>Действий за цикл</span>
              <input type="number" min={1} max={10} value={maxActions} onChange={(e) => setMaxActions(Number(e.target.value))} />
            </label>
            <label className="hud-field">
              <span>Лимит циклов</span>
              <input type="number" min={1} max={120} value={maxCycles} onChange={(e) => setMaxCycles(Number(e.target.value))} />
            </label>
          </section>

          {projects.length > 0 && (
            <section className="settings-card">
              <div className="settings-card-title">Проект</div>
              <select value={selectedProject?.id || ""} onChange={(e) => setSelectedProject(projects.find((p) => p.id === e.target.value))}>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>{project.name}</option>
                ))}
              </select>
            </section>
          )}
        </div>
      )}
    </aside>
  );

  if (isSettingsView) {
    return (
      <div className="app settings-only" onClick={closeSettingsWindow}>
        <div className="settings-shell">{settingsPanel}</div>
      </div>
    );
  }

  return (
    <div className={`app hud-app mode-${uiMode} mode-${windowMode} ${settingsOpen ? "settings-open" : ""}`}>
      <div className="hud-shell">
        <div className="hud-top-zone" />
        <HeaderOverlay
          onClose={() => appWindow.hide()}
          onHide={() => appWindow.hide()}
          onMinimize={() => appWindow.minimize()}
          onStop={handleCancelRun}
          showStop={isActive}
        />

        <div className="hud-content">
          {uiMode === "idle" && (
            <PromptInput
              value={queryText}
              disabled={!selectedProject || !queryText.trim() || isActive}
              onChange={setQueryText}
              onSubmit={handleRunCommand}
              status={status}
            />
          )}

          {uiMode !== "idle" && (
            <section className="hud-exec">
              <StatusLine
                title={summary}
                subtitle={run?.query_text || ""}
                status={runStatusLabel}
              />
              <TaskList steps={plan} />
              <ConfirmCard
                approval={pendingApprovals[0]}
                onApprove={() => handleApprove(pendingApprovals[0].id)}
                onReject={() => handleReject(pendingApprovals[0].id)}
              />
              {isDone ? <ResultCard status={runStatusLabel} /> : null}
              {status && !isDone ? <div className="hud-status-line">{status}</div> : null}
            </section>
          )}
        </div>
      </div>

      {settingsOpen ? (
        <div className="modal-backdrop" onClick={closeSettingsWindow}>
          {settingsPanel}
        </div>
      ) : null}
    </div>
  );
}
