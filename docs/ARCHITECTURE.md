# Architecture (Current State)

## 1) Компоненты

- Desktop UI: `apps/desktop` (`Tauri + React`).
- API: `apps/api` (`FastAPI`).
- Оркестрация и навыки: `core/` + `skills/`.
- Хранилище: `SQLite` через `memory/store.py` и `memory/db.py`.
- События и стриминг: event store + SSE (`apps/api/routes/run_events.py`).

## 2) Точка входа run

Основная точка входа: `POST /api/v1/projects/{project_id}/runs` в `apps/api/routes/runs.py`.

При создании run происходит:

1. Валидация проекта и режима.
2. Создание run в store (`created`).
3. Эмит `run_created`.
4. Определение intent через `IntentRouter` или fast-path.

## 3) Flow для CHAT

Ключевой путь качества ответа находится в `apps/api/routes/runs.py`.

1. Выбор intent:
- `fast_chat_path` для коротких безопасных сообщений.
- semantic decision через `IntentRouter.decide(...)`.
- при сбое semantic — деградация в `semantic_resilience`.

2. Сохранение meta run:
- intent-данные (`intent`, `intent_confidence`, `intent_path` и т.д.),
- tone/memory интерпретация,
- `runtime_metrics` (базовый объект метрик рантайма).

3. Эмит `intent_decided`:
- включает выбранный путь и `decision_latency_ms`.

4. Генерация chat-ответа:
- вызов LLM через `_call_chat_with_soft_retry(...)`,
- при ошибке/пустом ответе — fallback (`chat_llm_fallback`),
- при semantic resilience — degraded ответ.

5. Auto web research:
- решение принимает `_auto_web_research_decision(...)` (bool + reason),
- при срабатывании запускается `skills/web_research/skill.py`,
- собирается финальный текст и источники.

6. Финализация ответа:
- во всех финальных ветках эмитится `chat_response_generated`,
- в payload события добавляется `runtime_metrics`,
- те же `runtime_metrics` пишутся в `run.meta.runtime_metrics`.

## 4) Что пишется в runtime metrics

Текущее поле `runtime_metrics` содержит:

- `intent`
- `intent_path`
- `decision_latency_ms`
- `response_latency_ms`
- `auto_web_research_triggered`
- `auto_web_research_reason`
- `fallback_path`

Это используется для диагностики качества и скорости без изменения API-контрактов событий.

## 5) Flow для ACT и ASK_CLARIFY

- `ACT`: строится план через engine/planner, далее исполняются шаги навыков.
- `ASK_CLARIFY`: эмит `clarify_requested`, клиенту возвращаются уточняющие вопросы.

## 6) Event pipeline

- События пишутся в SQLite через `memory/store.py`.
- SSE endpoint: `GET /api/v1/runs/{run_id}/events` (`apps/api/routes/run_events.py`).
- Экспорт событий: `GET /api/v1/runs/{run_id}/events/download` (NDJSON).
- Полный снимок выполнения: `GET /api/v1/runs/{run_id}/snapshot`.

## 7) Ключевые модули качества ответа

- `apps/api/routes/runs.py`: intent routing, chat generation, fallback, auto web research, runtime metrics.
- `core/intent_router.py`: semantic intent decision.
- `core/brain/router.py`: маршрутизация и вызовы LLM/провайдера.
- `skills/web_research/skill.py`: поиск и сборка фактов из веба.
- `memory/store.py`: сохранение run meta/events для диагностики.
