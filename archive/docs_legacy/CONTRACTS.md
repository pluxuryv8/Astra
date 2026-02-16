# CONTRACTS (заморозка контрактов)

## Источник правды
- DB‑схема: `memory/migrations/*.sql` (см. `memory/migrations/001_init.sql:10-112`, `memory/migrations/002_approvals_fts.sql:1-39`, `memory/migrations/003_approvals_decision.sql:1-2`).
- API выдача: `apps/api/routes/runs.py` (snapshot + approvals), `apps/api/routes/run_events.py` (SSE/NDJSON) (см. `apps/api/routes/runs.py:24-286`, `apps/api/routes/run_events.py:15-61`).
- UI ожидания: TS типы `apps/desktop/src/types.ts` и подписка SSE в `apps/desktop/src/App.tsx` (см. `apps/desktop/src/types.ts:77-151`, `apps/desktop/src/App.tsx:44-70`).
- Формальные схемы: `schemas/*.schema.json` (см. `schemas/event.schema.json:1-90`, `schemas/snapshot.schema.json:1-57`, `schemas/approval.schema.json:1-22`).

## DB: таблицы и ключевые поля
- `runs`: `id`, `project_id`, `query_text`, `mode`, `status`, `created_at`, `started_at`, `finished_at` (см. `memory/migrations/001_init.sql:19-28`).
- `plan_steps`: `id`, `run_id`, `step_index`, `title`, `skill_name`, `inputs`, `depends_on`, `status` (см. `memory/migrations/001_init.sql:31-40`).
- `tasks`: `id`, `run_id`, `plan_step_id`, `attempt`, `status`, `started_at`, `finished_at`, `error`, `duration_ms` (см. `memory/migrations/001_init.sql:43-52`).
- `events`: `id`, `run_id`, `ts`, `type`, `level`, `message`, `payload`, `task_id`, `step_id` (см. `memory/migrations/001_init.sql:101-111`).
- `approvals`: `id`, `run_id`, `task_id`, `created_at`, `scope`, `title`, `description`, `proposed_actions`, `status`, `decided_at`, `decided_by`, `decision_json` (см. `memory/migrations/002_approvals_fts.sql:6-18`, `memory/migrations/003_approvals_decision.sql:1-2`).
- `sources`, `facts`, `conflicts`, `artifacts` (см. `memory/migrations/001_init.sql:57-98`).

## Event Protocol
- Формат события в API: `id`, `seq` (rowid), `run_id`, `ts`, `type`, `level`, `message`, `payload`, `task_id`, `step_id` (см. `memory/store.py:832-874`, `schemas/event.schema.json:6-78`).
- SSE выдаёт `event: <type>` и `data: <event json>` (см. `apps/api/routes/run_events.py:35-41`).
- Разрешённые типы событий загружаются из `schemas/events/*.schema.json` либо fallback‑списка (см. `core/event_bus.py:39-52`).
- Список типов фиксируется в `schemas/event.schema.json` (см. `schemas/event.schema.json:19-48`) и синхронизируется тестом `tests/test_event_types_sync.py` (см. `tests/test_event_types_sync.py:8-18`).

## Snapshot Contract
- Snapshot формируется в `_build_snapshot` и включает: `run`, `plan`, `tasks`, `sources`, `facts`, `conflicts`, `artifacts`, `approvals`, `metrics`, `last_events` (см. `apps/api/routes/runs.py:24-73`).
- Формальная схема snapshot: `schemas/snapshot.schema.json` (см. `schemas/snapshot.schema.json:1-57`).
- UI читает поля `run`, `plan`, `tasks`, `metrics`, `approvals`, `last_events` (см. `apps/desktop/src/App.tsx:699-705`, `apps/desktop/src/types.ts:140-151`).

## Approval Contract
- Статусы approvals: `pending`, `approved`, `rejected`, `expired` (см. `schemas/approval.schema.json:15-21`).
- Запрос подтверждения формируется в `core/skills/runner.py` и в `skills/autopilot_computer/skill.py` (см. `core/skills/runner.py:34-71`, `skills/autopilot_computer/skill.py:312-329`).
- API обновляет статус через `/approvals/{id}/approve|reject` (см. `apps/api/routes/runs.py:258-286`).
- События approvals:
  - `approval_requested` эмитится при создании approval (см. `core/skills/runner.py:58-71`, `skills/autopilot_computer/skill.py:323-329`).
  - `approval_resolved` эмитится при завершении ожидания approval (см. `core/skills/runner.py:88-100`, `skills/autopilot_computer/skill.py:339-345`).
  - `approval_approved` / `approval_rejected` остаются как есть (см. `core/skills/runner.py:101-119`, `skills/autopilot_computer/skill.py:346-351`, `apps/api/routes/runs.py:258-286`).

## UI ожидания (TS)
- `EventItem` включает `seq`, `id`, `run_id`, `ts`, `type`, `message`, `payload`, `level`, `task_id`, `step_id` (см. `apps/desktop/src/types.ts:77-88`).
- `Snapshot` включает `run`, `plan`, `approvals`, `last_events` и опционально `tasks`, `sources`, `facts`, `conflicts`, `artifacts`, `metrics` (см. `apps/desktop/src/types.ts:140-151`).
- SSE подписка фиксирована массивом `EVENT_TYPES` (см. `apps/desktop/src/App.tsx:44-70`).
