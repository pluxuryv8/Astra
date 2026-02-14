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
    <div className="panel memory-panel">
      <div className="panel-header">
        <div>
          <div className="panel-title">Memory</div>
          <div className="panel-subtitle">Постоянные заметки пользователя</div>
        </div>
        <button className="btn ghost small" onClick={onClose} title="Закрыть">
          ✕
        </button>
      </div>

      {error ? <div className="banner error">{error}</div> : null}

      <div className="panel-section">
        <div className="section-title">Поиск</div>
        <div className="field-row">
          <input
            className="input"
            type="text"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Найти запись…"
          />
          <button className="btn ghost" onClick={onRefresh} disabled={loading}>
            {loading ? "..." : "Обновить"}
          </button>
        </div>
      </div>

      <div className="panel-section">
        <div className="section-title">Список</div>
        {loading ? <div className="empty">Загрузка…</div> : null}
        {!loading && items.length === 0 ? <div className="empty">Пока нет записей</div> : null}
        <div className="memory-list">
          {items.map((item) => (
            <div key={item.id} className={`memory-card ${item.pinned ? "pinned" : ""}`}>
              <div className="memory-head">
                <div className="memory-title">
                  {item.pinned ? "PIN · " : ""}
                  {item.title}
                </div>
                <div className="memory-actions">
                  <button className="btn ghost small" onClick={() => onTogglePin(item.id, Boolean(item.pinned))}>
                    {item.pinned ? "Unpin" : "Pin"}
                  </button>
                  <button className="btn danger small" onClick={() => onDelete(item.id)}>
                    Delete
                  </button>
                </div>
              </div>
              <div className="memory-content">
                {item.content.length > 240 ? `${item.content.slice(0, 240)}…` : item.content}
              </div>
              {item.tags && item.tags.length ? <div className="memory-tags">{item.tags.join(" · ")}</div> : null}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
