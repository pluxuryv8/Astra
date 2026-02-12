CREATE TABLE IF NOT EXISTS user_memories (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  tags TEXT,
  source TEXT NOT NULL,
  is_deleted INTEGER NOT NULL DEFAULT 0,
  pinned INTEGER NOT NULL DEFAULT 0,
  last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS user_memories_created_idx ON user_memories(created_at);
CREATE INDEX IF NOT EXISTS user_memories_pinned_idx ON user_memories(pinned);
CREATE INDEX IF NOT EXISTS user_memories_deleted_idx ON user_memories(is_deleted);
