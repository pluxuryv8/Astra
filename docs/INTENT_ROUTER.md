# Intent Router

## Что делает
- Определяет режим запроса пользователя: `CHAT`, `ACT`, `ASK_CLARIFY`.
- Если не уверен — возвращает 1–2 уточняющих вопроса и не запускает автопилот.
- Для `ACT` выставляет `danger_flags` и рекомендуемый режим запуска.

## Типы intent
- `CHAT` — ответ текстом без действий на компьютере.
- `ACT` — предполагаются действия на компьютере (UI/CLI/приложения).
- `ASK_CLARIFY` — требуется уточнение, чтобы выбрать режим.

## Правила (rules-first)
- Явные команды действий (открыть/нажать/перетащить/в браузере/в VSCode) → `ACT`.
- Вопросы/объяснения/текстовые запросы → `CHAT`.
- Короткие и неясные запросы (“сделай это”) → `ASK_CLARIFY`.

## LLM-классификация
- Используется только при низкой уверенности правил.
- Локальная модель по умолчанию через Brain.
- Возвращает JSON с полями `intent`, `confidence`, `questions`, `danger_flags`.

## Danger flags
- `send_message`, `delete_file`, `payment`, `publish`, `account_settings`, `password`.
- При наличии флагов рекомендуется режим `execute_confirm`.

## Где встроено
- Router: `core/intent_router.py`.
- API entrypoint: `apps/api/routes/runs.py` (POST `/api/v1/projects/{project_id}/runs`).
- UI: `apps/desktop/src/App.tsx` (обработка ответа `kind: act|chat|clarify`).

## События
- `intent_decided` — решение IntentRouter.
- `clarify_requested` — вопросы при `ASK_CLARIFY`.
- `chat_response_generated` — ответ при `CHAT`.

## Ответ API
`POST /api/v1/projects/{project_id}/runs` возвращает:
- `kind: "act"` + `run` (созданный запуск)
- `kind: "chat"` + `chat_response`
- `kind: "clarify"` + `questions`

Формат решения: см. `core/intent_router.py`.
