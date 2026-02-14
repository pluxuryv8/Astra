import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { PanelRightOpen } from "lucide-react";
import { invoke } from "@tauri-apps/api/tauri";
import { LogicalPosition, LogicalSize, WebviewWindow, currentMonitor } from "@tauri-apps/api/window";
import ChatPage from "../pages/ChatPage";
import HistoryPage from "../pages/HistoryPage";
import MemoryPage from "../pages/MemoryPage";
import RemindersPage from "../pages/RemindersPage";
import SettingsPage from "../pages/SettingsPage";
import PermissionsPage from "../pages/PermissionsPage";
import ActivityPanel from "../widgets/ActivityPanel";
import Sidebar from "../widgets/Sidebar";
import RenameChatModal from "../widgets/RenameChatModal";
import NotificationToasts from "../widgets/NotificationToasts";
import IconButton from "../shared/ui/IconButton";
import { cn } from "../shared/utils/cn";
import { publishOverlayState } from "../shared/utils/overlayChannel";
import {
  DEFAULT_ACTIVITY_WIDTH,
  DEFAULT_SIDEBAR_WIDTH,
  useAppStore
} from "../shared/store/appStore";
import "../shared/styles/tokens.css";
import "../shared/styles/globals.css";
import "../shared/styles/grain.css";

const pageTransition = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 }
};

type ResizeTarget = "sidebar" | "activity" | null;

const OVERLAY_STORAGE_KEY = "astra.ui.overlayOpen";
const OVERLAY_MINI_KEY = "astra.ui.overlay.mini";
const OVERLAY_MINI_LEGACY_KEY = "astra.ui.overlayMini";
const OVERLAY_BOUNDS_KEY = "astra.ui.overlayBounds";
const OVERLAY_LAST_NORMAL_KEY = "astra.ui.overlay.lastNormalBounds";

const DND_THROTTLE_MS = 1200;
const MINI_HEIGHT = 120;
const OVERLAY_MARGIN = 16;

const ACTION_EVENT_TYPES = new Set([
  "micro_action_proposed",
  "micro_action_executed",
  "observation_captured",
  "step_retrying",
  "step_execution_started",
  "task_started",
  "task_progress"
]);

function deriveOverlayStatusLabel(runStatus?: string, phase?: string, mode?: string) {
  if (phase === "waiting") return "Жду подтверждения";
  if (phase === "error") return "Ошибка";
  if (runStatus === "planning") return "Планирую";
  if (runStatus === "running") return mode === "research" ? "Ищу информацию" : "В работе";
  if (runStatus === "paused") return "Думаю";
  if (runStatus === "failed" || runStatus === "canceled") return "Ошибка";
  return "Думаю";
}

function truncate(text: string, max: number) {
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

type Bounds = { x?: number; y?: number; width?: number; height?: number };

function readBounds(key: string): Bounds | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw) as Bounds;
  } catch {
    return null;
  }
}

function writeBounds(key: string, bounds: Bounds | null) {
  if (!bounds) return;
  try {
    localStorage.setItem(key, JSON.stringify(bounds));
  } catch {
    // ignore
  }
}

function setOverlayMini(value: boolean) {
  try {
    localStorage.setItem(OVERLAY_MINI_KEY, value ? "true" : "false");
    localStorage.setItem(OVERLAY_MINI_LEGACY_KEY, value ? "true" : "false");
  } catch {
    // ignore
  }
}

function readOverlayMini(): boolean {
  try {
    const raw = localStorage.getItem(OVERLAY_MINI_KEY);
    if (raw != null) return raw === "true";
    const legacy = localStorage.getItem(OVERLAY_MINI_LEGACY_KEY);
    return legacy === "true";
  } catch {
    return false;
  }
}

