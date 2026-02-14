import { X } from "lucide-react";
import { formatTime } from "../shared/utils/formatTime";
import { cn } from "../shared/utils/cn";
import { useAppStore } from "../shared/store/appStore";
import Sheet from "../shared/ui/Sheet";
import Button from "../shared/ui/Button";
import IconButton from "../shared/ui/IconButton";

export type NotificationCenterProps = {
  open: boolean;
  onClose: () => void;
};

export default function NotificationCenter({ open, onClose }: NotificationCenterProps) {
  const notifications = useAppStore((state) => state.notifications);
  const dismissNotification = useAppStore((state) => state.dismissNotification);
  const clearNotifications = useAppStore((state) => state.clearNotifications);

  return (
    <Sheet open={open} side="right" onClose={onClose} className="notification-sheet">
      <div className="notification-header">
        <div>
          <div className="notification-title">Уведомления</div>
          <div className="notification-subtitle">Последние события Astra.</div>
        </div>
        <div className="notification-actions">
          <Button type="button" variant="ghost" onClick={() => clearNotifications()}>
            Очистить
          </Button>
          <IconButton type="button" aria-label="Закрыть" onClick={onClose}>
            <X size={16} />
          </IconButton>
        </div>
      </div>
      <div className="notification-list">
        {notifications.length ? (
          notifications.map((item) => (
            <div key={item.id} className={cn("notification-item", item.severity && `is-${item.severity}`)}>
              <div className="notification-item-header">
                <div className="notification-item-title">{item.title}</div>
                <IconButton
                  type="button"
                  size="sm"
                  aria-label="Скрыть"
                  onClick={() => dismissNotification(item.id)}
                >
                  <X size={14} />
                </IconButton>
              </div>
              {item.body ? <div className="notification-item-body">{item.body}</div> : null}
              <div className="notification-item-meta">{formatTime(item.ts)}</div>
            </div>
          ))
        ) : (
          <div className="empty-state">Уведомлений пока нет.</div>
        )}
      </div>
    </Sheet>
  );
}
