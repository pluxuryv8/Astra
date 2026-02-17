import { MoreHorizontal, FileDown, Trash2, Pencil, Bell } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import Badge from "../shared/ui/Badge";
import DropdownMenu from "../shared/ui/DropdownMenu";
import IconButton from "../shared/ui/IconButton";

export type TopBarProps = {
  status: string;
  onClear: () => void;
  onRename: () => void;
  onExport: () => void;
  notificationsCount?: number;
  onToggleNotifications?: () => void;
};

export default function TopBar({
  status,
  onClear,
  onRename,
  onExport,
  notificationsCount = 0,
  onToggleNotifications
}: TopBarProps) {
  return (
    <div className="top-bar">
      <div className="top-bar-status">
        <span>Статус</span>
        <AnimatePresence mode="wait">
          <motion.div
            key={status}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16 }}
          >
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <Badge tone="accent">{status}</Badge>
              <Badge tone="success">Agents: 9/9 active</Badge>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="top-bar-actions">
        <IconButton type="button" aria-label="Уведомления" onClick={onToggleNotifications}>
          <Bell size={18} />
          {notificationsCount > 0 ? <span className="notification-dot" /> : null}
        </IconButton>
        <DropdownMenu
          items={[
            { id: "clear", label: "Очистить чат", icon: <Trash2 size={16} />, onSelect: onClear },
            { id: "rename", label: "Переименовать чат", icon: <Pencil size={16} />, onSelect: onRename },
            { id: "export", label: "Экспорт", icon: <FileDown size={16} />, onSelect: onExport }
          ]}
          trigger={({ toggle }) => (
            <IconButton type="button" aria-label="Меню чата" onClick={toggle}>
              <MoreHorizontal size={18} />
            </IconButton>
          )}
        />
      </div>
    </div>
  );
}
