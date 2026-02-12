# ARCHITECTURE_MAP (фактическая карта)

## Модульное дерево (только факт)
- Desktop UI (React): `apps/desktop/src/App.tsx` и `apps/desktop/src/api.ts` (см. `apps/desktop/src/App.tsx:1-229`, `apps/desktop/src/api.ts:1-200`).
- Desktop (Tauri/Rust): `apps/desktop/src-tauri/src/main.rs`, `apps/desktop/src-tauri/src/bridge.rs` (см. `apps/desktop/src-tauri/src/main.rs:1-70`, `apps/desktop/src-tauri/src/bridge.rs:1-275`).
- API (FastAPI): `apps/api/main.py` + роуты в `apps/api/routes/*` (см. `apps/api/main.py:1-39`, `apps/api/routes/*.py`).
- Core: `core/run_engine.py`, `core/planner.py`, `core/event_bus.py`, `core/skills/*`, `core/providers/*`, `core/secrets.py` (см. `core/*.py`).
- Bridge (Python-клиент к desktop-bridge): `core/bridge/desktop_bridge.py` (см. `core/bridge/desktop_bridge.py:1-35`).
- Storage/Memory (SQLite + миграции): `memory/db.py`, `memory/store.py`, `memory/migrations/*.sql`, `memory/vault.py` (см. `memory/*`).

## Потоки данных/событий
- UI → API: UI использует `fetch` к `API_BASE` и маршрутам `/api/v1/*` через `apps/desktop/src/api.ts` (см. `apps/desktop/src/api.ts:14-200`).
- UI ← API (SSE): UI открывает `EventSource` на `/api/v1/runs/{run_id}/events` и подписывается на `EVENT_TYPES` (см. `apps/desktop/src/App.tsx:44-70`, `apps/desktop/src/App.tsx:798-830`).
- UI ↔ API (snapshot/polling): UI запрашивает `/api/v1/runs/{run_id}/snapshot` и при ошибке SSE включает polling (см. `apps/desktop/src/api.ts:141-143`, `apps/desktop/src/App.tsx:777-825`).
- API → Core: API создаёт `RunEngine` и вызывает его методы в роуте runs (см. `apps/api/main.py:26-39`, `apps/api/routes/runs.py:76-182`).
- Core → DB: `RunEngine` читает/пишет run/plan/task/etc через `memory.store` (см. `core/run_engine.py:20-214`, `memory/store.py:72-890`).
- Core → SSE: события создаются через `core.event_bus.emit`, которые записываются в `events` в БД (см. `core/event_bus.py:41-67`, `memory/store.py:811-890`).
- Core → Bridge → Desktop: навыки `autopilot_computer`, `computer`, `shell` вызывают `DesktopBridge` и HTTP эндпоинты локального bridge (см. `skills/autopilot_computer/skill.py:82-311`, `skills/computer/skill.py:17-24`, `skills/shell/skill.py:17-23`, `core/bridge/desktop_bridge.py:7-35`).

## Desktop (UI + Tauri)
- UI хранит список событий/статусов/approvals и строит состояние HUD на основе SSE (`EVENT_TYPES`, `openEventStream`) (см. `apps/desktop/src/App.tsx:44-230`, `apps/desktop/src/App.tsx:798-855`).
- UI вызывает API функции из `apps/desktop/src/api.ts` (create/run/plan/approvals/etc) (см. `apps/desktop/src/api.ts:99-200`).
- Tauri запускает desktop-bridge HTTP сервер и регистрирует глобальные хоткеи (`Cmd+Shift+S`, `Cmd+Shift+O`, `Cmd+W`, `Cmd+Q`) (см. `apps/desktop/src-tauri/src/main.rs:33-63`).

## API (FastAPI) — маршруты и реализации
- `FastAPI` приложение создаётся в `apps/api/main.py` и подключает роуты (см. `apps/api/main.py:11-39`).
- Auth: `/api/v1/auth/status`, `/api/v1/auth/bootstrap` (см. `apps/api/routes/auth.py:9-18`).
- Projects: `POST/GET/PUT /api/v1/projects` и `GET /api/v1/projects/{project_id}` + `GET /api/v1/projects/{project_id}/memory/search` (см. `apps/api/routes/projects.py:10-49`).
- Runs: `POST /api/v1/projects/{project_id}/runs`, `POST /api/v1/runs/{run_id}/plan`, `POST /api/v1/runs/{run_id}/start`, `POST /api/v1/runs/{run_id}/cancel`, `POST /api/v1/runs/{run_id}/pause`, `POST /api/v1/runs/{run_id}/resume`, `POST /api/v1/runs/{run_id}/tasks/{task_id}/retry`, `POST /api/v1/runs/{run_id}/steps/{step_id}/retry`, `GET /api/v1/runs/{run_id}`, `GET /api/v1/runs/{run_id}/plan`, `GET /api/v1/runs/{run_id}/tasks`, `GET /api/v1/runs/{run_id}/sources`, `GET /api/v1/runs/{run_id}/facts`, `GET /api/v1/runs/{run_id}/conflicts`, `GET /api/v1/runs/{run_id}/artifacts`, `GET /api/v1/runs/{run_id}/snapshot`, `GET /api/v1/runs/{run_id}/snapshot/download`, `GET /api/v1/runs/{run_id}/approvals`, `POST /api/v1/approvals/{approval_id}/approve`, `POST /api/v1/approvals/{approval_id}/reject`, `POST /api/v1/runs/{run_id}/conflicts/{conflict_id}/resolve` (см. `apps/api/routes/runs.py:14-289`).
- Events (SSE/NDJSON): `GET /api/v1/runs/{run_id}/events`, `GET /api/v1/runs/{run_id}/events/download` (см. `apps/api/routes/run_events.py:12-53`).
- Skills registry: `GET /api/v1/skills`, `GET /api/v1/skills/{skill_name}/manifest`, `POST /api/v1/skills/reload` (см. `apps/api/routes/skills.py:7-33`).
- Artifacts: `GET /api/v1/artifacts/{artifact_id}/download` (см. `apps/api/routes/artifacts.py:12-22`).
- Secrets: `/api/v1/secrets/unlock`, `/api/v1/secrets/openai`, `/api/v1/secrets/openai_local`, `/api/v1/secrets/openai_local (GET)`, `/api/v1/secrets/status` (см. `apps/api/routes/secrets.py:9-46`).

