import { useEffect, useMemo, useState } from "react";
import { Copy, Trash2 } from "lucide-react";
import { formatTime } from "../shared/utils/formatTime";
import { formatRelativeTime } from "../shared/utils/formatRelativeTime";
import { useAppStore } from "../shared/store/appStore";
import Button from "../shared/ui/Button";
import Input from "../shared/ui/Input";
import Tabs from "../shared/ui/Tabs";
import IconButton from "../shared/ui/IconButton";

export default function RemindersPage() {
  const reminders = useAppStore((state) => state.reminders);
  const remindersLoading = useAppStore((state) => state.remindersLoading);
  const remindersError = useAppStore((state) => state.remindersError);
  const loadReminders = useAppStore((state) => state.loadReminders);
  const createReminder = useAppStore((state) => state.createReminder);
  const cancelReminder = useAppStore((state) => state.cancelReminder);

  const [view, setView] = useState<"pending" | "history">("pending");
  const [text, setText] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [delivery, setDelivery] = useState("local");
  const [formError, setFormError] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    void loadReminders();
  }, [loadReminders]);

  const statusLabel = (status: string, dueAtValue?: string) => {
    if (status === "failed") return "Ошибка";
    if (status === "sent") return "Отправлено";
    if (status === "cancelled") return "Отменено";
    if (dueAtValue) {
      const ts = new Date(dueAtValue).getTime();
      if (!Number.isNaN(ts) && ts < Date.now()) {
        return "Просрочено";
      }
    }
    return "Ожидает";
  };

  const deliveryLabel = (value?: string) => {
    if (value === "telegram") return "Telegram";
    return "Локально";
  };

  const pending = useMemo(() => {
    return reminders
      .filter((item) => item.status !== "sent" && item.status !== "cancelled" && item.status !== "failed")
      .sort((a, b) => (a.due_at || "").localeCompare(b.due_at || ""));
  }, [reminders]);

  const history = useMemo(() => {
    return reminders
      .filter((item) => item.status === "sent" || item.status === "failed" || item.status === "cancelled")
      .sort((a, b) => (b.due_at || "").localeCompare(a.due_at || ""));
  }, [reminders]);

  const handleCreate = async () => {
    setFormError("");
    if (!text.trim()) {
      setFormError("Введите текст напоминания.");
      return;
    }
    if (!dueAt) {
      setFormError("Укажите дату и время.");
      return;
    }
    const ts = new Date(dueAt).getTime();
    if (Number.isNaN(ts)) {
      setFormError("Некорректная дата.");
      return;
    }
    const diff = ts - Date.now();
    if (diff < 0) {
      setFormError("Время напоминания не может быть в прошлом.");
      return;
    }
    if (diff < 60_000) {
      setFormError("Слишком близкое время. Укажите хотя бы через минуту.");
      return;
    }
    setCreating(true);
    const ok = await createReminder({
      text: text.trim(),
      dueAt: new Date(dueAt).toISOString(),
      delivery
    });
    setCreating(false);
    if (ok) {
      setText("");
      setDueAt("");
      setDelivery("local");
      void loadReminders();
    }
  };

  return (
    <section className="page-stub reminders-page">
      <div className="page-header">
        <div>
          <div className="page-title">Напоминания</div>
          <div className="page-subtitle">После отправки напоминание удаляется автоматически.</div>
        </div>
      </div>

      <div className="reminders-create">
        <div className="reminders-create-title">Создать напоминание</div>
        <div className="reminders-create-grid">
          <Input
            placeholder="Текст напоминания"
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <Input
            type="datetime-local"
            value={dueAt}
            onChange={(event) => setDueAt(event.target.value)}
          />
          <select className="ui-select" value={delivery} onChange={(event) => setDelivery(event.target.value)}>
            <option value="local">Локально</option>
            <option value="telegram">Telegram</option>
          </select>
          <Button type="button" variant="primary" onClick={handleCreate} disabled={creating}>
            {creating ? "Создаю…" : "Создать"}
          </Button>
        </div>
        {formError ? <div className="inline-error">{formError}</div> : null}
      </div>

      <Tabs
        value={view}
        onChange={(value) => setView(value as "pending" | "history")}
        items={[
          { value: "pending", label: "Ожидают" },
          { value: "history", label: "История" }
        ]}
      />

      <div className="reminder-list">
        {remindersError ? (
          <div className="inline-error">
            {remindersError}
            <Button type="button" variant="ghost" onClick={() => void loadReminders()}>
              Повторить
            </Button>
          </div>
        ) : null}
        {remindersLoading ? <div className="inline-loading">Загрузка напоминаний…</div> : null}
        {(view === "pending" ? pending : history).map((reminder) => (
          <div key={reminder.id} className="reminder-card">
            <div className="reminder-card-header">
              <div>
                <div className="reminder-title">{reminder.text}</div>
                <div className="reminder-meta">
                  Время · {formatTime(reminder.due_at)} · {formatRelativeTime(reminder.due_at)}
                </div>
                <div className="reminder-meta">
                  Канал · {deliveryLabel(reminder.delivery)} · Статус · {statusLabel(reminder.status, reminder.due_at)}
                </div>
                {reminder.last_error ? <div className="reminder-note">Ошибка: {reminder.last_error}</div> : null}
              </div>
              <div className="reminder-actions">
                <IconButton
                  type="button"
                  size="sm"
                  aria-label="Скопировать"
                  onClick={() => void navigator.clipboard?.writeText(reminder.text)}
                >
                  <Copy size={16} />
                </IconButton>
                {view === "pending" ? (
                  <IconButton
                    type="button"
                    size="sm"
                    aria-label="Отменить"
                    onClick={() => void cancelReminder(reminder.id)}
                  >
                    <Trash2 size={16} />
                  </IconButton>
                ) : null}
              </div>
            </div>
          </div>
        ))}
        {!((view === "pending" ? pending : history).length) && !remindersLoading ? (
          <div className="empty-state">
            {view === "pending"
              ? "Напоминаний нет. Скажи: «в 16:00 напомни …»"
              : "История пуста."}
          </div>
        ) : null}
      </div>
    </section>
  );
}
