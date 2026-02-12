import { useEffect, useMemo, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { appWindow, LogicalSize, PhysicalPosition, PhysicalSize, currentMonitor } from "@tauri-apps/api/window";
import { exit } from "@tauri-apps/api/process";
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
import TopHoverBar from "./ui/TopHoverBar";
import IdleScreen from "./ui/IdleScreen";
import RunScreen from "./ui/RunScreen";
import SettingsPanel from "./ui/SettingsPanel";
import ConfirmModal from "./ui/ConfirmModal";
import type {
  Approval,
  AutopilotActionEvent,
  AutopilotActionPayload,
  AutopilotStatePayload,
  EventItem,
  HudEventLine,
  PlanStep,
  Project,
  ProjectSettings,
  Run,
  SnapshotMetrics,
  Task
} from "./types";

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
  "approval_resolved",
  "approval_approved",
  "approval_rejected",
  "step_cancelled_by_user",
  "user_action_required",
  "autopilot_state",
  "autopilot_action"
];

const MODE_OPTIONS = [
  { value: "plan_only", label: "Только план" },
  { value: "research", label: "Исследование" },
  { value: "execute_confirm", label: "Выполнение с подтверждением" },
  { value: "autopilot_safe", label: "Автопилот (безопасный)" }
];

const HUD_WINDOW_MODE = "astra_window_mode";
const HUD_WINDOW_SIZE = "astra_window_size";
const HUD_OVERLAY_SIZE = "astra_overlay_size";
const HUD_OVERLAY_POS = "astra_overlay_pos";
const HUD_OVERLAY_SIZE_BEFORE_COMPACT = "astra_overlay_size_before_compact";
const RUN_MODE_KEY = "astra_run_mode";
const ANIM_BG_KEY = "astra_anim_bg";
const COMPACT_KEY = "astra_ui_compact";
const SETTINGS_VIEW = "settings";
const POLL_INTERVAL_MS = 4500;
const DEFAULT_OVERLAY_LOGICAL = { width: 520, height: 360 };
const DEFAULT_WINDOW_LOGICAL = { width: 860, height: 600 };
const DEFAULT_COMPACT_LOGICAL = { width: 420, height: 240 };
const EVENT_BUFFER_LIMIT = 420;

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

function phaseLabel(phase: string) {
  if (phase === "idle") return "Ожидание";
  if (phase === "thinking") return "Думает";
  if (phase === "executing") return "Выполняет";
  if (phase === "waiting_confirm") return "Ожидает подтверждения";
  if (phase === "done") return "Готово";
  return "";
}

type PermissionsStatus = {
  screen_recording?: boolean;
  accessibility?: boolean;
  message?: string;
};