## Core (Run/Plan/Events/Skills)
- План всегда формируется `create_default_plan()` из двух шагов: `autopilot_computer` и `memory_save` (см. `core/planner.py:9-27`).
- `RunEngine` создаёт план, запускает шаги, создает `Task`, пишет статусы и события, сохраняет результаты SkillResult (см. `core/run_engine.py:18-214`, `core/run_engine.py:215-307`).
- `SkillRunner` валидирует input schema, инициирует approval, ждёт approval в цикле, затем запускает `run/execute` навыка (см. `core/skills/runner.py:12-116`, `core/skills/runner.py:118-168`).
- Реестр навыков читает `skills/*/manifest.json` и импортирует `skills.<name>.skill` (см. `core/skills/registry.py:14-64`, `core/skills/registry.py:56-78`).
- Провайдеры LLM/поиска используют `requests.post` и читают секреты через `core.secrets` (см. `core/providers/llm_client.py:18-106`, `core/providers/search_client.py:19-71`, `core/secrets.py:1-86`).

## Bridge (desktop_bridge.py + Rust bridge)
- Python-клиент вызывает локальные endpoint'ы: `/computer/preview`, `/computer/execute`, `/shell/preview`, `/shell/execute`, `/autopilot/capture`, `/autopilot/act` на `127.0.0.1:${ASTRA_DESKTOP_BRIDGE_PORT}` (по умолчанию 43124) (см. `core/bridge/desktop_bridge.py:7-35`).
- Rust bridge поднимает HTTP сервер на `127.0.0.1:${ASTRA_DESKTOP_BRIDGE_PORT}` и обслуживает те же пути + `GET /autopilot/permissions` (см. `apps/desktop/src-tauri/src/bridge.rs:71-89`).
- Структуры данных для `/computer/*` — `ComputerActionDto`, `ComputerRequest`, `ComputerResponse` (см. `apps/desktop/src-tauri/src/bridge.rs:10-39`).
- Структуры данных для `/autopilot/*` — `AutopilotCaptureRequest/Response`, `AutopilotActRequest` (см. `apps/desktop/src-tauri/src/bridge.rs:41-66`).
- При отсутствии `desktop-skills` возвращается `503 НЕДОСТУПНО` для execute/capture/act/permissions (см. `apps/desktop/src-tauri/src/bridge.rs:118-157`, `apps/desktop/src-tauri/src/bridge.rs:203-275`).

## Storage/Memory
- SQLite база создаётся в `.astra/astra.db` (имя файла из `memory/db.py`) (см. `memory/db.py:7-18`).
- Миграции определяют таблицы `projects`, `runs`, `plan_steps`, `tasks`, `sources`, `facts`, `conflicts`, `artifacts`, `events` (см. `memory/migrations/001_init.sql:5-74`).
- Доп. таблицы: `approvals`, `session_tokens`, `memory_fts` (см. `memory/migrations/002_approvals_fts.sql:7-30`).
- Хранилище approval decision: `approvals.decision_json` (см. `memory/migrations/003_approvals_decision.sql:1-2`).
- Все read/write операции осуществляет `memory/store.py` (см. `memory/store.py:72-890`).
- Шифрованное хранилище секретов использует `pynacl` и Argon2id (см. `memory/vault.py:1-69`).

## Где искать что (ключевые файлы)
- Точки входа API: `apps/api/main.py` (см. `apps/api/main.py:1-39`).
- UI → API контракт: `apps/desktop/src/api.ts` (см. `apps/desktop/src/api.ts:14-200`).
- SSE события и типы: `apps/desktop/src/App.tsx` и `core/event_bus.py` (см. `apps/desktop/src/App.tsx:44-70`, `core/event_bus.py:8-55`).
- Планирование: `core/planner.py` (см. `core/planner.py:9-27`).
- Исполнение шагов/skills: `core/run_engine.py`, `core/skills/runner.py` (см. `core/run_engine.py:18-214`, `core/skills/runner.py:12-168`).
- Bridge endpoints: `apps/desktop/src-tauri/src/bridge.rs` и `core/bridge/desktop_bridge.py` (см. `apps/desktop/src-tauri/src/bridge.rs:71-275`, `core/bridge/desktop_bridge.py:7-35`).
