import { useMemo } from "react";
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

export default function NotificationToasts() {
  const notifications = useAppStore((state) => state.notifications);
  const dismissNotification = useAppStore((state) => state.dismissNotification);
  const toasts = useMemo<ToastItem[]>(() => notifications.slice(0, 3), [notifications]);

  if (!toasts.length) return null;

  return (
    <div className="toast-stack">
      {toasts.map((toast) => (
        <div key={toast.id} className={cn("toast", toast.severity && `is-${toast.severity}`)}>
          <div className="toast-header">
            <div className="toast-title">{toast.title}</div>
            <IconButton type="button" size="sm" aria-label="Скрыть" onClick={() => dismissNotification(toast.id)}>
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