function getErrorMessage(err: unknown, fallback: string) {
  if (err instanceof Error) return err.message || fallback;
  if (typeof err === "string") return err;
  return fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isAutopilotStatePayload(payload: unknown): payload is AutopilotStatePayload {
  if (!isRecord(payload)) return false;
  return typeof payload.goal === "string" && Array.isArray(payload.plan) && typeof payload.step_summary === "string";
}

function isAutopilotActionPayload(payload: unknown): payload is AutopilotActionPayload {
  if (!isRecord(payload)) return false;
  if (!isRecord(payload.action)) return false;
  return typeof payload.index === "number" && typeof payload.total === "number";
}

function aggregateEvents(events: EventItem[]): HudEventLine[] {
  const out: HudEventLine[] = [];
  const filtered = (events || []).filter((e) => e.type !== "autopilot_state" && e.type !== "autopilot_action");
  for (const event of filtered) {
    const prev = out[out.length - 1];
    if (prev && prev.type === event.type && prev.message === event.message) {
      prev.count += 1;
      prev.ts = event.ts ?? prev.ts;
      prev.payload = event.payload || prev.payload;
      continue;
    }
    out.push({
      key: `${event.seq ?? event.id}-${event.type}`,
      type: event.type,
      message: event.message,
      ts: event.ts,
      count: 1,
      payload: event.payload
    });
  }
  return out;
}

export default function App() {
  const isSettingsView = new URLSearchParams(window.location.search).get("view") === SETTINGS_VIEW;
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [plan, setPlan] = useState<PlanStep[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [metrics, setMetrics] = useState<SnapshotMetrics | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [queryText, setQueryText] = useState("");
  const [mode, setMode] = useState<string>(() => localStorage.getItem(RUN_MODE_KEY) || "execute_confirm");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(isSettingsView);
  const [permissions, setPermissions] = useState<PermissionsStatus | null>(null);
  const [apiAvailable, setApiAvailable] = useState<boolean | null>(null);
  const [openaiKey, setOpenaiKey] = useState("");
  const [apiKeyReady, setApiKeyReady] = useState(false);
  const [keyStored, setKeyStored] = useState(false);
  const [savingKey, setSavingKey] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<{ text: string; tone: "success" | "error" | "info" } | null>(null);
  const [modelName, setModelName] = useState("gpt-4.1");
  const [animatedBg, setAnimatedBg] = useState<boolean>(() => localStorage.getItem(ANIM_BG_KEY) !== "0");
  const [isCompact, setIsCompact] = useState<boolean>(() => localStorage.getItem(COMPACT_KEY) === "1");
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [windowMode, setWindowMode] = useState<"window" | "overlay">("overlay");
  const [streamState, setStreamState] = useState<"idle" | "live" | "reconnecting" | "polling">("idle");
  const [dismissedApprovalId, setDismissedApprovalId] = useState<string | null>(null);
  const windowModeRef = useRef<"window" | "overlay">("overlay");
  const isFullscreenRef = useRef(false);

  const eventsRef = useRef<EventItem[]>([]);
  const seenSeqRef = useRef<Set<number>>(new Set());
  const eventSourceRef = useRef<EventSource | null>(null);
  const refreshInFlight = useRef(false);
  const refreshQueued = useRef(false);
  const refreshTimerRef = useRef<number | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const lastEventIdRef = useRef<number>(0);
  const reconnectAttemptRef = useRef(0);

  const pendingApprovals = useMemo(() => approvals.filter((a) => a.status === "pending"), [approvals]);
  const visibleApproval = pendingApprovals.find((a) => a.id !== dismissedApprovalId) || null;
  const autopilotState = useMemo<AutopilotStatePayload | null>(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const event = events[i];
      if (event.type !== "autopilot_state") continue;
      if (isAutopilotStatePayload(event.payload)) return event.payload;
    }
    return null;
  }, [events]);
  const autopilotActions = useMemo<AutopilotActionEvent[]>(() => {
    const out: AutopilotActionEvent[] = [];
    for (const event of events) {
      if (event.type !== "autopilot_action") continue;
      if (!isAutopilotActionPayload(event.payload)) continue;
      out.push({ seq: event.seq, ts: event.ts, payload: event.payload });
    }
    return out.slice(-24);
  }, [events]);
  const displayEvents = useMemo(() => aggregateEvents(events), [events]);

  useEffect(() => {
    windowModeRef.current = windowMode;
  }, [windowMode]);

  useEffect(() => {
    isFullscreenRef.current = isFullscreen;
  }, [isFullscreen]);

  useEffect(() => {
    localStorage.setItem(RUN_MODE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    localStorage.setItem(ANIM_BG_KEY, animatedBg ? "1" : "0");
  }, [animatedBg]);

  useEffect(() => {
    localStorage.setItem(COMPACT_KEY, isCompact ? "1" : "0");
  }, [isCompact]);

  useEffect(() => {
    if (!settingsMessage) return;
    const timer = setTimeout(() => setSettingsMessage(null), 5000);
    return () => clearTimeout(timer);
  }, [settingsMessage]);

  useEffect(() => {
    if (isSettingsView) {
      setSettingsOpen(true);
    }
  }, [isSettingsView]);

  useEffect(() => {
    initAuth()
      .then(async () => {
        await loadProjects();
        const last = localStorage.getItem("astra_last_run_id");
        if (last) {
          await refreshSnapshot(last);
          void openEventStream(last);
        }
      })
      .catch((err: unknown) => setStatusMessage(getErrorMessage(err, "Не удалось инициализировать доступ")));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (isSettingsView) return;
    appWindow
      .isFullscreen()
      .then(setIsFullscreen)
      .catch(() => setIsFullscreen(false));
  }, [isSettingsView]);

  useEffect(() => {
    if (!selectedProject && projects.length > 0) {
      setSelectedProject(projects[0]);
    }
  }, [projects, selectedProject]);

  useEffect(() => {
    if (!selectedProject) return;
    const settings = selectedProject.settings || {};
    const llm = (settings.llm || {}) as ProjectSettings["llm"];
    setModelName(llm?.model || "gpt-4.1");
  }, [selectedProject]);

  useEffect(() => {
    checkPermissions()
      .then(setPermissions)
      .catch(() => setPermissions(null));
  }, []);

  useEffect(() => {
    if (!settingsOpen && !isSettingsView) return;
    const checkApi = async () => {
      const ok = await checkApiStatus();
      setApiAvailable(ok);
    };
    checkApi();
  }, [settingsOpen, isSettingsView]);

  useEffect(() => {
    if (!settingsOpen && !isSettingsView) return;
    const checkLocalKey = async () => {
      try {
        const res = await getLocalOpenAIStatus();
        setKeyStored(res.stored);
      } catch {
        setKeyStored(false);
      }
    };
    checkLocalKey();
  }, [settingsOpen, isSettingsView]);

  useEffect(() => {
    if (isSettingsView) return;
    const saved = (localStorage.getItem(HUD_WINDOW_MODE) as "window" | "overlay") || "overlay";
    if (saved === "overlay") {
      void applyOverlayMode();
    } else {
      void applyWindowMode();
    }
    const unlistenResize = appWindow.onResized(async () => {
      if (isFullscreenRef.current) return;
      const size = await appWindow.innerSize();
      if (windowModeRef.current === "overlay") {
        localStorage.setItem(HUD_OVERLAY_SIZE, JSON.stringify({ width: size.width, height: size.height }));
      } else {
        localStorage.setItem(HUD_WINDOW_SIZE, JSON.stringify({ width: size.width, height: size.height }));
      }
    });
    const unlistenMove = appWindow.onMoved(async () => {
      if (isFullscreenRef.current) return;
      if (windowModeRef.current !== "overlay") return;
      const pos = await appWindow.outerPosition();
      localStorage.setItem(HUD_OVERLAY_POS, JSON.stringify({ x: pos.x, y: pos.y }));
    });
    return () => {
      unlistenResize.then((fn) => fn());
      unlistenMove.then((fn) => fn());
    };
  }, [isSettingsView]);

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
  }, [run, windowMode, isSettingsView]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (settingsOpen || isSettingsView) {
          closeSettingsWindow();
        } else if (visibleApproval) {
          setDismissedApprovalId(visibleApproval.id);
        } else {
          appWindow.hide();
        }
      }
      if (event.metaKey && event.key.toLowerCase() === "q") {
        event.preventDefault();
        void exit(0);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [settingsOpen, isSettingsView, visibleApproval]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!approvals.length) {
      setDismissedApprovalId(null);
      return;
    }
    if (visibleApproval && visibleApproval.id !== dismissedApprovalId) {
      setDismissedApprovalId(null);
    }
  }, [approvals, dismissedApprovalId, visibleApproval]);

  useEffect(() => {
    return () => {
      cleanupEventStream();
      stopPolling();
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (refreshTimerRef.current) {
        window.clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, []);

  async function applyWindowMode(persist = true, overrideSize?: { width: number; height: number }) {
    const scale = await appWindow.scaleFactor();
    const sizeRaw = localStorage.getItem(HUD_WINDOW_SIZE);
    const stored = sizeRaw ? (JSON.parse(sizeRaw) as { width?: number; height?: number }) : null;
    const fallback = {
      width: Math.round(DEFAULT_WINDOW_LOGICAL.width * scale),
      height: Math.round(DEFAULT_WINDOW_LOGICAL.height * scale)
    };
    const size = overrideSize || (stored?.width && stored?.height ? { width: stored.width, height: stored.height } : fallback);
    await appWindow.setDecorations(true);
    await appWindow.setAlwaysOnTop(false);
    await appWindow.setFullscreen(false);
    await appWindow.setResizable(true);
    await appWindow.setMinSize(new LogicalSize(560, 360));
    await sleep(60);
    await appWindow.setSize(new PhysicalSize(size.width, size.height));
    if (persist) {
      localStorage.setItem(HUD_WINDOW_MODE, "window");
    }
    setWindowMode("window");
    setIsFullscreen(false);
  }

  async function applyOverlayMode(persist = true, override?: { size?: { width: number; height: number }; pos?: { x: number; y: number } | null }) {
    const scale = await appWindow.scaleFactor();
    const sizeRaw = localStorage.getItem(HUD_OVERLAY_SIZE);
    const posRaw = localStorage.getItem(HUD_OVERLAY_POS);
    const storedSize = sizeRaw ? (JSON.parse(sizeRaw) as { width?: number; height?: number }) : null;
    const storedPos = posRaw ? (JSON.parse(posRaw) as { x?: number; y?: number }) : null;
    const fallback = {
      width: Math.round(DEFAULT_OVERLAY_LOGICAL.width * scale),
      height: Math.round(DEFAULT_OVERLAY_LOGICAL.height * scale)
    };
    const size = override?.size || (storedSize?.width && storedSize?.height ? { width: storedSize.width, height: storedSize.height } : fallback);
    const requestedPos = override?.pos === undefined ? storedPos : override.pos;

    const monitor = await currentMonitor();
    const bounds = monitor
      ? {
          x: monitor.position.x,
          y: monitor.position.y,
          width: monitor.size.width,
          height: monitor.size.height
        }
      : null;
    const windowSize = bounds ? { width: Math.min(size.width, bounds.width), height: Math.min(size.height, bounds.height) } : size;
    const centered = bounds
      ? {
          x: Math.round(bounds.x + (bounds.width - windowSize.width) / 2),
          y: Math.round(bounds.y + (bounds.height - windowSize.height) / 2)
        }
      : { x: 60, y: 60 };
    const rawPos = requestedPos && typeof requestedPos.x === "number" && typeof requestedPos.y === "number" ? { x: requestedPos.x, y: requestedPos.y } : centered;
    const pos =
      bounds
        ? {
            x: Math.min(Math.max(rawPos.x, bounds.x), bounds.x + Math.max(0, bounds.width - windowSize.width)),
            y: Math.min(Math.max(rawPos.y, bounds.y), bounds.y + Math.max(0, bounds.height - windowSize.height))
          }
        : rawPos;

    await appWindow.setDecorations(false);
    await appWindow.setAlwaysOnTop(true);
    await appWindow.setFullscreen(false);
    await appWindow.setResizable(true);
    await appWindow.setMinSize(new LogicalSize(420, 240));
    await sleep(60);
    await appWindow.setSize(new PhysicalSize(windowSize.width, windowSize.height));
    await appWindow.setPosition(new PhysicalPosition(pos.x, pos.y));
    if (persist) {
      localStorage.setItem(HUD_WINDOW_MODE, "overlay");
    }
    setWindowMode("overlay");
    setIsFullscreen(false);
  }

  async function toggleOverlayMode() {
    if (windowMode === "overlay") {
      await applyWindowMode();
    } else {
      await applyOverlayMode();
    }
  }

  async function toggleFullscreen() {
    try {
      const next = !isFullscreenRef.current;
      await appWindow.setFullscreen(next);
      setIsFullscreen(next);
    } catch (err: unknown) {
      setStatusMessage(getErrorMessage(err, "Не удалось переключить полный экран"));
    }
  }

  async function toggleCompact() {
    const next = !isCompact;
    setIsCompact(next);
    if (isSettingsView) return;
    if (windowModeRef.current !== "overlay") return;
    try {
      const scale = await appWindow.scaleFactor();
      if (next) {
        const current = await appWindow.innerSize();
        localStorage.setItem(HUD_OVERLAY_SIZE_BEFORE_COMPACT, JSON.stringify({ width: current.width, height: current.height }));
        await applyOverlayMode(true, {
          size: { width: Math.round(DEFAULT_COMPACT_LOGICAL.width * scale), height: Math.round(DEFAULT_COMPACT_LOGICAL.height * scale) }
        });
      } else {
        const prevRaw = localStorage.getItem(HUD_OVERLAY_SIZE_BEFORE_COMPACT);
        const prev = prevRaw ? (JSON.parse(prevRaw) as { width?: number; height?: number }) : null;
        if (prev?.width && prev?.height) {
          await applyOverlayMode(true, { size: { width: prev.width, height: prev.height } });
        } else {
          await applyOverlayMode(true);
        }
      }
    } catch (err: unknown) {
      setStatusMessage(getErrorMessage(err, "Не удалось переключить компактный режим"));
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
    if (!selectedProject) return;
    const current = selectedProject.settings || {};
    const llm = (current.llm || {}) as NonNullable<ProjectSettings["llm"]>;
    const nextSettings = {
      ...current,
      llm: {
        ...llm,
        provider: "openai",
        base_url: llm.base_url || "https://api.openai.com/v1",
        model: modelName.trim() || llm.model || "gpt-4.1"
      }
    };
    const updated = await updateProject(projectId, { settings: nextSettings });
    setSelectedProject(updated);
  }

  async function ensureApiKey(): Promise<boolean> {
    if (apiKeyReady) return true;
    try {
      const res = await getLocalOpenAIStatus();
      setKeyStored(res.stored);
      if (!res.stored) {
        setStatusMessage("Ключ не найден. Открой настройки и сохрани его.");
        return false;
      }
      setApiKeyReady(true);
      return true;
    } catch (err: unknown) {
      setStatusMessage(getErrorMessage(err, "Не удалось проверить ключ."));
      return false;
    }
  }

  async function handleSaveSettings() {
    if (!selectedProject) {
      setSettingsMessage({ text: "Проект не найден", tone: "error" });
      return;
    }
    try {
      setSavingKey(true);
      if (openaiKey.trim()) {
        await storeOpenAIKeyLocal(openaiKey.trim());
        setKeyStored(true);
        setApiKeyReady(true);
        setOpenaiKey("");
      }
      await applySettingsToProject(selectedProject.id);
      setSettingsMessage({
        text: openaiKey.trim() ? "Ключ и модель сохранены" : "Модель сохранена",
        tone: "success"
      });
    } catch (err: unknown) {
      setSettingsMessage({ text: getErrorMessage(err, "Не удалось сохранить"), tone: "error" });
    } finally {
      setSavingKey(false);
    }
  }

  async function handleRunCommand() {
    if (!selectedProject || !queryText.trim()) return;
    try {
      const response = await createRun(selectedProject.id, { query_text: queryText, mode });
      if (response.kind === "clarify") {
        const questions = response.questions?.filter(Boolean) || [];
        setStatusMessage(questions.join(" ") || "Нужны уточнения.");
        return;
      }
      if (response.kind === "chat") {
        setStatusMessage(response.chat_response || "Ответ готов.");
        setQueryText("");
        return;
      }
      if (response.kind === "act" && response.run) {
        const newRun = response.run;
        setRun(newRun);
        localStorage.setItem("astra_last_run_id", newRun.id);
        setPlan([]);
        setTasks([]);
        setMetrics(null);
        setApprovals([]);
        setDismissedApprovalId(null);
        resetEventBuffer();
        setStatusMessage(null);
        void openEventStream(newRun.id);
        await createPlan(newRun.id);
        await refreshSnapshot(newRun.id);
        await startRun(newRun.id);
        setQueryText("");
        return;
      }
      setStatusMessage("Не удалось определить режим запуска.");
    } catch (err: unknown) {
      setStatusMessage(getErrorMessage(err, "Не удалось запустить"));
    }
  }

  async function handleCancelRun() {
    if (!run) return;
    try {
      await cancelRun(run.id);
      await refreshSnapshot(run.id);
    } catch (err: unknown) {
      setStatusMessage(getErrorMessage(err, "Не удалось остановить"));
    }
  }

  async function handleApprove(approvalId: string) {
    await approve(approvalId);
    setDismissedApprovalId(null);
    if (run) await refreshSnapshot(run.id);
  }

  async function handleReject(approvalId: string) {
    await reject(approvalId);
    setDismissedApprovalId(null);
    if (run) await refreshSnapshot(run.id);
  }

  function ingestEvents(incoming?: EventItem[] | null) {
    if (!incoming?.length) return;
    const next = [...eventsRef.current];
    let changed = false;
    for (const event of incoming) {
      const seq = typeof event.seq === "number" ? event.seq : null;
      if (seq !== null) {
        if (seenSeqRef.current.has(seq)) continue;
        seenSeqRef.current.add(seq);
        lastEventIdRef.current = Math.max(lastEventIdRef.current, seq);
      }
      next.push(event);
      changed = true;
    }
    if (!changed) return;
    next.sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));

    let trimmed = next;
    if (trimmed.length > EVENT_BUFFER_LIMIT) {
      trimmed = trimmed.slice(-EVENT_BUFFER_LIMIT);
      const newSeen = new Set<number>();
      for (const event of trimmed) {
        if (typeof event.seq === "number") newSeen.add(event.seq);
      }
      seenSeqRef.current = newSeen;
    }

    eventsRef.current = trimmed;
    setEvents(trimmed);
  }

  async function refreshSnapshot(runId?: string) {
    const id = runId || run?.id;
    if (!id) return;
    const snapshot = await getSnapshot(id);
    setRun(snapshot.run);
    setPlan(snapshot.plan || []);
    setTasks(snapshot.tasks || []);
    setMetrics(snapshot.metrics || null);
    setApprovals(snapshot.approvals || []);
    ingestEvents(snapshot.last_events || []);
  }

  async function refreshSnapshotSafe(runId: string) {
    if (refreshInFlight.current) {
      refreshQueued.current = true;
      return;
    }
    refreshInFlight.current = true;
    try {
      await refreshSnapshot(runId);
    } finally {
      refreshInFlight.current = false;
      if (refreshQueued.current) {
        refreshQueued.current = false;
        void refreshSnapshotSafe(runId);
      }
    }
  }

  function queueSnapshotRefresh(runId: string, delayMs = 650) {
    if (refreshTimerRef.current) return;
    refreshTimerRef.current = window.setTimeout(() => {
      refreshTimerRef.current = null;
      void refreshSnapshotSafe(runId);
    }, delayMs);
  }

  function cleanupEventStream() {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (refreshTimerRef.current) {
      window.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }

  function stopPolling() {
    if (pollTimerRef.current) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }

  function resetEventBuffer() {
    eventsRef.current = [];
    seenSeqRef.current = new Set();
    setEvents([]);
    lastEventIdRef.current = 0;
  }

  function resetRunView() {
    cleanupEventStream();
    stopPolling();
    resetEventBuffer();
    setStreamState("idle");
    reconnectAttemptRef.current = 0;
    setRun(null);
    setPlan([]);
    setTasks([]);
    setMetrics(null);
    setApprovals([]);
    setDismissedApprovalId(null);
    setStatusMessage(null);
  }

  function startPolling(runId: string) {
    if (pollTimerRef.current) return;
    setStreamState("polling");
    pollTimerRef.current = window.setInterval(() => {
      void refreshSnapshotSafe(runId);
    }, POLL_INTERVAL_MS);
  }

  function scheduleReconnect(runId: string) {
    if (reconnectTimerRef.current) return;
    const attempt = reconnectAttemptRef.current + 1;
    reconnectAttemptRef.current = attempt;
    const base = Math.min(20000, 700 * Math.pow(2, attempt));
    const jitter = Math.round(base * (0.25 * Math.random()));
    const delay = base + jitter;
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      void openEventStream(runId);
    }, delay);
  }

  async function openEventStream(runId: string) {
    cleanupEventStream();
    stopPolling();
    const token = getSessionToken();
    if (!token) {
      await initAuth();
    }
    const safeToken = getSessionToken();
    const url = new URL(`${apiBase()}/runs/${runId}/events`);
    if (safeToken) {
      url.searchParams.set("token", safeToken);
    }
    if (lastEventIdRef.current) {
      url.searchParams.set("last_event_id", String(lastEventIdRef.current));
    }

    const es = new EventSource(url.toString());
    es.onopen = () => {
      setStreamState("live");
      reconnectAttemptRef.current = 0;
      stopPolling();
      queueSnapshotRefresh(runId, 0);
    };
    es.onerror = () => {
      setStreamState("reconnecting");
      es.close();
      startPolling(runId);
      scheduleReconnect(runId);
    };
    EVENT_TYPES.forEach((type) => {
      es.addEventListener(type, (evt) => handleEvent(type, evt as MessageEvent));
    });
    eventSourceRef.current = es;
  }

  async function handleEvent(type: string, evt: MessageEvent) {
    try {
      const event = JSON.parse(evt.data) as EventItem;
      ingestEvents([event]);
      const targetRunId = event.run_id || run?.id;
      if (targetRunId && type !== "autopilot_action") {
        const delay =
          type === "run_done" || type === "run_failed" || type === "run_canceled"
            ? 0
            : type === "approval_requested" || type === "approval_approved" || type === "approval_rejected"
              ? 0
              : type === "task_progress"
                ? 1100
                : 650;
        queueSnapshotRefresh(targetRunId, delay);
      }
      if (type === "run_done" || type === "run_failed" || type === "run_canceled") {
        setStatusMessage(statusLabel(type.replace("run_", "")));
      }
    } catch (err: unknown) {
      setStatusMessage(getErrorMessage(err, "Не удалось прочитать событие"));
    }
  }

  const runStatus = run?.status || "idle";
  const isActive = ["running", "paused"].includes(runStatus);
  const isDone = ["done", "failed", "canceled"].includes(runStatus);
  const needsUser = Boolean(autopilotState?.needs_user) || autopilotState?.status === "needs_user";
  const waitingConfirm = Boolean(visibleApproval) || autopilotState?.status === "waiting_confirm" || needsUser;

  let uiPhase = "idle";
  if (isDone) uiPhase = "done";
  else if (waitingConfirm) uiPhase = "waiting_confirm";
  else if (isActive || run) {
    if (autopilotState?.phase === "thinking" || runStatus === "created") {
      uiPhase = "thinking";
    } else {
      uiPhase = "executing";
    }
  }

  const activeStep = plan.find((step) => step.status === "running") || plan.find((step) => step.status === "created") || plan[0];
  const goal = autopilotState?.goal || run?.query_text || "—";
  const summary = autopilotState?.step_summary || activeStep?.title || run?.query_text || "—";
  const reason = autopilotState?.reason || autopilotState?.ask_confirm?.reason || "";
  const runStatusLabel = statusLabel(runStatus);

  const streamHint =
    streamState === "reconnecting"
      ? "Переподключение к событиям…"
      : streamState === "polling"
        ? "События: опрос снимка"
        : null;

  if (isSettingsView) {
    return (
      <div className="app settings-only">
        <SettingsPanel
          modelName={modelName}
          onModelChange={setModelName}
          openaiKey={openaiKey}
          onOpenaiKeyChange={setOpenaiKey}
          keyStored={keyStored}
          apiAvailable={apiAvailable}
          permissions={permissions}
          mode={mode}
          modeOptions={MODE_OPTIONS}
          onModeChange={setMode}
          animatedBg={animatedBg}
          onAnimatedBgChange={setAnimatedBg}
          onSave={handleSaveSettings}
          saving={savingKey}
          message={settingsMessage}
          onClose={closeSettingsWindow}
          onRefreshPermissions={async () => setPermissions(await checkPermissions())}
          isStandalone
        />
      </div>
    );
  }

  return (
    <div className={`app mode-${windowMode} ${settingsOpen ? "settings-open" : ""} ${isCompact ? "is-compact" : ""} ${isFullscreen ? "is-fullscreen" : ""}`}>
      <div className={`hud-shell ${animatedBg ? "animated" : ""} ${isCompact ? "compact" : ""} ${isFullscreen ? "fullscreen" : ""}`}>
        <div className="hud-top-zone" data-tauri-drag-region />
        <TopHoverBar
          onHide={() => appWindow.hide()}
          onMinimize={() => appWindow.minimize()}
          onToggleFullscreen={toggleFullscreen}
          isFullscreen={isFullscreen}
          onToggleCompact={toggleCompact}
          isCompact={isCompact}
          onStop={handleCancelRun}
          stopEnabled={Boolean(run && !isDone)}
          onOpenSettings={() => setSettingsOpen(true)}
          streamState={streamState}
        />

        <div className="hud-content">
          {uiPhase === "idle" ? (
            <IdleScreen
              value={queryText}
              disabled={!selectedProject}
              onChange={setQueryText}
              onSubmit={handleRunCommand}
              status={statusMessage || streamHint}
            />
          ) : (
            <RunScreen
              phaseLabel={phaseLabel(uiPhase)}
              runStatusLabel={runStatusLabel}
              goal={goal}
              nowTitle={summary}
              nowReason={reason}
              plan={plan}
              activeStepId={activeStep?.id}
              tasks={tasks}
              metrics={metrics}
              autopilotState={autopilotState}
              autopilotActions={autopilotActions}
              events={displayEvents}
              needsUser={needsUser}
              isDone={isDone}
              compact={isCompact}
              onNewRun={resetRunView}
              infoLine={statusMessage || streamHint}
            />
          )}
        </div>

        {visibleApproval ? (
          <ConfirmModal
            approval={visibleApproval}
            onApprove={() => handleApprove(visibleApproval.id)}
            onReject={() => handleReject(visibleApproval.id)}
            onDismiss={() => setDismissedApprovalId(visibleApproval.id)}
          />
        ) : null}

        {settingsOpen ? (
          <div className="settings-backdrop" onClick={closeSettingsWindow}>
            <SettingsPanel
              modelName={modelName}
              onModelChange={setModelName}
              openaiKey={openaiKey}
              onOpenaiKeyChange={setOpenaiKey}
              keyStored={keyStored}
              apiAvailable={apiAvailable}
              permissions={permissions}
              mode={mode}
              modeOptions={MODE_OPTIONS}
              onModeChange={setMode}
              animatedBg={animatedBg}
              onAnimatedBgChange={setAnimatedBg}
              onSave={handleSaveSettings}
              saving={savingKey}
              message={settingsMessage}
              onClose={closeSettingsWindow}
              onRefreshPermissions={async () => setPermissions(await checkPermissions())}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}
