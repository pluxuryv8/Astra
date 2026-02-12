# Executor Loop v1

## Назначение
Executor Loop v1 исполняет компьютерные шаги плана (UI-действия) в режиме «один атомарный шаг → наблюдение → проверка».

Поддерживаемые `PlanStep.kind`:
- `BROWSER_RESEARCH_UI`
- `COMPUTER_ACTIONS`
- `FILE_ORGANIZE`
- `CODE_ASSIST`

Источник: `core/executor/computer_executor.py`.

## Цикл выполнения
1. `observe` — делается снимок экрана (`/autopilot/capture`) и вычисляется хеш.
2. `micro-plan` — Brain предлагает **одно** атомарное действие (JSON).
3. `act` — выполняется одно действие (`/autopilot/act`).
4. `verify` — сравнение хеша до/после, при необходимости ожидание с polling.
5. Повтор до лимитов или пока модель не вернёт `action_type=done`.

## Лимиты и таймауты
Управляются через env или `settings.executor` проекта:
- `ASTRA_EXECUTOR_MAX_MICRO_STEPS` (default `30`)
- `ASTRA_EXECUTOR_MAX_NO_PROGRESS` (default `5`)
- `ASTRA_EXECUTOR_MAX_TOTAL_TIME_S` (default `600`)
- `ASTRA_EXECUTOR_WAIT_AFTER_ACT_MS` (default `350`)
- `ASTRA_EXECUTOR_WAIT_POLL_MS` (default `500`)
- `ASTRA_EXECUTOR_WAIT_TIMEOUT_MS` (default `4000`)
- `ASTRA_EXECUTOR_MAX_ACTION_RETRIES` (default `1`)
- `ASTRA_EXECUTOR_SCREENSHOT_WIDTH` (default `1280`)
- `ASTRA_EXECUTOR_SCREENSHOT_QUALITY` (default `60`)

## Dry-run
Для симуляции без реальных кликов:
- `ASTRA_EXECUTOR_DRY_RUN=true`

В этом режиме executor всё ещё делает `observe`, но не вызывает `/autopilot/act`.

## Approvals
Если `step.requires_approval` или `danger_flags` не пусты:
- создаётся approval (`scope=computer_step`),
- шаг ждёт подтверждения,
- при отказе — шаг завершается с ошибкой.

При невозможности продолжать (ошибка микропланирования/нет прогресса) создаётся approval `scope=executor_help`.

## События (audit)
Executor пишет события:
- `step_execution_started`
- `observation_captured`
- `micro_action_proposed`
- `micro_action_executed`
- `verification_result`
- `step_waiting`
- `step_retrying`
- `step_paused_for_approval`
- `step_execution_finished`

Схемы: `schemas/events/*.schema.json`.

## Где встроено
- Используется в `core/run_engine.py` для шагов `autopilot_computer` с `kind` из списка выше.
