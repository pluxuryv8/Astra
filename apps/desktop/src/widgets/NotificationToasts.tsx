import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { useAppStore } from "../shared/store/appStore";
import { cn } from "../shared/utils/cn";
import { formatTime } from "../shared/utils/formatTime";
import IconButton from "../shared/ui/IconButton";

type ToastItem = {
  id: string;
  title: string;
  body?: string;
  ts: string;
  severity?: "info" | "success" | "warning" | "error";
};

const TOAST_TTL = 6000;

export default function NotificationToasts() {
  const notifications = useAppStore((state) => state.notifications);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const seenRef = useRef<Set<string>>(new Set());
  const timersRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    const next: ToastItem[] = [];
    notifications.forEach((item) => {
      if (seenRef.current.has(item.id)) return;
      seenRef.current.add(item.id);
      next.push(item);
    });
    if (!next.length) return;
    setToasts((prev) => [...next, ...prev].slice(0, 3));
    next.forEach((item) => {
      const timer = window.setTimeout(() => {
        setToasts((prev) => prev.filter((toast) => toast.id !== item.id));
      }, TOAST_TTL);
      timersRef.current.set(item.id, timer);
    });
  }, [notifications]);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  const dismiss = (id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      window.clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  };

  if (!toasts.length) return null;

  return (
    <div className="toast-stack">
      {toasts.map((toast) => (
        <div key={toast.id} className={cn("toast", toast.severity && `is-${toast.severity}`)}>
          <div className="toast-header">
            <div className="toast-title">{toast.title}</div>
            <IconButton type="button" size="sm" aria-label="Скрыть" onClick={() => dismiss(toast.id)}>
              <X size={14} />
            </IconButton>
          </div>
          {toast.body ? <div className="toast-body">{toast.body}</div> : null}
          <div className="toast-meta">{formatTime(toast.ts)}</div>
        </div>
      ))}
    </div>
  );
}
