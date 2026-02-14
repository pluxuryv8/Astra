import { useMemo, useState } from "react";
import type { AutopilotActionEvent, AutopilotStatePayload, HudEventLine, PlanStep, SnapshotMetrics, Task } from "../types";

type RunScreenProps = {
  phaseLabel: string;
  runStatusLabel: string;
  goal: string;
  nowTitle: string;
  nowReason?: string;
  plan: PlanStep[];
  activeStepId?: string;
  tasks: Task[];
  metrics: SnapshotMetrics | null;
  autopilotState: AutopilotStatePayload | null;
  autopilotActions: AutopilotActionEvent[];
  events: HudEventLine[];
  needsUser: boolean;
  isDone: boolean;
  compact: boolean;
  onNewRun: () => void;
  infoLine?: string | null;
};

function statusText(status?: string | null) {
  if (!status) return "—";
  if (status === "created" || status === "queued") return "Ожидание";
  if (status === "running") return "В работе";
  if (status === "paused") return "Пауза";
  if (status === "done") return "Готово";
  if (status === "failed") return "Ошибка";
  if (status === "canceled") return "Отменено";
  if (status === "waiting_approval") return "Ждёт подтверждение";
  if (status === "waiting_confirm") return "Ждёт подтверждение";
  if (status === "needs_user") return "Нужно действие";
  return status;
}

