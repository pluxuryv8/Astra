import { useCallback, useEffect, useMemo, useState } from "react";
import { Copy, RefreshCw } from "lucide-react";
import { cn } from "../shared/utils/cn";
import { formatTime } from "../shared/utils/formatTime";
import { listRunsHistory, getRunSnapshot } from "../shared/api/runHistoryService";
import type { EventItem, Run, Snapshot } from "../shared/types/api";
import type { ActivityStepStatus } from "../shared/types/ui";
import { phaseLabel, stepLabel, useAppStore } from "../shared/store/appStore";
import Badge from "../shared/ui/Badge";
import Button from "../shared/ui/Button";
import IconButton from "../shared/ui/IconButton";
import SearchInput from "../shared/ui/SearchInput";

type StatusFilter = "all" | "success" | "error" | "waiting" | "active";

const STATUS_FILTERS: { id: StatusFilter; label: string }[] = [
  { id: "all", label: "Все" },
  { id: "success", label: "Успех" },
  { id: "error", label: "Ошибка" },
  { id: "waiting", label: "Жду подтверждения" },
  { id: "active", label: "В работе" }
];

function mapRunStatus(run: Run) {
  const status = run.status;
  if (status === "done") return { label: "Успех", tone: "success" as const, category: "success" as const };
  if (status === "failed") return { label: "Ошибка", tone: "danger" as const, category: "error" as const };
  if (status === "canceled") return { label: "Остановлен", tone: "muted" as const, category: "error" as const };
  if (status === "paused" || status === "waiting_approval" || status === "waiting_confirm") {
    return { label: "Жду подтверждения", tone: "warn" as const, category: "waiting" as const };
  }
  if (status === "planning") return { label: "Планирую", tone: "muted" as const, category: "active" as const };
  if (status === "running") return { label: "В работе", tone: "accent" as const, category: "active" as const };
  return { label: "Неизвестно", tone: "muted" as const, category: "all" as const };
}

function mapMode(mode: string) {
  if (mode === "research") return "Исследование";
  if (mode === "execute" || mode === "act") return "Действие";
  return "Обычный";
}

function formatDuration(started?: string | null, finished?: string | null) {
  if (!started) return "—";
  const start = new Date(started).getTime();
  const end = finished ? new Date(finished).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end)) return "—";
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  if (seconds < 60) return `${seconds}с`;
  const minutes = Math.floor(seconds / 60);
  const rem = seconds % 60;
  if (minutes < 60) return `${minutes}м ${rem}с`;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours < 24) return `${hours}ч ${mins}м`;
  const days = Math.floor(hours / 24);
  const hrs = hours % 24;
  return `${days}д ${hrs}ч`;
}

function formatEventTime(ts?: number) {
  if (!ts) return "";
  const value = ts > 1e12 ? ts : ts * 1000;
  return formatTime(value);
}

function eventGroupLabel(ts?: number) {
  if (!ts) return "Без времени";
  const value = ts > 1e12 ? ts : ts * 1000;
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short" }).format(new Date(value));
}

function isErrorEvent(event: EventItem) {
  if (event.level === "error") return true;
  return event.type.includes("error") || event.type.includes("failed");
}

function eventLabel(type: string) {
  const map: Record<string, string> = {
    plan_created: "План создан",
    run_started: "Запуск начат",
    run_done: "Запуск завершён",
    run_failed: "Запуск завершён с ошибкой",
    run_canceled: "Запуск отменён",
    approval_requested: "Запрос подтверждения",
    step_paused_for_approval: "Пауза для подтверждения",
    step_execution_started: "Начат шаг",
    step_execution_finished: "Шаг завершён",
    task_started: "Задача запущена",
    task_done: "Задача завершена",
    task_failed: "Ошибка задачи",
    local_llm_http_error: "Ошибка локальной модели",
    llm_request_failed: "Ошибка запроса LLM"
  };
  return map[type] ?? type;
}

function summarizeEvents(snapshot: Snapshot) {
  const summary: string[] = [];
  const events = snapshot.last_events || [];
  if (snapshot.plan?.length) summary.push("План создан");
  if (events.some((event) => event.type === "run_started") || snapshot.run.started_at) {
    summary.push("Запуск начат");
  }
  if (events.some((event) => event.type === "approval_requested" || event.type === "step_paused_for_approval")) {
    summary.push("Ожидается подтверждение");
  }
  const error = events.find(isErrorEvent);
  if (error) {
    summary.push(`Обнаружена ошибка: ${eventLabel(error.type)}`);
  }
  if (snapshot.run.status === "done") summary.push("Выполнение завершено");
  return summary;
}

function normalizeStepStatus(status?: string): ActivityStepStatus {
  if (status === "done") return "done";
  if (status === "running") return "active";
  if (status === "failed" || status === "canceled") return "error";
  return "pending";
}

