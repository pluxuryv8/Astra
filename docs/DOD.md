# DOD (Definition of Done для следующих шагов)

## 1) Сборка жива
- Команда `./scripts/run.sh` должна поднимать API и Tauri dev без ошибок (см. `scripts/run.sh:58-134`).
- Альтернатива фоном: `./scripts/run.sh --background` (см. `scripts/run.sh:7-104`).

## 2) API жив
- `GET /api/v1/auth/status` возвращает 200 и JSON `{"initialized": ...}` (см. `apps/api/routes/auth.py:9-13`).
- `GET /api/v1/skills` возвращает список манифестов (см. `apps/api/routes/skills.py:7-18`).
- `GET /api/v1/projects` возвращает список проектов (см. `apps/api/routes/projects.py:10-28`).

## 3) UI жив
- UI загружается из Tauri/Vite и вызывает API базовый URL через `apps/desktop/src/api.ts` (см. `apps/desktop/src/api.ts:14-200`).
- В UI есть HUD, который строится на основе состояния событий/снапшота (см. `apps/desktop/src/App.tsx:167-230`, `apps/desktop/src/App.tsx:857-879`).

## 4) События живы (SSE)
- SSE endpoint: `GET /api/v1/runs/{run_id}/events` отдаёт `text/event-stream` и читает события из БД (см. `apps/api/routes/run_events.py:12-48`).
- UI открывает `EventSource` на этот endpoint и подписывается на типы из `EVENT_TYPES` (см. `apps/desktop/src/App.tsx:44-70`, `apps/desktop/src/App.tsx:798-830`).

## 5) Безопасность (approvals)
- Для навыков со `scopes` = `confirm_required` `SkillRunner` создаёт approval и ждёт решения (см. `core/skills/runner.py:31-116`).
- Навык `autopilot_computer` создаёт approval при `ask_confirm` или ключевых словах (см. `skills/autopilot_computer/skill.py:200-339`, `skills/autopilot_computer/skill.py:362-364`).
- API позволяет approve/reject через `/api/v1/approvals/{approval_id}` (см. `apps/api/routes/runs.py:250-274`).

## 6) Формат отчёта для будущих шагов
- Обязательный раздел: список изменённых файлов (только фактические изменения).
- Обязательный раздел: список выполненных команд (если выполнялись).
- Обязательный раздел: результат (успех/ошибка + ссылка на лог/файл).
