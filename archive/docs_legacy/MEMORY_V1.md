# MEMORY v1

## Разделение памяти
- **Run history**: события/шаги/артефакты конкретного запуска. Это техническая история (debug/trace) и не считается «памятью о пользователе».
  - Таблицы: `runs`, `plan_steps`, `tasks`, `events`, `sources`, `facts`, `artifacts`.
  - Поиск по истории: `memory_fts` (см. `memory/migrations/002_approvals_fts.sql:21-31`, `memory/store.py:843-899`).
- **Permanent Memory**: память о пользователе. Создаётся **только** по явной команде «запомни/сохрани/в память/зафиксируй» или через UI.
  - Таблица: `user_memories` (см. `memory/migrations/006_user_memories.sql:1-13`).

## Когда создаётся permanent memory
- Планировщик добавляет шаг `MEMORY_COMMIT` **только** при явном триггере (см. `core/planner.py:560-586`).
- Данные для записи берутся из текста пользователя и передаются в `memory_save` (см. `core/planner.py:85-115`, `core/planner.py:396-416`).
- `memory_save` создаёт запись в `user_memories` и пишет события (см. `skills/memory_save/skill.py:7-38`).

## Хранилище (SQLite)
Таблица `user_memories`:
- `id`, `created_at`, `updated_at`
- `title`, `content`
- `tags` (JSON)
- `source` (user_command | imported | system)
- `is_deleted`, `pinned`, `last_used_at`

Лимит контента: `ASTRA_MEMORY_MAX_CHARS` (по умолчанию 4000), проверяется при сохранении (см. `memory/store.py:41-56`, `memory/store.py:898-958`).

## API
- `GET /api/v1/memory/list?query=&tag=&limit=`
- `POST /api/v1/memory/create` `{title?, content, tags?, source?, from?}`
- `DELETE /api/v1/memory/{id}`
- `POST /api/v1/memory/{id}/pin`
- `POST /api/v1/memory/{id}/unpin`

См. `apps/api/routes/memory.py:1-86`.

## События
- `memory_save_requested {from, preview_len}`
- `memory_saved {memory_id, title, len, tags_count}`
- `memory_deleted {memory_id}`
- `memory_list_viewed {query, result_count}`

См. `schemas/events/*.schema.json`.

## Как удалить память
- Через UI панель “Память” (кнопка Delete).
- Через API `DELETE /api/v1/memory/{id}`.

## Где смотреть
- DB: `memory/migrations/006_user_memories.sql`.
- Store: `memory/store.py:898-1019`.
- Skill: `skills/memory_save/skill.py:1-38`.
- UI: `apps/desktop/src/ui/MemoryPanel.tsx:1-76`.
