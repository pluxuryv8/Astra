import { useEffect, useState } from "react";
import { useAppStore } from "../shared/store/appStore";
import Button from "../shared/ui/Button";
import Input from "../shared/ui/Input";
import Modal from "../shared/ui/Modal";

export default function RenameChatModal() {
  const renameChatId = useAppStore((state) => state.renameChatId);
  const chats = useAppStore((state) => state.conversations);
  const renameChat = useAppStore((state) => state.renameConversation);
  const closeRenameChat = useAppStore((state) => state.closeRenameChat);
  const [value, setValue] = useState("");

  useEffect(() => {
    if (!renameChatId) return;
    const chat = chats.find((item) => item.id === renameChatId);
    setValue(chat?.title ?? "");
  }, [renameChatId, chats]);

  const handleSubmit = () => {
    if (!renameChatId) return;
    renameChat(renameChatId, value);
    closeRenameChat();
  };

  return (
    <Modal open={Boolean(renameChatId)} title="Переименовать чат" onClose={closeRenameChat}>
      <div className="feedback-form">
        <Input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="Введите название"
          autoFocus
        />
        <div className="ui-modal-actions">
          <Button type="button" variant="ghost" onClick={closeRenameChat}>
            Отмена
          </Button>
          <Button type="button" variant="primary" onClick={handleSubmit}>
            Сохранить
          </Button>
        </div>
      </div>
    </Modal>
  );
}
