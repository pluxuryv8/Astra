import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MoreHorizontal, Plus, RefreshCw } from "lucide-react";
import { cn } from "../shared/utils/cn";
import { formatTime } from "../shared/utils/formatTime";
import type { AppPage, ConversationSummary } from "../shared/types/ui";
import { useAppStore } from "../shared/store/appStore";
import Button from "../shared/ui/Button";
import IconButton from "../shared/ui/IconButton";
import SearchInput from "../shared/ui/SearchInput";
import DropdownMenu from "../shared/ui/DropdownMenu";
import ProfileMenu from "./ProfileMenu";

export type SidebarProps = {
  width: number;
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
};

const listVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.04 } }
};

const itemVariants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0 }
};

export default function Sidebar({ width, activePage, onNavigate }: SidebarProps) {
  const conversations = useAppStore((state) => state.conversations);
  const conversationMessages = useAppStore((state) => state.conversationMessages);
  const selectedChatId = useAppStore((state) => state.lastSelectedChatId);
  const selectConversation = useAppStore((state) => state.selectConversation);
  const startNewConversation = useAppStore((state) => state.startNewConversation);
  const openRenameChat = useAppStore((state) => state.openRenameChat);
  const deleteConversation = useAppStore((state) => state.deleteConversation);
  const refreshRuns = useAppStore((state) => state.refreshRuns);
  const apiStatus = useAppStore((state) => state.apiStatus);

  const [search, setSearch] = useState("");

  const filteredChats = useMemo(() => {
    const value = search.trim().toLowerCase();
    if (!value) return conversations;
    return conversations.filter((chat) => {
      const titleMatch = chat.title.toLowerCase().includes(value);
      if (titleMatch) return true;
      const lastMessage = conversationMessages[chat.id]?.slice(-1)[0];
      return lastMessage?.text.toLowerCase().includes(value) ?? false;
    });
  }, [search, conversations, conversationMessages]);

  const handleSelectChat = async (chatId: string) => {
    await selectConversation(chatId);
    onNavigate("chat");
  };

  return (
    <aside className="sidebar" style={{ width }}>
      <div className="sidebar-header">
        <div className="sidebar-title">Randarc</div>
        <IconButton
          type="button"
          size="sm"
          variant="subtle"
          aria-label="Обновить список"
          onClick={() => void refreshRuns()}
          disabled={apiStatus !== "ready"}
        >
          <RefreshCw size={16} />
        </IconButton>
      </div>

      <div className="sidebar-content">
        <Button
          type="button"
          className="sidebar-new-chat"
          variant="primary"
          onClick={() => {
            startNewConversation();
            onNavigate("chat");
          }}
        >
          <Plus size={16} />
          Новый чат
        </Button>

        <SearchInput
          placeholder="Поиск"
          aria-label="Поиск"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />

        <div className="sidebar-section">
          <div className="sidebar-section-title">Разделы</div>
          <nav className="sidebar-nav">
            {[
              { id: "chat", label: "Чаты" },
              { id: "history", label: "История" },
              { id: "memory", label: "Память" },
              { id: "reminders", label: "Напоминания" },
              { id: "permissions", label: "Права доступа" },
              { id: "settings", label: "Настройки" }
            ].map((item) => (
              <button
                key={item.id}
                type="button"
                className={cn("sidebar-nav-item", { "is-active": activePage === item.id })}
                onClick={() => onNavigate(item.id as AppPage)}
              >
                <span>{item.label}</span>
                <span className="sidebar-nav-dot" />
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-section">
          <div className="sidebar-section-title">Чаты</div>
          <motion.div className="chat-list" variants={listVariants} initial="hidden" animate="show">
            <AnimatePresence mode="popLayout">
              {filteredChats.map((chat: ConversationSummary) => (
                <motion.div
                  layout
                  key={chat.id}
                  variants={itemVariants}
                  initial="hidden"
                  animate="show"
                  exit={{ opacity: 0, y: 6 }}
                  className={cn("chat-item", { "is-active": selectedChatId === chat.id })}
                >
                  <button type="button" className="chat-item-body" onClick={() => void handleSelectChat(chat.id)}>
                    <div className="chat-item-title">{chat.title}</div>
                    <div className="chat-item-meta">
                      <span>{formatTime(chat.updated_at)}</span>
                      <span className="chat-item-icons">
                        {chat.app_icons.map((tone, index) => (
                          <span key={`${chat.id}-app-${index}`} className="app-dot" data-tone={tone} />
                        ))}
                      </span>
                    </div>
                  </button>
                  <div className="chat-item-actions">
                    <DropdownMenu
                      align="right"
                      width={180}
                      items={[
                        {
                          id: "rename",
                          label: "Переименовать",
                          onSelect: () => openRenameChat(chat.id)
                        },
                        {
                          id: "delete",
                          label: "Удалить",
                          tone: "danger",
                          onSelect: () => deleteConversation(chat.id)
                        }
                      ]}
                      trigger={({ toggle }) => (
                        <IconButton
                          type="button"
                          size="sm"
                          aria-label="Действия"
                          onClick={toggle}
                        >
                          <MoreHorizontal size={16} />
                        </IconButton>
                      )}
                    />
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </motion.div>
        </div>
      </div>

      <div className="sidebar-footer">
        <ProfileMenu onNavigate={onNavigate} />
      </div>
    </aside>
  );
}