function buildActivity(snapshot: Snapshot) {
  const pending = snapshot.approvals?.some((approval) => approval.status === "pending");
  const phase: "planning" | "executing" | "review" | "waiting" | "error" = pending
    ? "waiting"
    : snapshot.run.status === "failed"
      ? "error"
      : snapshot.run.status === "done"
        ? "review"
        : snapshot.run.status === "running"
          ? "executing"
          : "planning";
  const steps = (snapshot.plan || []).map((step) => ({
    id: step.id,
    title: step.title,
    status: normalizeStepStatus(step.status)
  }));
  return { phase, steps };
}

export default function HistoryPage() {
  const projectId = useAppStore((state) => state.projectId);
  const conversations = useAppStore((state) => state.conversations);
  const setLastSelectedPage = useAppStore((state) => state.setLastSelectedPage);
  const setLastSelectedChatId = useAppStore((state) => state.setLastSelectedChatId);
  const selectConversation = useAppStore((state) => state.selectConversation);

  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [eventsFilter, setEventsFilter] = useState<Set<string>>(new Set());
  const [eventsLimit, setEventsLimit] = useState(120);
  const [eventsCompact, setEventsCompact] = useState(true);

  const loadRuns = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    const result = await listRunsHistory(projectId, 200);
    if (!result.ok) {
      setError(result.error.detail || "Не удалось загрузить историю");
      setLoading(false);
      return;
    }
    const sorted = [...result.data].sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    setRuns(sorted);
    setLoading(false);
  }, [projectId]);

  const loadSnapshot = async (runId: string) => {
    setSnapshotLoading(true);
    setSnapshotError(null);
    const result = await getRunSnapshot(runId);
    if (!result.ok) {
      setSnapshot(null);
      setSnapshotError(result.error.detail || "Не удалось загрузить детали запуска");
      setSnapshotLoading(false);
      return;
    }
    setSnapshot(result.data);
    setEventsFilter(new Set());
    setEventsLimit(120);
    setSnapshotLoading(false);
  };

  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    if (!selectedRunId && runs.length) {
      const first = runs[0];
      setSelectedRunId(first.id);
      void loadSnapshot(first.id);
    }
  }, [runs, selectedRunId]);

  const filteredRuns = useMemo(() => {
    const query = search.trim().toLowerCase();
    return runs.filter((run) => {
      if (filter !== "all") {
        const mapped = mapRunStatus(run);
        if (mapped.category !== filter) return false;
      }
      if (!query) return true;
      return run.query_text.toLowerCase().includes(query);
    });
  }, [runs, search, filter]);

  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId) || null, [runs, selectedRunId]);
  const activeConversation = useMemo(() => {
    if (!selectedRun) return null;
    return conversations.find((conv) => conv.run_ids.includes(selectedRun.id)) || null;
  }, [conversations, selectedRun]);

  const events = useMemo(() => {
    if (!snapshot?.last_events) return [];
    return [...snapshot.last_events].sort((a, b) => (a.ts || 0) - (b.ts || 0));
  }, [snapshot?.last_events]);

  const eventTypes = useMemo(() => Array.from(new Set(events.map((evt) => evt.type))).sort(), [events]);

  const filteredEvents = useMemo(() => {
    const filterSet = eventsFilter;
    const base = filterSet.size
      ? events.filter((evt) => filterSet.has(evt.type))
      : events;
    return base.slice(-eventsLimit);
  }, [events, eventsFilter, eventsLimit]);

  const errorEvents = useMemo(() => events.filter(isErrorEvent), [events]);

  const summary = useMemo(() => (snapshot ? summarizeEvents(snapshot) : []), [snapshot]);

  const activity = useMemo(() => (snapshot ? buildActivity(snapshot) : null), [snapshot]);

  return (
    <section className="page-stub history-page">
      <div className="page-header">
        <div>
          <div className="page-title">История запусков</div>
          <div className="page-subtitle">Список запусков по текущему проекту.</div>
        </div>
        <div className="history-actions">
          <SearchInput placeholder="Поиск по запросу" value={search} onChange={(event) => setSearch(event.target.value)} />
          <IconButton type="button" aria-label="Обновить" onClick={() => void loadRuns()}>
            <RefreshCw size={16} />
          </IconButton>
        </div>
      </div>

      <div className="history-layout">
        <div className="history-list">
          <div className="history-filters">
            {STATUS_FILTERS.map((item) => (
              <Badge
                key={item.id}
                tone={filter === item.id ? "accent" : "muted"}
                size="sm"
                role="button"
                tabIndex={0}
                className="history-filter-chip"
                onClick={() => setFilter(item.id)}
              >
                {item.label}
              </Badge>
            ))}
          </div>

          {loading ? <div className="inline-loading">Загрузка истории…</div> : null}
          {error ? (
            <div className="inline-error">
              {error}
              <Button type="button" variant="ghost" onClick={() => void loadRuns()}>
                Повторить
              </Button>
            </div>
          ) : null}

          {filteredRuns.map((run) => {
            const status = mapRunStatus(run);
            return (
              <button
                key={run.id}
                type="button"
                className={cn("run-row", { "is-active": run.id === selectedRunId })}
                onClick={() => {
                  setSelectedRunId(run.id);
                  void loadSnapshot(run.id);
                }}
              >
                <div className="run-row-header">
                  <Badge tone={status.tone} size="sm">
                    {status.label}
                  </Badge>
                  <span className="run-row-mode">{mapMode(run.mode)}</span>
                </div>
                <div className="run-row-title">{run.query_text || "Без запроса"}</div>
                <div className="run-row-meta">
                  {formatTime(run.started_at || run.created_at)}
                  {" · "}
                  {formatDuration(run.started_at, run.finished_at)}
                </div>
              </button>
            );
          })}

          {!filteredRuns.length && !loading ? (
            <div className="empty-state">Запусков пока нет.</div>
          ) : null}
        </div>

        <div className="run-detail">
          {!selectedRun ? (
            <div className="empty-state">Выберите запуск, чтобы увидеть детали.</div>
          ) : (
            <>
              <div className="run-card">
                <div className="run-card-header">
                  <div>
                    <div className="run-card-title">Детали запуска</div>
                    <div className="run-card-subtitle">{selectedRun.query_text || "Без запроса"}</div>
                  </div>
                  <div className="run-card-actions">
                    <Button type="button" variant="ghost" onClick={() => void loadSnapshot(selectedRun.id)}>
                      Обновить
                    </Button>
                    {activeConversation ? (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => {
                          setLastSelectedPage("chat");
                          setLastSelectedChatId(activeConversation.id);
                          void selectConversation(activeConversation.id);
                        }}
                      >
                        Открыть в чате
                      </Button>
                    ) : null}
                  </div>
                </div>
                <div className="run-card-grid">
                  <div>
                    <div className="run-card-label">Статус</div>
                    <div className="run-card-value">{mapRunStatus(selectedRun).label}</div>
                  </div>
                  <div>
                    <div className="run-card-label">Режим</div>
                    <div className="run-card-value">{mapMode(selectedRun.mode)}</div>
                  </div>
                  <div>
                    <div className="run-card-label">Старт</div>
                    <div className="run-card-value">{formatTime(selectedRun.started_at || selectedRun.created_at)}</div>
                  </div>
                  <div>
                    <div className="run-card-label">Длительность</div>
                    <div className="run-card-value">{formatDuration(selectedRun.started_at, selectedRun.finished_at)}</div>
                  </div>
                </div>
              </div>

              {snapshotLoading ? <div className="inline-loading">Загрузка деталей…</div> : null}
              {snapshotError ? <div className="inline-error">{snapshotError}</div> : null}

              {snapshot ? (
                <>
                  <div className="run-card">
                    <div className="run-card-title">Запрос пользователя</div>
                    <div className="run-card-query">{snapshot.run.query_text || "—"}</div>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => void navigator.clipboard?.writeText(snapshot.run.query_text || "")}
                    >
                      <Copy size={14} />
                      Скопировать
                    </Button>
                  </div>

                  <div className="run-card">
                    <div className="run-card-title">Ключевые события</div>
                    {summary.length ? (
                      <ul className="run-summary-list">
                        {summary.map((line) => (
                          <li key={line}>{line}</li>
                        ))}
                      </ul>
                    ) : (
                      <div className="run-empty">Нет ключевых событий</div>
                    )}
                  </div>

                  <div className="run-card">
                    <div className="run-card-title">Активность</div>
                    <div className="run-activity-phase">
                      <span>Фаза</span>
                      <Badge tone="muted" size="sm">
                        {phaseLabel(activity?.phase || "planning")}
                      </Badge>
                    </div>
                    <div className="run-activity-steps">
                      {(activity?.steps || []).length ? (
                        activity?.steps.map((step) => (
                          <div key={step.id} className="run-activity-step">
                            <span className="run-activity-step-title">{step.title}</span>
                            <span className="run-activity-step-status">{stepLabel(step.status)}</span>
                          </div>
                        ))
                      ) : (
                        <div className="run-empty">Шаги пока не сформированы.</div>
                      )}
                    </div>
                  </div>

                  <div className="run-card">
                    <div className="run-card-header">
                      <div>
                        <div className="run-card-title">События</div>
                        <div className="run-card-subtitle">Последние события запуска.</div>
                      </div>
                      <div className="run-card-actions">
                        <Button type="button" variant="ghost" onClick={() => setEventsCompact(!eventsCompact)}>
                          {eventsCompact ? "Подробно" : "Кратко"}
                        </Button>
                      </div>
                    </div>
                    <div className="run-event-filters">
                      {eventTypes.map((type) => (
                        <Badge
                          key={type}
                          tone={eventsFilter.has(type) ? "accent" : "muted"}
                          size="sm"
                          role="button"
                          tabIndex={0}
                          className="history-filter-chip"
                          onClick={() => {
                            const next = new Set(eventsFilter);
                            if (next.has(type)) next.delete(type);
                            else next.add(type);
                            setEventsFilter(next);
                          }}
                        >
                          {eventLabel(type)}
                        </Badge>
                      ))}
                      {eventsFilter.size ? (
                        <Badge
                          tone="muted"
                          size="sm"
                          role="button"
                          tabIndex={0}
                          className="history-filter-chip"
                          onClick={() => setEventsFilter(new Set())}
                        >
                          Сбросить фильтры
                        </Badge>
                      ) : null}
                    </div>

                    <div className="event-list">
                      {filteredEvents.length ? (
                        (() => {
                          let lastGroup = "";
                          return filteredEvents.map((event) => {
                            const group = eventGroupLabel(event.ts);
                            const showGroup = group !== lastGroup;
                            lastGroup = group;
                            return (
                              <div key={event.id} className="event-item">
                                {showGroup ? <div className="event-group">{group}</div> : <div />}
                                <div className="event-body">
                                  <div className="event-header">
                                    <span className="event-time">{formatEventTime(event.ts)}</span>
                                    <span className="event-type">{eventLabel(event.type)}</span>
                                  </div>
                                  <div className="event-message">{event.message || "—"}</div>
                                  {!eventsCompact && event.payload ? (
                                    <div className="event-payload">
                                      {JSON.stringify(event.payload).slice(0, 220)}
                                    </div>
                                  ) : null}
                                </div>
                              </div>
                            );
                          });
                        })()
                      ) : (
                        <div className="run-empty">Событий пока нет.</div>
                      )}
                    </div>
                    {events.length > eventsLimit ? (
                      <Button type="button" variant="ghost" onClick={() => setEventsLimit(eventsLimit + 120)}>
                        Загрузить ещё
                      </Button>
                    ) : null}
                  </div>

                  <div className="run-card">
                    <div className="run-card-header">
                      <div>
                        <div className="run-card-title">Ошибки</div>
                        <div className="run-card-subtitle">Ошибки запуска и диагностика.</div>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => {
                          const lines = errorEvents.map((evt) => {
                            const payload = evt.payload || {};
                            const provider =
                              typeof payload.provider === "string"
                                ? payload.provider
                                : typeof payload.llm_provider === "string"
                                  ? payload.llm_provider
                                  : "";
                            const status =
                              typeof payload.http_status === "number"
                                ? payload.http_status
                                : typeof payload.status === "number"
                                  ? payload.status
                                  : "";
                            const artifact = typeof payload.artifact_path === "string" ? payload.artifact_path : "";
                            return [
                              `Тип: ${evt.type}`,
                              `Сообщение: ${evt.message}`,
                              provider ? `Провайдер: ${provider}` : null,
                              status ? `HTTP: ${status}` : null,
                              artifact ? `Артефакт: ${artifact}` : null
                            ]
                              .filter(Boolean)
                              .join(" | ");
                          });
                          void navigator.clipboard?.writeText(lines.join("\n"));
                        }}
                      >
                        Скопировать диагностику
                      </Button>
                    </div>
                    {errorEvents.length ? (
                      <div className="run-error-list">
                        {errorEvents.map((evt) => {
                          const payload = evt.payload || {};
                          const provider =
                            typeof payload.provider === "string"
                              ? payload.provider
                              : typeof payload.llm_provider === "string"
                                ? payload.llm_provider
                                : null;
                          const status =
                            typeof payload.http_status === "number"
                              ? payload.http_status
                              : typeof payload.status === "number"
                                ? payload.status
                                : null;
                          const artifact = typeof payload.artifact_path === "string" ? payload.artifact_path : null;
                          return (
                            <div key={evt.id} className="run-error-card">
                              <div className="run-error-header">
                                <Badge tone="danger" size="sm">
                                  {eventLabel(evt.type)}
                                </Badge>
                                <span className="run-error-time">{formatEventTime(evt.ts)}</span>
                              </div>
                              <div className="run-error-message">{evt.message || "Ошибка без сообщения"}</div>
                              <div className="run-error-meta">
                                {provider ? <span>Провайдер: {provider}</span> : null}
                                {status ? <span>HTTP: {status}</span> : null}
                                {artifact ? <span>Артефакт: {artifact}</span> : null}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div className="run-empty">Ошибок не обнаружено.</div>
                    )}
                  </div>
                </>
              ) : null}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
