import type { UserMemory } from "../types";

type MemoryPanelProps = {
  items: UserMemory[];
  query: string;
  loading: boolean;
  error?: string | null;
  onQueryChange: (value: string) => void;
  onRefresh: () => void;
  onDelete: (id: string) => void;
  onTogglePin: (id: string, pinned: boolean) => void;
  onClose: () => void;
};

export default function MemoryPanel({
  items,
  query,
  loading,
  error,
  onQueryChange,
  onRefresh,
  onDelete,
  onTogglePin,
  onClose
}: MemoryPanelProps) {
  return (
    <div className="settings-panel memory-panel" onClick={(e) => e.stopPropagation()}>
      <div className="settings-header">
        <div>
          <div className="settings-title">Память</div>
          <div className="settings-subtitle">Постоянные записи пользователя</div>
        </div>
        <button className="icon-button" onClick={onClose} title="Закрыть">
          ✕
        </button>
      </div>

      {error ? <div className="settings-banner error">{error}</div> : null}

      <div className="settings-section">
        <div className="section-title">Поиск</div>
        <div className="memory-search">
          <input
            type="text"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Ищу..."
          />
          <button className="btn ghost" onClick={onRefresh} disabled={loading}>
            {loading ? "..." : "Обновить"}
          </button>
        </div>
      </div>

      <div className="settings-section">
        <div className="section-title">Список</div>
        {loading ? <div className="empty">Загрузка...</div> : null}
        {!loading && items.length === 0 ? <div className="empty">Пока нет записей</div> : null}
        <div className="memory-list">
          {items.map((item) => (
            <div key={item.id} className={`memory-card ${item.pinned ? "pinned" : ""}`}>
              <div className="memory-head">
                <div className="memory-title">
                  {item.pinned ? "📌 " : ""}
                  {item.title}
                </div>
                <div className="memory-actions">
                  <button className="btn ghost" onClick={() => onTogglePin(item.id, Boolean(item.pinned))}>
                    {item.pinned ? "Unpin" : "Pin"}
                  </button>
                  <button className="btn danger" onClick={() => onDelete(item.id)}>
                    Delete
                  </button>
                </div>
              </div>
              <div className="memory-content">
                {item.content.length > 240 ? `${item.content.slice(0, 240)}…` : item.content}
              </div>
              {item.tags && item.tags.length ? (
                <div className="memory-tags">{item.tags.join(" · ")}</div>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
