import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Minus, X } from "lucide-react";
import { appWindow, LogicalPosition, LogicalSize, WebviewWindow } from "@tauri-apps/api/window";
import { invoke } from "@tauri-apps/api/tauri";
import type { OverlayState } from "../shared/types/ui";
import { subscribeOverlayState } from "../shared/utils/overlayChannel";
import { cn } from "../shared/utils/cn";
import "../shared/styles/tokens.css";
import "../shared/styles/globals.css";
import "../shared/styles/grain.css";
import "../shared/styles/overlay.css";

const OVERLAY_BOUNDS_KEY = "astra.ui.overlayBounds";
const OVERLAY_OPEN_KEY = "astra.ui.overlayOpen";
const OVERLAY_MINI_KEY = "astra.ui.overlay.mini";
const OVERLAY_MINI_LEGACY_KEY = "astra.ui.overlayMini";

const DEFAULT_WIDTH = 420;
const DEFAULT_HEIGHT = 220;
const MINI_HEIGHT = 120;

const FALLBACK_STATE: OverlayState = {
  statusLabel: "Думаю",
  lastUserMessage: "—",
  lastAstraSnippet: [],
  stepsTree: [],
  hasApprovalPending: false,
  updatedAt: new Date().toISOString()
};

type Bounds = { x?: number; y?: number; width?: number; height?: number };

function loadBounds(): Bounds | null {
  try {
    const raw = localStorage.getItem(OVERLAY_BOUNDS_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as Bounds;
  } catch {
    return null;
  }
}

function saveBounds(bounds: Bounds) {
  try {
    localStorage.setItem(OVERLAY_BOUNDS_KEY, JSON.stringify(bounds));
  } catch {
    // ignore
  }
}

function loadBoolean(key: string, fallback = false) {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    return raw === "true";
  } catch {
    return fallback;
  }
}

function loadMiniState() {
  const modern = loadBoolean(OVERLAY_MINI_KEY, false);
  if (modern) return true;
  return loadBoolean(OVERLAY_MINI_LEGACY_KEY, false);
}