export default function AppShell() {
  const activePage = useAppStore((state) => state.lastSelectedPage);
  const setActivePage = useAppStore((state) => state.setLastSelectedPage);
  const sidebarWidth = useAppStore((state) => state.sidebarWidth);
  const activityWidth = useAppStore((state) => state.activityWidth);
  const setSidebarWidth = useAppStore((state) => state.setSidebarWidth);
  const setActivityWidth = useAppStore((state) => state.setActivityWidth);
  const activityOpen = useAppStore((state) => state.activityOpen);
  const setActivityOpen = useAppStore((state) => state.setActivityOpen);
  const overlayOpen = useAppStore((state) => state.overlayOpen);
  const setOverlayOpen = useAppStore((state) => state.setOverlayOpen);
  const density = useAppStore((state) => state.density);
  const grainEnabled = useAppStore((state) => state.grainEnabled);
  const bootstrap = useAppStore((state) => state.bootstrap);
  const conversationId = useAppStore((state) => state.lastSelectedChatId);
  const conversationMessages = useAppStore((state) => state.conversationMessages);
  const activity = useAppStore((state) => state.activity);
  const approvals = useAppStore((state) => state.approvals);
  const events = useAppStore((state) => state.events);
  const currentRun = useAppStore((state) => state.currentRun);
  const overlayBehavior = useAppStore((state) => state.overlayBehavior);
  const overlayCorner = useAppStore((state) => state.overlayCorner);
  const authStatus = useAppStore((state) => state.authStatus);
  const loadReminders = useAppStore((state) => state.loadReminders);

  const [resizing, setResizing] = useState<ResizeTarget>(null);
  const [autoCollapsed, setAutoCollapsed] = useState(false);
  const [actionPulse, setActionPulse] = useState(false);
  const resizeStartRef = useRef({ startX: 0, startWidth: 0, target: null as ResizeTarget });
  const actionTimeoutRef = useRef<number | null>(null);
  const lastEventIdRef = useRef<string | null>(null);
  const dndRef = useRef<{
    active: boolean;
    prevMini: boolean;
    prevBounds: Bounds | null;
    lastApply: number;
    pendingTimer: number | null;
  }>({
    active: false,
    prevMini: false,
    prevBounds: null,
    lastApply: 0,
    pendingTimer: null
  });

  const page = useMemo(() => {
    switch (activePage) {
      case "history":
        return <HistoryPage />;
      case "memory":
        return <MemoryPage />;
      case "reminders":
        return <RemindersPage />;
      case "permissions":
        return <PermissionsPage />;
      case "settings":
        return <SettingsPage />;
      default:
        return <ChatPage />;
    }
  }, [activePage]);

  const overlayPayload = useMemo(() => {
    const messages = conversationId ? conversationMessages[conversationId] || [] : [];
    let lastUser = "";
    let lastAstra = "";
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const item = messages[i];
      if (!lastUser && item.role === "user") {
        lastUser = item.text;
      }
      if (!lastAstra && item.role === "astra") {
        lastAstra = item.text;
      }
      if (lastUser && lastAstra) break;
    }

    const snippets = activity?.details?.length
      ? activity.details.slice(-3)
      : lastAstra
        ? lastAstra.split("\n").slice(0, 3)
        : [];

    return {
      statusLabel: deriveOverlayStatusLabel(currentRun?.status, activity?.phase, currentRun?.mode),
      lastUserMessage: truncate(lastUser, 140) || "—",
      lastAstraSnippet: snippets.map((line) => truncate(line.trim(), 160)).filter(Boolean),
      stepsTree: (activity?.steps || []).map((step) => ({
        id: step.id,
        title: step.title,
        status: step.status
      })),
      hasApprovalPending: approvals.some((item) => item.status === "pending"),
      updatedAt: new Date().toISOString()
    };
  }, [activity?.details, activity?.phase, activity?.steps, approvals, conversationId, conversationMessages, currentRun?.mode, currentRun?.status]);

  useEffect(() => {
    const latest = events[events.length - 1];
    if (!latest || latest.id === lastEventIdRef.current) return;
    lastEventIdRef.current = latest.id;
    if (!ACTION_EVENT_TYPES.has(latest.type)) return;
    setActionPulse(true);
    if (actionTimeoutRef.current) {
      window.clearTimeout(actionTimeoutRef.current);
    }
    actionTimeoutRef.current = window.setTimeout(() => {
      setActionPulse(false);
    }, 1800);
  }, [events]);

  useEffect(() => {
    return () => {
      if (actionTimeoutRef.current) {
        window.clearTimeout(actionTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    document.body.dataset.density = density;
    document.body.dataset.grain = grainEnabled ? "on" : "off";
  }, [density, grainEnabled]);

  useEffect(() => {
    publishOverlayState(overlayPayload);
  }, [overlayPayload]);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  useEffect(() => {
    if (authStatus !== "CONNECTED") return;
    const timer = window.setInterval(() => {
      void loadReminders();
    }, 60000);
    return () => window.clearInterval(timer);
  }, [authStatus, loadReminders]);

  useEffect(() => {
    const syncOverlay = async () => {
      if (!("__TAURI__" in window)) return;
      try {
        if (overlayOpen) {
          await invoke("overlay_show");
        } else {
          await invoke("overlay_hide");
        }
      } catch {
        // overlay window may be unavailable in dev
      }
    };
    void syncOverlay();
  }, [overlayOpen]);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== OVERLAY_STORAGE_KEY) return;
      const next = event.newValue === "true";
      setOverlayOpen(next);
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [setOverlayOpen]);

  useEffect(() => {
    if (!("__TAURI__" in window)) return;
    if (!overlayOpen) {
      if (dndRef.current.pendingTimer) {
        window.clearTimeout(dndRef.current.pendingTimer);
        dndRef.current.pendingTimer = null;
      }
      dndRef.current.active = false;
      return;
    }

    const shouldDnd = activity?.phase === "executing" || actionPulse;

    const applyDnd = async () => {
      const win = WebviewWindow.getByLabel("overlay");
      if (!win) return;

      if (shouldDnd) {
        if (!dndRef.current.active) {
          dndRef.current.active = true;
          dndRef.current.prevMini = readOverlayMini();
          dndRef.current.prevBounds = readBounds(OVERLAY_BOUNDS_KEY);
          if (dndRef.current.prevBounds) {
            writeBounds(OVERLAY_LAST_NORMAL_KEY, dndRef.current.prevBounds);
          }
        }

        if (overlayBehavior === "hide") {
          await win.hide();
          return;
        }

        await win.show();

        if (overlayBehavior === "mini") {
          if (!dndRef.current.prevMini) {
            const size = await win.innerSize();
            await win.setSize(new LogicalSize(size.width, MINI_HEIGHT));
            setOverlayMini(true);
          }
          return;
        }

        if (overlayBehavior === "corner") {
          const monitor = await currentMonitor();
          if (!monitor) return;
          const winSize = await win.outerSize();
          const { width, height } = winSize;
          const bounds = monitor.size;
          let x = OVERLAY_MARGIN;
          let y = OVERLAY_MARGIN;
          switch (overlayCorner) {
            case "top-left":
              x = OVERLAY_MARGIN;
              y = OVERLAY_MARGIN;
              break;
            case "bottom-left":
              x = OVERLAY_MARGIN;
              y = Math.max(OVERLAY_MARGIN, bounds.height - height - OVERLAY_MARGIN);
              break;
            case "bottom-right":
              x = Math.max(OVERLAY_MARGIN, bounds.width - width - OVERLAY_MARGIN);
              y = Math.max(OVERLAY_MARGIN, bounds.height - height - OVERLAY_MARGIN);
              break;
            default:
              x = Math.max(OVERLAY_MARGIN, bounds.width - width - OVERLAY_MARGIN);
              y = OVERLAY_MARGIN;
              break;
          }
          await win.setPosition(new LogicalPosition(x, y));
        }
        return;
      }

      if (!dndRef.current.active) return;
      await win.show();
      const restore = dndRef.current.prevBounds || readBounds(OVERLAY_LAST_NORMAL_KEY);
      if (restore?.width && restore?.height) {
        await win.setSize(new LogicalSize(restore.width, restore.height));
      }
      if (typeof restore?.x === "number" && typeof restore?.y === "number") {
        await win.setPosition(new LogicalPosition(restore.x, restore.y));
      }
      setOverlayMini(dndRef.current.prevMini);
      dndRef.current.active = false;
    };

    const now = Date.now();
    const elapsed = now - dndRef.current.lastApply;
    if (elapsed < DND_THROTTLE_MS) {
      if (!dndRef.current.pendingTimer) {
        dndRef.current.pendingTimer = window.setTimeout(() => {
          dndRef.current.pendingTimer = null;
          dndRef.current.lastApply = Date.now();
          void applyDnd();
        }, DND_THROTTLE_MS - elapsed);
      }
      return;
    }
    dndRef.current.lastApply = now;
    void applyDnd();
  }, [overlayOpen, overlayBehavior, overlayCorner, actionPulse, activity?.phase]);

  useEffect(() => {
    const handleResize = () => {
      const narrow = window.innerWidth < 1100;
      if (narrow && activityOpen) {
        setAutoCollapsed(true);
      }
      if (!narrow) {
        setAutoCollapsed(false);
      }
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [activityOpen]);

  const activityVisible = activityOpen && !autoCollapsed;

  const startResize = (target: ResizeTarget, event: ReactPointerEvent<HTMLDivElement>) => {
    if (!target) return;
    event.preventDefault();
    const startWidth = target === "sidebar" ? sidebarWidth : activityWidth;
    resizeStartRef.current = { startX: event.clientX, startWidth, target };
    setResizing(target);
    document.body.classList.add("is-resizing");

    const handleMove = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - resizeStartRef.current.startX;
      if (resizeStartRef.current.target === "sidebar") {
        setSidebarWidth(resizeStartRef.current.startWidth + delta);
      } else if (resizeStartRef.current.target === "activity") {
        setActivityWidth(resizeStartRef.current.startWidth - delta);
      }
    };

    const handleUp = () => {
      setResizing(null);
      document.body.classList.remove("is-resizing");
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
  };

  return (
    <div className={cn("app-shell", { "is-resizing": Boolean(resizing) })}>
      <Sidebar
        width={sidebarWidth}
        activePage={activePage}
        onNavigate={setActivePage}
      />
      <div
        className="resize-handle"
        onPointerDown={(event) => startResize("sidebar", event)}
        onDoubleClick={() => setSidebarWidth(DEFAULT_SIDEBAR_WIDTH)}
        role="separator"
        aria-orientation="vertical"
        aria-label="Изменить ширину панели чатов"
      />
      <main className="app-main">
        <AnimatePresence mode="wait">
          <motion.div
            key={activePage}
            className="page-wrapper"
            variants={pageTransition}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            {page}
          </motion.div>
        </AnimatePresence>
        {!activityVisible ? (
          <div className="activity-open">
            <IconButton
              type="button"
              variant="subtle"
              aria-label="Открыть активность"
              onClick={() => {
                setAutoCollapsed(false);
                setActivityOpen(true);
              }}
            >
              <PanelRightOpen size={18} />
            </IconButton>
            <span>Открыть активность</span>
          </div>
        ) : null}
      </main>
      {activityVisible ? (
        <div
          className="resize-handle"
          onPointerDown={(event) => startResize("activity", event)}
          onDoubleClick={() => setActivityWidth(DEFAULT_ACTIVITY_WIDTH)}
          role="separator"
          aria-orientation="vertical"
          aria-label="Изменить ширину панели активности"
        />
      ) : null}
      <ActivityPanel
        open={activityVisible}
        width={activityVisible ? activityWidth : 0}
        resizing={Boolean(resizing)}
        onToggle={() => setActivityOpen(!activityOpen)}
      />
      <RenameChatModal />
      <NotificationToasts />
    </div>
  );
}
