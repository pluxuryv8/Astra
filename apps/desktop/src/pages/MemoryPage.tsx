import { useEffect, useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import { useAppStore } from "../shared/store/appStore";
import SearchInput from "../shared/ui/SearchInput";
import IconButton from "../shared/ui/IconButton";
import Badge from "../shared/ui/Badge";
import Button from "../shared/ui/Button";
import Modal from "../shared/ui/Modal";
import { formatTime } from "../shared/utils/formatTime";

export default function MemoryPage() {
  const memoryItems = useAppStore((state) => state.memoryItems);
  const memoryLoading = useAppStore((state) => state.memoryLoading);
  const memoryError = useAppStore((state) => state.memoryError);
  const loadMemory = useAppStore((state) => state.loadMemory);
  const deleteMemory = useAppStore((state) => state.deleteMemory);
  const [search, setSearch] = useState("");
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ id: string; title: string } | null>(null);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void loadMemory(search.trim());
    }, 250);
    return () => window.clearTimeout(handle);
  }, [loadMemory, search]);

  const filtered = useMemo(() => {
    const value = search.trim().toLowerCase();
    const base = memoryItems.filter((item) => {
      if (selectedTag && !(item.tags || []).includes(selectedTag)) return false;
      if (!value) return true;
      return [item.title, item.content, (item.tags || []).join(" ")].join(" ").toLowerCase().includes(value);
    });
    return base;
  }, [search, memoryItems, selectedTag]);

  const tags = useMemo(() => {
    const unique = new Set<string>();
    memoryItems.forEach((item) => {
      (item.tags || []).forEach((tag) => unique.add(tag));
    });
    return Array.from(unique);
  }, [memoryItems]);

  return (
    <section className="page-stub memory-page">
      <div className="page-header">
        <div>
          <div className="page-title">Память</div>
          <div className="page-subtitle">Сохранённые факты о пользователе и контексте.</div>
        </div>
        <SearchInput placeholder="Поиск по памяти" value={search} onChange={(event) => setSearch(event.target.value)} />
      </div>

      {tags.length ? (
        <div className="memory-tags">
          <Badge
            tone={selectedTag ? "muted" : "accent"}
            size="sm"
            onClick={() => setSelectedTag(null)}
          >
            Все теги
          </Badge>
          {tags.map((tag) => (
            <Badge
              key={tag}
              tone={selectedTag === tag ? "accent" : "muted"}
              size="sm"
              onClick={() => setSelectedTag(tag)}
            >
              {tag}
            </Badge>
          ))}
        </div>
      ) : null}

      <div className="memory-list">
        {memoryError ? (
          <div className="inline-error">
            {memoryError}
            <Button type="button" variant="ghost" onClick={() => void loadMemory(search.trim())}>
              Повторить
            </Button>
          </div>
        ) : null}
        {memoryLoading ? <div className="inline-loading">Загрузка памяти…</div> : null}
        {filtered.map((item) => (
          <div key={item.id} className="memory-card">
            <div className="memory-card-header">
              <div>
                <div className="memory-title">{item.title}</div>
                <div className="memory-meta">
                  Обновлено · {formatTime(item.updated_at || item.created_at || "")}
                </div>
              </div>
              <IconButton
                type="button"
                size="sm"
                aria-label="Удалить"
                onClick={() => setPendingDelete({ id: item.id, title: item.title })}
              >
                <Trash2 size={16} />
              </IconButton>
            </div>
            <div className="memory-detail">{item.content}</div>
            {(item.tags || []).length ? (
              <div className="memory-tags">
                {(item.tags || []).map((tag) => (
                  <Badge key={tag} tone="muted" size="sm">
                    {tag}
                  </Badge>
                ))}
              </div>
            ) : null}
          </div>
        ))}
        {!filtered.length && !memoryLoading ? (
          <div className="empty-state">Память пуста. Скажи в чате: «запомни …»</div>
        ) : null}
      </div>

      <Modal open={Boolean(pendingDelete)} title="Удалить запись памяти?" onClose={() => setPendingDelete(null)}>
        <div className="ui-modal-body">
          {pendingDelete?.title ? `«${pendingDelete.title}»` : "Вы уверены, что хотите удалить запись?"}
        </div>
        <div className="ui-modal-actions">
          <Button type="button" variant="ghost" onClick={() => setPendingDelete(null)}>
            Отмена
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={() => {
              if (!pendingDelete) return;
              void deleteMemory(pendingDelete.id).then(() => setPendingDelete(null));
            }}
          >
            Удалить
          </Button>
        </div>
      </Modal>
    </section>
  );
}
