import { AnimatePresence, motion } from "framer-motion";
import { Copy, MoreHorizontal, ThumbsDown, ThumbsUp } from "lucide-react";
import { cn } from "../shared/utils/cn";
import type { Message } from "../shared/types/ui";
import DropdownMenu from "../shared/ui/DropdownMenu";
import IconButton from "../shared/ui/IconButton";
import { formatTime } from "../shared/utils/formatTime";
import type { RefObject } from "react";

export type ChatThreadProps = {
  messages: Message[];
  ratings: Record<string, "up" | "down">;
  onRequestMore: (messageId: string) => void;
  onThumbUp: (messageId: string) => void;
  onThumbDown: (messageId: string) => void;
  onCopy: (messageId: string) => void;
  onScroll?: () => void;
  scrollRef?: RefObject<HTMLDivElement | null>;
};

export default function ChatThread({
  messages,
  ratings,
  onRequestMore,
  onThumbUp,
  onThumbDown,
  onCopy,
  onScroll,
  scrollRef
}: ChatThreadProps) {
  return (
    <div className="chat-thread" onScroll={onScroll} ref={scrollRef}>
      <AnimatePresence mode="popLayout">
        {messages.map((message) => {
          const isUser = message.role === "user";
          const rating = ratings[message.id];
          return (
            <motion.div
              layout
              key={message.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.18 }}
              className={cn("chat-message", {
                "is-user": isUser,
                "is-assistant": !isUser
              })}
            >
              <div className="chat-bubble">{message.text}</div>
              <div className="chat-meta">
                <span>
                  {isUser ? "Вы" : "Astra"}
                  {message.ts ? ` · ${formatTime(message.ts)}` : ""}
                  {isUser ? " · доставлено" : ""}
                </span>
                {!isUser ? (
                  <div className="chat-message-actions">
                    <IconButton
                      type="button"
                      aria-label="Скопировать"
                      size="sm"
                      onClick={() => onCopy(message.id)}
                    >
                      <Copy size={16} />
                    </IconButton>
                    <div className="chat-rating">
                      <IconButton
                        type="button"
                        aria-label="Полезно"
                        size="sm"
                        active={rating === "up"}
                        onClick={() => onThumbUp(message.id)}
                      >
                        <ThumbsUp size={16} />
                      </IconButton>
                      <IconButton
                        type="button"
                        aria-label="Не полезно"
                        size="sm"
                        active={rating === "down"}
                        onClick={() => onThumbDown(message.id)}
                      >
                        <ThumbsDown size={16} />
                      </IconButton>
                    </div>
                    <DropdownMenu
                      align="right"
                      width={200}
                      items={[
                        {
                          id: "more",
                          label: "Попросить подробнее",
                          onSelect: () => onRequestMore(message.id)
                        }
                      ]}
                      trigger={({ toggle }) => (
                        <IconButton type="button" aria-label="Еще" size="sm" onClick={toggle}>
                          <MoreHorizontal size={16} />
                        </IconButton>
                      )}
                    />
                  </div>
                ) : null}
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
