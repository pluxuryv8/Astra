# Контекст чата (история диалога)

## Ключ диалога
- Диалог определяется цепочкой запусков, связанной через `parent_run_id`.
- UI группирует сообщения в диалоги по `parent_run_id` при загрузке запусков (`apps/desktop/src/shared/store/appStore.ts:982-1044`).
- При отправке нового сообщения UI теперь отправляет `parent_run_id` как последний `run_id` в текущем диалоге (`apps/desktop/src/shared/store/appStore.ts:1186-1210`).

## Где хранится история
- Пользовательское сообщение хранится в `runs.query_text` и событии `run_created` (payload содержит `query_text`) (`memory/store.py:200-229`, `apps/api/routes/runs.py:190-196`).
- Ответ ассистента сохраняется в событии `chat_response_generated` с полем `text` (`apps/api/routes/runs.py:236-245`, `schemas/events/chat_response_generated.schema.json:1-13`).

## Как извлекается история
- Сервер использует цепочку `parent_run_id` и извлекает последние N чатов через `store.list_recent_chat_turns` (`memory/store.py:285-360`).
- История возвращается в порядке от старых к новым: `user → assistant` для каждого шага.

## Подмешивание истории в LLM запрос
- История подмешивается только для интента `CHAT` в `create_run` (`apps/api/routes/runs.py:190-247`).
- Последовательность: `system` → `history` → текущий `user` (`core/chat_context.py:4-12`, `apps/api/routes/runs.py:217-230`).

## Лимит истории
- Лимит по количеству “ходов” (turns) задан константой `CHAT_HISTORY_TURNS = 20` (`apps/api/routes/runs.py:29-30`).

## Как проверить вручную
1. Создай новый чат и отправь 2-3 сообщения подряд.
2. Проверь, что UI отправляет `parent_run_id` (смотри request body в DevTools).
3. В БД появится событие `chat_response_generated` с полем `text` (таблица `events`).
