import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Loader2,
  Pause,
  PanelRightClose,
  Square,
  Layers
} from "lucide-react";
import type { ReactNode } from "react";
import { useMemo } from "react";
import { cn } from "../shared/utils/cn";
import Badge from "../shared/ui/Badge";
import Button from "../shared/ui/Button";
import IconButton from "../shared/ui/IconButton";
import Tooltip from "../shared/ui/Tooltip";
import { phaseLabel, stepLabel, useAppStore } from "../shared/store/appStore";
import type { ActivityStepStatus } from "../shared/types/ui";

export type ActivityPanelProps = {
  open: boolean;
  width: number;
  resizing: boolean;
  onToggle: () => void;
};

const statusTone: Record<ActivityStepStatus, "success" | "warn" | "muted" | "danger"> = {
  done: "success",
  active: "warn",
  pending: "muted",
  error: "danger"
};

const statusIcon: Record<ActivityStepStatus, ReactNode> = {
  done: <CheckCircle2 size={16} />,
  active: <Loader2 size={16} className="spin" />,
  pending: <Circle size={16} />,
  error: <AlertTriangle size={16} />
};

export default function ActivityPanel({ open, width, resizing, onToggle }: ActivityPanelProps) {
  const activity = useAppStore((state) => state.activity);
  const approvals = useAppStore((state) => state.approvals);
  const detailed = useAppStore((state) => state.activityDetailed);
  const setDetailed = useAppStore((state) => state.setActivityDetailed);
  const pauseActiveRun = useAppStore((state) => state.pauseActiveRun);
  const cancelActiveRun = useAppStore((state) => state.cancelActiveRun);
  const streamState = useAppStore((state) => state.streamState);
  const currentRun = useAppStore((state) => state.currentRun);
  const events = useAppStore((state) => state.events);
  const overlayOpen = useAppStore((state) => state.overlayOpen);
  const setOverlayOpen = useAppStore((state) => state.setOverlayOpen);

  const phase = activity ? phaseLabel(activity.phase) : "Планирую";
  const pendingApproval = approvals.find((item) => item.status === "pending");
  const canPause = currentRun?.status === "running";
  const canStop =
    currentRun?.status === "running" || currentRun?.status === "paused" || currentRun?.status === "planning";
  const errorEvent = useMemo(() => {
    return [...events].reverse().find((event) => event.type === "local_llm_http_error");
  }, [events]);
  const artifactPath = useMemo(() => {
    const payload = errorEvent?.payload;
    if (payload && typeof payload === "object" && "artifact_path" in payload) {
      const value = payload.artifact_path;
      return typeof value === "string" ? value : null;
    }
    return null;
  }, [errorEvent]);

  return (
    <aside
      className={cn("activity-panel", { "is-hidden": !open, "is-resizing": resizing })}
      style={{ width }}
    >
      <div className="activity-header">
        <div className="activity-title">Активность</div>
        <div className="activity-actions">
          <IconButton
            type="button"
            size="sm"
            variant="subtle"
            aria-label="Пауза"
            onClick={() => void pauseActiveRun()}
            disabled={!canPause}
          >
            <Pause size={16} />
          </IconButton>
          <IconButton
            type="button"
            size="sm"
            variant="subtle"
            aria-label="Остановить"
            onClick={() => void cancelActiveRun()}
            disabled={!canStop}
          >
            <Square size={16} />
          </IconButton>
          <Tooltip label={overlayOpen ? "Скрыть оверлей" : "Показать оверлей"}>
            <span>
              <IconButton
                type="button"
                size="sm"
                variant="subtle"
                aria-label="Оверлей"
                onClick={() => setOverlayOpen(!overlayOpen)}
                active={overlayOpen}
              >
                <Layers size={16} />
              </IconButton>
            </span>
          </Tooltip>
          <IconButton type="button" size="sm" aria-label="Свернуть" onClick={onToggle}>
            <PanelRightClose size={16} />
          </IconButton>
        </div>
      </div>

      <AnimatePresence initial={false} mode="wait">
        {open ? (
          <motion.div
            key="activity-content"
            className="activity-content"
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 10 }}
            transition={{ duration: 0.2 }}
          >
            <div className="activity-phase">
              <div>
                <div className="activity-phase-label">Текущая фаза</div>
                <div className="activity-phase-title">{phase}</div>
              </div>
              <button
                type="button"
                className={cn("activity-toggle", { "is-active": detailed })}
                onClick={() => setDetailed(!detailed)}
              >
                {detailed ? "Подробно" : "Кратко"}
              </button>
            </div>

            {streamState !== "live" ? (
              <div className="activity-connection">
                <Badge
                  tone={streamState === "reconnecting" ? "warn" : streamState === "offline" ? "danger" : "muted"}
                  size="sm"
                >
                  {streamState === "connecting"
                    ? "События: подключаюсь…"
                    : streamState === "reconnecting"
                      ? "События: переподключаюсь…"
                      : streamState === "offline"
                        ? "События: нет соединения"
                        : "События: ожидание"}
                </Badge>
              </div>
            ) : null}

            <div className="activity-steps">
              {activity?.steps?.length ? (
                activity.steps.map((step) => (
                  <motion.div
                    layout
                    key={step.id}
                    className="activity-step"
                    data-status={step.status}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <span className="activity-step-icon" data-status={step.status}>
                      {statusIcon[step.status]}
                    </span>
                    <span className="activity-step-title">{step.title}</span>
                    <Badge tone={statusTone[step.status]} size="sm">
                      {stepLabel(step.status)}
                    </Badge>
                  </motion.div>
                ))
              ) : (
                <div className="activity-empty">Шаги появятся после планирования.</div>
              )}
            </div>

            {detailed && activity?.details?.length ? (
              <div className="activity-details">
                {activity.details.map((line) => (
                  <div key={line} className="activity-detail-item">
                    {line}
                  </div>
                ))}
              </div>
            ) : null}

            {pendingApproval ? (
              <div className="activity-approval">
                <div className="activity-approval-title">Требуется подтверждение</div>
                <div>{pendingApproval.title || "Нужен ответ перед продолжением работы."}</div>
                {pendingApproval.description ? (
                  <div className="activity-approval-detail">{pendingApproval.description}</div>
                ) : null}
              </div>
            ) : null}

            {errorEvent ? (
              <div className="activity-error">
                <div className="activity-error-title">Ошибка локальной модели</div>
                <div className="activity-error-text">
                  {errorEvent.message || "Проверьте параметры локальной модели."}
                </div>
                {artifactPath ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      navigator.clipboard?.writeText(artifactPath).catch(() => null);
                    }}
                  >
                    Показать детали
                  </Button>
                ) : null}
              </div>
            ) : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </aside>
  );
}
