# FIXLOG: Randarc Astra A/B/C

Дата: 2026-02-16

## 1) Что было сломано (подтверждено)

- `semantic`-ошибка ломала запуск вместо полезного ответа:
  - до фикса при ошибке semantic шёл `run_failed`/ошибка из `create_run` (`apps/api/routes/runs.py:303`, `apps/api/routes/runs.py:318`).
  - инвариант зафиксирован тестом деградации в chat (`tests/test_semantic_routing.py:267`).

- `web_research` мог завершаться без `sources`/`artifact`, хотя fetch/extract уже происходил:
  - причина: отсутствие строгой валидации LLM JSON + ветка invalid judge decision (`skills/web_research/skill.py:253`, `skills/web_research/skill.py:257`, `skills/web_research/skill.py:787`).
  - симптом в live events: только `task_progress` + `task_done` без `source_found/artifact_created` (воспроизведено на run `0ec8d6db-0cc8-4315-98ef-059cb1a6679e`).

- `web_research` без cloud должен продолжать работу локально и отдавать fallback:
  - deep-loop и локальные fallback ветки теперь явные (`skills/web_research/skill.py:769`, `skills/web_research/skill.py:804`, `skills/web_research/skill.py:895`).

- reminders без `run_id` теряли нормальный lifecycle в потоке UI:
  - добавлен стабильный event stream id `reminder:<id>` (`apps/api/routes/reminders.py:23`, `core/reminders/scheduler.py:54`, `apps/api/routes/run_events.py:19`).
  - scheduler стартует на app startup (`apps/api/main.py:46`).

- SSE в desktop показывал общий “подключаюсь…”, без точной причины:
  - добавлен preflight + дифференцированные ошибки `401/404/port unreachable` (`apps/desktop/src/shared/api/eventStream.ts:162`, `apps/desktop/src/shared/api/eventStream.ts:164`, `apps/desktop/src/shared/api/eventStream.ts:229`).

- startup gate:
  - `run.sh` теперь валится, если API не поднялся, и не продолжает desktop в этом состоянии (`scripts/run.sh:105`, `scripts/run.sh:120`).
  - `check.sh` добавляет API health gate + A/B/C инварианты (`scripts/check.sh:18`, `scripts/check.sh:26`).

## 2) Что изменено

- `apps/api/routes/runs.py`
  - введён controlled semantic resilience (`_semantic_resilience_decision`) и сохранение `semantic_error_code` (`apps/api/routes/runs.py:127`, `apps/api/routes/runs.py:317`, `apps/api/routes/runs.py:422`).

- `core/planner.py` + semantic contract
  - добавлен отдельный `WEB_RESEARCH -> web_research` route (`core/planner.py:25`, `core/planner.py:52`, `core/planner.py:1160`).
  - `plan_hint` расширен под `WEB_RESEARCH` (`core/semantic/decision.py:19`, `prompts/semantic_decision.md:15`, `prompts/semantic_decision.md:31`).

- `skills/web_research/skill.py`
  - добавлена schema-валидация LLM JSON (`skills/web_research/skill.py:259`).
  - invalid judge decision теперь не “теряет” результат: включается fallback с источниками/артефактом (`skills/web_research/skill.py:788`, `skills/web_research/skill.py:869`, `skills/web_research/skill.py:881`).

- reminders
  - event lifecycle для `run_id=None` через `reminder:<id>` (`apps/api/routes/reminders.py:23`, `core/reminders/scheduler.py:140`, `apps/api/routes/run_events.py:19`).
  - Telegram send contract + retries + status update (`core/reminders/scheduler.py:146`, `core/reminders/scheduler.py:160`, `core/reminders/scheduler.py:174`).

- desktop UX/diagnostics
  - точные SSE ошибки (`apps/desktop/src/shared/api/eventStream.ts:162`).
  - auto-dismiss notification TTL (`apps/desktop/src/shared/store/appStore.ts:72`, `apps/desktop/src/shared/store/appStore.ts:1473`).
  - dropdown/profile позиционирование (`apps/desktop/src/shared/ui/DropdownMenu.tsx:52`, `apps/desktop/src/shared/styles/globals.css:763`).

- tests
  - semantic resilience invariant (`tests/test_semantic_routing.py:267`).
  - planner web_research route (`tests/test_planner.py:106`).
  - reminders delivery/event lifecycle (`tests/test_reminders.py:109`, `tests/test_reminders.py:128`).
  - web research invalid judge fallback (`tests/test_web_research_deep.py:291`).

## 3) Как проверить

### Базовый прогон

```bash
pytest -q
```

Факт: `91 passed, 2 warnings`.

```bash
npm --prefix apps/desktop run test
npm --prefix apps/desktop run lint
```

Факт: desktop tests/lint проходят (`11/11 pass`, lint exit 0).

```bash
./scripts/doctor.sh prereq
```

Факт: `Doctor: OK` (есть WARN по env/local probe).

### Fail-fast startup gate

```bash
ASTRA_API_PORT=notnum ./scripts/run.sh --background; echo EXIT:$?
```

Факт: `API не поднялся...`, `EXIT:1`.

### SSE strict auth (почему UI может “подключаться…”)

```bash
ASTRA_AUTH_MODE=strict ASTRA_DATA_DIR=.astra_diag_strict3 .venv/bin/python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8061
curl -i 'http://127.0.0.1:8061/api/v1/runs/does-not-exist/events?once=1'
curl -i "http://127.0.0.1:8061/api/v1/runs/does-not-exist/events?once=1&token=$(cat .astra_diag_strict3/auth.token)"
```

Факт: без токена `401 missing_authorization`; с токеном `404 Запуск не найден`.

### Reminder lifecycle (без run_id)

```bash
POST /api/v1/reminders/create {delivery=telegram, run_id=null, due_at=past}
GET /api/v1/reminders
GET /api/v1/runs/reminder:<id>/events/download
```

Факт (live): `status=failed`, `last_error=telegram_not_configured`, события `reminder_created -> reminder_due -> reminder_failed`.

### Web research smoke (deterministic)

1. Создать run+plan с шагом `kind=WEB_RESEARCH`, `skill_name=web_research`.
2. `POST /api/v1/runs/{run_id}/start`.
3. Проверить snapshot/events.

Факт (live, run `e177d0e6-35c7-4cd5-a6cf-dfe7c21b99e5`):
- `final_status=done`
- `sources_count=2`
- `artifact_types=['web_research_answer_md']`
- events содержат `source_found`, `source_fetched`, `artifact_created`.

## 4) Риски / НЕИЗВЕСТНО

- НЕИЗВЕСТНО: end-to-end Telegram delivery в реальный чат (без моков) в этом окружении.
  - Нужны реальные `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`, затем повтор smoke с `delivery=telegram`.

- НЕИЗВЕСТНО: стабильность semantic latency под текущей локальной LLM при высоком load.
  - Нужен нагрузочный прогон `create_run` с профилированием `llm_request_started/succeeded/failed` по нескольким run.

- НЕИЗВЕСТНО: desktop Tauri запуск в этой сессии не валидировался визуально (проверка была через API/UI unit tests).
  - Нужен живой запуск `npm --prefix apps/desktop run tauri dev` и ручной smoke на overlay/event stream.