function formatTime(ts?: number) {
  if (!ts) return "";
  const date = new Date(ts);
  return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

function shortHash(hash?: string) {
  if (!hash) return "—";
  if (hash.length <= 12) return hash;
  return `${hash.slice(0, 6)}…${hash.slice(-4)}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function formatAutopilotAction(action: Record<string, unknown>) {
  const type = typeof action.type === "string" ? action.type : "action";
  const x = typeof action.x === "number" ? action.x : null;
  const y = typeof action.y === "number" ? action.y : null;
  const text = typeof action.text === "string" ? action.text : null;
  const key = typeof action.key === "string" ? action.key : null;
  const ms = typeof action.ms === "number" ? action.ms : null;

  if (type === "type" && text) return `Ввод текста: "${text.length > 80 ? `${text.slice(0, 80)}…` : text}"`;
  if (type === "key" && key) return `Клавиша: ${key}`;
  if (type === "wait") return `Ожидание: ${ms ?? 500}мс`;
  if (type === "scroll") {
    const dy = typeof action.dy === "number" ? action.dy : typeof action.delta_y === "number" ? action.delta_y : null;
    return `Скролл${dy ? `: ${dy > 0 ? "вниз" : "вверх"} (${Math.abs(dy)})` : ""}`;
  }
  if (type === "drag") {
    const toX = typeof action.to_x === "number" ? action.to_x : typeof action.x2 === "number" ? action.x2 : null;
    const toY = typeof action.to_y === "number" ? action.to_y : typeof action.y2 === "number" ? action.y2 : null;
    if (x !== null && y !== null && toX !== null && toY !== null) return `Перетаскивание: (${x}, ${y}) → (${toX}, ${toY})`;
    return "Перетаскивание";
  }
  if (type === "move_mouse") {
    if (x !== null && y !== null) return `Курсор: (${x}, ${y})`;
    return "Движение курсора";
  }
  if (type === "click" || type === "double_click") {
    const label = type === "double_click" ? "Двойной клик" : "Клик";
    if (x !== null && y !== null) return `${label}: (${x}, ${y})`;
    return label;
  }
  return type;
}

export default function RunScreen({
  phaseLabel,
  runStatusLabel,
  goal,
  nowTitle,
  nowReason,
  plan,
  activeStepId,
  tasks,
  metrics,
  autopilotState,
  autopilotActions,
  events,
  needsUser,
  isDone,
  compact,
  onNewRun,
  infoLine
}: RunScreenProps) {
  const [logExpanded, setLogExpanded] = useState(false);
  const [expandedKey, setExpandedKey] = useState<string | null>(null);

  const coverage = metrics?.coverage || null;
  const tasksDone = useMemo(() => tasks.filter((t) => t.status === "done").length, [tasks]);
  const tasksTotal = tasks.length;
  const stepTitleById = useMemo(() => {
    const map = new Map<string, string>();
    for (const step of plan) map.set(step.id, step.title);
    return map;
  }, [plan]);
  const recentTasks = useMemo(() => {
    if (!tasks.length) return [];
    return [...tasks].slice(-6).reverse();
  }, [tasks]);

  const sortedEvents = useMemo(() => [...(events || [])].reverse(), [events]);
  const maxVisible = logExpanded ? 18 : 6;
  const visibleEvents = sortedEvents.slice(0, maxVisible);
  const hasMore = sortedEvents.length > maxVisible;

  const plannedActions = useMemo(() => {
    if (!autopilotState?.actions?.length) return [];
    const out: string[] = [];
    for (const action of autopilotState.actions.slice(0, 6)) {
      if (isRecord(action)) out.push(formatAutopilotAction(action));
    }
    return out;
  }, [autopilotState]);

  const executedActions = useMemo(() => {
    return autopilotActions.slice(-6).map((item) => formatAutopilotAction(item.payload.action));
  }, [autopilotActions]);

  return (
    <section className={`run ${compact ? "compact" : ""}`}>
      <header className="run-header">
        <div className="run-kicker">
          <span className="run-phase">{phaseLabel}</span>
          <span className="run-pill">{runStatusLabel}</span>
          {coverage ? (
            <span className="run-meta">
              {coverage.done}/{coverage.total}
            </span>
          ) : tasksTotal ? (
            <span className="run-meta">
              {tasksDone}/{tasksTotal}
            </span>
          ) : null}
          {needsUser ? <span className="run-warn">нужно действие</span> : null}
        </div>
        <div className="run-goal">{goal}</div>
      </header>

      <div className="glass-card now">
        <div className="card-label">Сейчас</div>
        <div className="now-title">{nowTitle}</div>
        {nowReason ? <div className="now-reason">{nowReason}</div> : null}
      </div>

      <div className="glass-card track">
        <div className="card-head">
          <div className="card-title">Трек</div>
          <div className="card-sub">
            {autopilotState ? (
              <>
                <span>{autopilotState.phase === "thinking" ? "думает" : "делает"}</span>
                <span className="dot" />
                <span>
                  цикл {autopilotState.cycle}/{autopilotState.max_cycles}
                </span>
              </>
            ) : (
              <span>по плану</span>
            )}
          </div>
        </div>

        {plan.length === 0 ? (
          <div className="empty">План ещё собирается</div>
        ) : (
          <ul className="plan-list">
            {plan.map((step, index) => {
              const isActive = Boolean(activeStepId && step.id === activeStepId);
              const number = typeof step.step_index === "number" ? step.step_index + 1 : index + 1;
              const status = statusText(step.status);
              return (
                <li key={step.id} className={`plan-item ${isActive ? "active" : ""}`}>
                  <div className="plan-title">
                    <span className="plan-n">{number}.</span> {step.title}
                  </div>
                  <div className="plan-status">{status}</div>
                </li>
              );
            })}
          </ul>
        )}

        {!compact && recentTasks.length ? (
          <div className="subsection">
            <div className="card-label">Задачи</div>
            <ul className="task-list">
              {recentTasks.map((task) => {
                const stepTitle = task.plan_step_id ? stepTitleById.get(task.plan_step_id) : null;
                const attempt = typeof task.attempt === "number" ? task.attempt : null;
                const error = typeof task.error === "string" && task.error ? task.error : null;
                const line = [
                  statusText(task.status),
                  stepTitle ? `• ${stepTitle}` : null,
                  attempt ? `• попытка ${attempt}` : null,
                  error ? `• ${error.length > 60 ? `${error.slice(0, 60)}…` : error}` : null
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <li key={task.id} className="task-item">
                    {line}
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </div>

      {!compact && autopilotState ? (
        <div className="glass-card autopilot">
          <div className="card-head">
            <div className="card-title">Автопилот</div>
            <div className="card-sub">{statusText(autopilotState.status)}</div>
          </div>

          <div className="autopilot-grid">
            <div className="autopilot-row">
              <span className="card-label">Экран</span>
              <span className="mono">{shortHash(autopilotState.screen_hash)}</span>
            </div>
            <div className="autopilot-row">
              <span className="card-label">Решение</span>
              <span className="mono">{shortHash(autopilotState.action_hash)}</span>
            </div>
          </div>

          {plannedActions.length ? (
            <div className="subsection">
              <div className="card-label">Планируемые действия</div>
              <ul className="chip-list">
                {plannedActions.map((text, idx) => (
                  <li key={idx} className="chip">
                    {text}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {executedActions.length ? (
            <div className="subsection">
              <div className="card-label">Последние действия</div>
              <ul className="action-list">
                {executedActions.map((text, idx) => (
                  <li key={idx} className="action-item">
                    {text}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="glass-card log">
        <div className="card-head">
          <div className="card-title">События</div>
          <div className="card-sub">
            {hasMore ? (
              <button className="text-button" onClick={() => setLogExpanded((v) => !v)}>
                {logExpanded ? "Свернуть" : "Показать ещё"}
              </button>
            ) : null}
          </div>
        </div>

        {visibleEvents.length === 0 ? (
          <div className="empty">Пока тихо</div>
        ) : (
          <ul className="events-list">
            {visibleEvents.map((event) => {
              const isExpanded = expandedKey === event.key;
              const payload = event.payload && Object.keys(event.payload).length ? JSON.stringify(event.payload, null, 2) : null;
              return (
                <li
                  key={event.key}
                  className={`event-item ${isExpanded ? "expanded" : ""}`}
                  onClick={() => setExpandedKey(isExpanded ? null : event.key)}
                >
                  <div className="event-head">
                    <span className="event-time">{formatTime(event.ts)}</span>
                    <span className="event-type">
                      {event.count > 1 ? `${event.count}×` : ""} {event.message}
                    </span>
                  </div>
                  {isExpanded && payload ? <pre className="event-payload">{payload}</pre> : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {isDone ? (
        <div className="glass-card done">
          <div className="done-title">Завершено</div>
          <div className="done-text">{runStatusLabel}</div>
          <button className="btn primary" onClick={onNewRun}>
            Новый запрос
          </button>
        </div>
      ) : null}

      {infoLine ? <div className="status-line">{infoLine}</div> : null}
    </section>
  );
}