export default function OverlayApp() {
  const [overlayState, setOverlayState] = useState<OverlayState>(FALLBACK_STATE);
  const [stepsOpen, setStepsOpen] = useState(false);
  const [isMini, setIsMini] = useState(() => loadMiniState());
  const boundsRef = useRef<Bounds>({ width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });
  const prevHeightRef = useRef<number>(DEFAULT_HEIGHT);

  useEffect(() => {
    localStorage.setItem(OVERLAY_OPEN_KEY, "true");
  }, []);

  useEffect(() => {
    document.body.dataset.view = "overlay";
    return () => {
      delete document.body.dataset.view;
    };
  }, []);

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== OVERLAY_MINI_KEY && event.key !== OVERLAY_MINI_LEGACY_KEY) return;
      if (event.newValue == null) return;
      setIsMini(event.newValue === "true");
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  useEffect(() => {
    const stored = loadBounds();
    if (stored) {
      boundsRef.current = { ...boundsRef.current, ...stored };
    }
    const applyBounds = async () => {
      const width = boundsRef.current.width ?? DEFAULT_WIDTH;
      const height = boundsRef.current.height ?? DEFAULT_HEIGHT;
      try {
        await appWindow.setSize(new LogicalSize(width, height));
      } catch {
        // ignore
      }
      if (typeof boundsRef.current.x === "number" && typeof boundsRef.current.y === "number") {
        try {
          await appWindow.setPosition(new LogicalPosition(boundsRef.current.x, boundsRef.current.y));
        } catch {
          // ignore
        }
      }
    };
    void applyBounds();

    const unlistenMovePromise = appWindow.onMoved((event) => {
      boundsRef.current = { ...boundsRef.current, x: event.payload.x, y: event.payload.y };
      saveBounds(boundsRef.current);
    });
    const unlistenResizePromise = appWindow.onResized((event) => {
      boundsRef.current = { ...boundsRef.current, width: event.payload.width, height: event.payload.height };
      saveBounds(boundsRef.current);
    });

    return () => {
      void unlistenMovePromise.then((unlisten) => unlisten());
      void unlistenResizePromise.then((unlisten) => unlisten());
    };
  }, []);

  useEffect(() => {
    const unsubscribe = subscribeOverlayState((state) => {
      setOverlayState(state);
    });
    return () => {
      unsubscribe();
    };
  }, []);

  const steps = useMemo(() => overlayState.stepsTree || [], [overlayState.stepsTree]);
  const visibleSteps = stepsOpen ? steps : steps.slice(0, 5);

  const toggleMini = async () => {
    const size = await appWindow.innerSize();
    if (!isMini) {
      prevHeightRef.current = size.height || DEFAULT_HEIGHT;
      await appWindow.setSize(new LogicalSize(size.width, MINI_HEIGHT));
      boundsRef.current = { ...boundsRef.current, height: MINI_HEIGHT };
      saveBounds(boundsRef.current);
      localStorage.setItem(OVERLAY_MINI_KEY, "true");
      localStorage.setItem(OVERLAY_MINI_LEGACY_KEY, "true");
      setIsMini(true);
      return;
    }
    const restoreHeight = prevHeightRef.current || DEFAULT_HEIGHT;
    await appWindow.setSize(new LogicalSize(size.width, restoreHeight));
    boundsRef.current = { ...boundsRef.current, height: restoreHeight };
    saveBounds(boundsRef.current);
    localStorage.setItem(OVERLAY_MINI_KEY, "false");
    localStorage.setItem(OVERLAY_MINI_LEGACY_KEY, "false");
    setIsMini(false);
  };

  const handleOpenMain = async () => {
    const main = WebviewWindow.getByLabel("main");
    if (!main) return;
    try {
      await main.show();
      await main.setFocus();
    } catch {
      // ignore
    }
  };

  const handleClose = async () => {
    localStorage.setItem(OVERLAY_OPEN_KEY, "false");
    try {
      await invoke("overlay_hide");
    } catch {
      // ignore
    }
  };

  return (
    <div className="overlay-root">
      <div className={cn("overlay-card", { "is-mini": isMini })}>
        <header className="overlay-header" data-tauri-drag-region>
          <div className="overlay-title" data-tauri-drag-region>
            Astra
          </div>
          <div className={cn("overlay-status", { error: overlayState.statusLabel === "Ошибка" })} data-tauri-drag-region>
            {overlayState.statusLabel}
          </div>
        </header>

        {overlayState.hasApprovalPending ? (
          <div className="overlay-approval">Нужно подтверждение</div>
        ) : null}

        <div className="overlay-body">
          <div className="overlay-line">
            <span className="overlay-label">Ты</span>
            <span className="overlay-text">{overlayState.lastUserMessage || "—"}</span>
          </div>
          <div className="overlay-line">
            <span className="overlay-label">Astra</span>
            <span className="overlay-text">{overlayState.lastAstraSnippet?.[0] || "—"}</span>
          </div>
          {overlayState.lastAstraSnippet?.slice(1).length ? (
            <div className="overlay-snippets">
              {overlayState.lastAstraSnippet.slice(1).map((line) => (
                <div key={line} className="overlay-snippet">
                  {line}
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="overlay-footer">
          <button
            type="button"
            className={cn("overlay-btn", { primary: overlayState.hasApprovalPending })}
            onClick={handleOpenMain}
          >
            Открыть Astra
          </button>
          <button type="button" className="overlay-btn" onClick={() => setStepsOpen(!stepsOpen)}>
            {stepsOpen ? "Скрыть шаги" : "Развернуть шаги"}
            {stepsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          <button type="button" className="overlay-btn ghost" onClick={toggleMini}>
            <Minus size={14} />
            {isMini ? "Развернуть" : "Свернуть"}
          </button>
          <button type="button" className="overlay-btn ghost" onClick={handleClose}>
            <X size={14} />
            Закрыть
          </button>
        </div>

        <div className={cn("overlay-steps", { open: stepsOpen })}>
          {visibleSteps.length ? (
            visibleSteps.map((step) => (
              <div key={step.id} className={cn("overlay-step", step.status)}>
                <span className="overlay-step-title">{step.title}</span>
                <span className="overlay-step-status">
                  {step.status === "done"
                    ? "Готово"
                    : step.status === "active"
                      ? "В работе"
                      : step.status === "error"
                        ? "Ошибка"
                        : "Ожидание"}
                </span>
              </div>
            ))
          ) : (
            <div className="overlay-empty">Шаги появятся после планирования.</div>
          )}
        </div>
      </div>
    </div>
  );
}
