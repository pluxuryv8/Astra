# ASTRA Brain/Skills Audit

Дата аудита: 2026-02-15  
Репозиторий: `randarc-astra`  
Аудируемый контур: `core/*`, `skills/*`, `apps/api/*`, `apps/desktop/*`, `memory/*`, `schemas/*`, `prompts/*`, `scripts/*`

Ограничение метода: все выводы ниже подтверждены только `file:line` или выводом команд. Если подтверждения нет, помечено как `НЕИЗВЕСТНО`.

## Шаг 1: Инвентаризация

### 1.1 Карта директорий
Команда:
```bash
find core skills apps/api apps/desktop memory schemas prompts scripts -maxdepth 2 -type d | rg -v 'node_modules|dist|target|__pycache__' | sort
```
Ключевой вывод:
```text
apps/api
apps/api/routes
apps/desktop
apps/desktop/src
apps/desktop/src-tauri
apps/desktop/src-tauri/src
core
core/brain
core/bridge
core/executor
core/memory
core/ocr
core/providers
core/reminders
core/safety
core/semantic
core/skills
memory
memory/migrations
prompts
schemas
schemas/autopilot
schemas/events
schemas/skills
scripts
skills
skills/autopilot_computer
skills/computer
skills/conflict_scan
skills/extract_facts
skills/memory_save
skills/registry
skills/reminder_create
skills/report
skills/shell
skills/smoke_run
skills/web_research
```

### 1.2 Список skills/* и entrypoint
Команды:
```bash
ls -1 skills
find skills -maxdepth 2 -type f -name "skill.py" -print | sort
rg -n "class .*Skill|skill\s*=|def run\(|def execute\(" -S skills core
```

Вывод `ls -1 skills`:
```text
__init__.py
__pycache__
autopilot_computer
computer
conflict_scan
extract_facts
memory_save
registry
reminder_create
report
shell
smoke_run
web_research
```

Entry points:
- `skills/autopilot_computer/skill.py`.
- `skills/computer/skill.py`.
- `skills/conflict_scan/skill.py`.
- `skills/extract_facts/skill.py`.
- `skills/memory_save/skill.py`.
- `skills/reminder_create/skill.py`.
- `skills/report/skill.py`.
- `skills/shell/skill.py`.
- `skills/smoke_run/skill.py`.
- `skills/web_research/skill.py`.

#### Skills inventory (entrypoint + кратко что делает)
- `autopilot_computer`: цикл screenshot -> LLM action -> execute, с approval и артефактами (`skills/autopilot_computer/skill.py:93`, `skills/autopilot_computer/skill.py:135`, `skills/autopilot_computer/skill.py:302`, `skills/autopilot_computer/skill.py:378`, `skills/autopilot_computer/skill.py:453`).
- `computer`: выполняет список low-level действий через desktop bridge (`skills/computer/skill.py:17`, `skills/computer/skill.py:19`, `skills/computer/skill.py:20`).
- `conflict_scan`: группирует факты и поднимает конфликты (`skills/conflict_scan/skill.py:29`, `skills/conflict_scan/skill.py:45`).
- `extract_facts`: извлекает факты через LLM для последующей валидации/репорта (`skills/extract_facts/skill.py:67`, `skills/extract_facts/skill.py:127`).
- `memory_save`: нормализует/дедуплицирует и сохраняет user memory, эмитит события памяти (`skills/memory_save/skill.py:138`, `skills/memory_save/skill.py:149`, `skills/memory_save/skill.py:173`, `skills/memory_save/skill.py:210`).
- `reminder_create`: парсит reminder (если нет готовых полей), пишет в store, эмитит `reminder_created` (`skills/reminder_create/skill.py:19`, `skills/reminder_create/skill.py:26`, `skills/reminder_create/skill.py:33`, `skills/reminder_create/skill.py:41`).
- `report`: собирает источники/факты/конфликты и пишет markdown-артефакт (`skills/report/skill.py:9`, `skills/report/skill.py:54`, `skills/report/skill.py:60`).
- `shell`: исполняет shell-команду через bridge (`skills/shell/skill.py:17`, `skills/shell/skill.py:19`, `skills/shell/skill.py:20`).
- `smoke_run`: быстрый smoke-сценарий capture/scroll/act, возвращает факт-проверку (`skills/smoke_run/skill.py:24`, `skills/smoke_run/skill.py:34`, `skills/smoke_run/skill.py:56`, `skills/smoke_run/skill.py:71`).
- `web_research`: режим candidates/deep, поиск+fetch+extract+judge+answer artifact (`skills/web_research/skill.py:447`, `skills/web_research/skill.py:481`, `skills/web_research/skill.py:562`, `skills/web_research/skill.py:600`, `skills/web_research/skill.py:630`).

Дополнительно по загрузке skills:
- Реестр грузит `manifest.json` из `skills/*` и пишет `skills/registry/registry.json` (`core/skills/registry.py:29`, `core/skills/registry.py:31`, `core/skills/registry.py:50`, `core/skills/registry.py:54`).
- Точка входа: объект `skill` или `run` в модуле (`core/skills/registry.py:62`, `core/skills/registry.py:65`, `core/skills/registry.py:67`).

## Шаг 2: Главные цепочки (main flows)

### A) Chat flow: user -> api -> intent/semantic -> planner/chat_response/report -> events -> UI
- API принимает запрос и создаёт run: `apps/api/routes/runs.py:253`.
- Intent routing через semantic decision: `apps/api/routes/runs.py:283`, `core/intent_router.py:86`, `core/intent_router.py:108`, `core/semantic/decision.py:205`.
- Для `CHAT` формируется `LLMRequest` и вызывается brain: `apps/api/routes/runs.py:436`, `apps/api/routes/runs.py:442`, `apps/api/routes/runs.py:449`.
- Результат чата публикуется событием: `apps/api/routes/runs.py:454`, `apps/api/routes/runs.py:456`.
- SSE-выдача событий: `apps/api/routes/run_events.py:15`, `apps/api/routes/run_events.py:30`, `apps/api/routes/run_events.py:46`.
- UI подписывается на поток и обновляет store/activity: `apps/desktop/src/shared/store/appStore.ts:1209`, `apps/desktop/src/shared/store/appStore.ts:1214`, `apps/desktop/src/shared/store/appStore.ts:1205`.

### B) Memory flow: user -> semantic memory_item -> memory_save -> DB -> profile injection -> ответ/просмотр
- Semantic может вернуть `memory_item`: `core/semantic/decision.py:82`, `core/semantic/decision.py:124`, `core/intent_router.py:128`.
- Параллельно API гоняет memory interpreter для `summary/facts/preferences`: `apps/api/routes/runs.py:323`, `core/memory/interpreter.py:199`.
- Memory payload строится и сохраняется skill-ом: `apps/api/routes/runs.py:369`, `apps/api/routes/runs.py:420`, `skills/memory_save/skill.py:138`, `skills/memory_save/skill.py:173`.
- Persistence в SQLite (`user_memories`): `memory/store.py:1197`, `memory/store.py:1225`, `memory/store.py:1258`.
- Профиль внедряется в chat prompt через context builder: `apps/api/routes/runs.py:317`, `core/chat_context.py:120`, `apps/api/routes/runs.py:440`.

### C) Act/autopilot flow: user -> planner COMPUTER_ACTIONS/AUTOPILOT -> bridge capture/act -> events -> UI
- ACT-ветка создаёт/возвращает план: `apps/api/routes/runs.py:426`, `apps/api/routes/runs.py:429`.
- План строится из `plan_hint` и `KIND_TO_SKILL`: `core/planner.py:42`, `core/planner.py:1072`, `core/planner.py:1158`.
- RunEngine исполняет шаги, для computer-step уходит в `ComputerExecutor`: `core/run_engine.py:219`, `core/run_engine.py:311`.
- Executor делает capture/act через bridge и эмитит микрособытия: `core/executor/computer_executor.py:376`, `core/executor/computer_executor.py:601`, `core/executor/computer_executor.py:395`.
- Python bridge client -> Tauri bridge HTTP endpoints: `core/bridge/desktop_bridge.py:26`, `core/bridge/desktop_bridge.py:29`, `apps/desktop/src-tauri/src/bridge.rs:93`, `apps/desktop/src-tauri/src/bridge.rs:94`, `apps/desktop/src-tauri/src/bridge.rs:95`.
- UI принимает события и обновляет overlay/status: `apps/desktop/src/shared/store/appStore.ts:1209`, `apps/desktop/src/app/AppShell.tsx:175`, `apps/desktop/src/app/AppShell.tsx:238`, `apps/desktop/src/app/OverlayApp.tsx:198`.

## Шаг 3: Проверки и запуск команд

### 3.1 `python3 -m pytest -q`
```text
83 passed, 2 skipped, 2 warnings in 3.01s
warnings:
- tests/test_contracts.py:13 DeprecationWarning: jsonschema.RefResolver is deprecated
```

### 3.2 `npm --prefix apps/desktop run test`
```text
# tests 11
# pass 11
# fail 0
```

### 3.3 `npm --prefix apps/desktop run lint`
```text
> eslint "src/**/*.{ts,tsx}"
(exit 0)
```

### 3.4 `./scripts/doctor.sh prereq`
```text
FAIL Ollama not reachable at http://127.0.0.1:11434 (GET /api/tags)
Doctor: FAIL (1)
```
Дополнительно: много `WARN env ... is not set`, при этом `OK OCR engine tesseract`, `OK OCR python deps`, `OK Cloud disabled`, `OK Reminders enabled`.

## Шаг 4: Поиск “сырости/хаков/ограничителей”

Команда:
```bash
rg -n "TODO|FIXME|HACK|TEMP|stub|NEED|legacy|fallback|re\.compile\(|TRIGGERS|any\(phrase in|in normalized" -S core skills apps/api memory prompts
```

Ключевые находки:
- Legacy-триггеры и ветка `ASTRA_LEGACY_DETECTORS`: `core/planner.py:64`, `core/planner.py:73`, `core/planner.py:90`, `core/planner.py:1184`.
- Явный fallback в brain routing: `core/brain/router.py:229` (`sanitized_empty_fallback`).
- Stub-провайдеры в web research: `skills/web_research/manifest.json:8`, `skills/registry/registry.json:65`, `core/providers/search_client.py:108`.
- Regex redaction/token детекторы: `core/llm_routing.py:93`, `core/llm_routing.py:94`, `core/llm_routing.py:95`.
- Эвристические `any(token in text)`/phrase triggers: `core/planner.py:186`, `core/planner.py:937`, `core/assistant_phrases.py:25`.
- Deep mode явный стоп на stub provider: `skills/web_research/skill.py:500`, `skills/web_research/skill.py:501`.
- Name fallback по regex в контексте профиля: `core/chat_context.py:47`, `core/chat_context.py:49`.

## Шаг 5: Оценка по аспектам

### 1) Intent routing (`core/intent_router.py`) + семантика (`core/semantic/*`, `prompts/semantic*`)
Оценки: Готовность `8/10`, Надёжность `7/10`, Качество UX `7/10`, Наблюдаемость `6/10`, Тестируемость `8/10`.

Обоснование:
- Жёсткая схема semantic-ответа (intent/confidence/memory_item/plan_hint) и валидация входа/выхода (`core/semantic/decision.py:76`, `core/semantic/decision.py:104`, `core/semantic/decision.py:181`).
- Проверка `memory_item.evidence` как подстроки пользовательского текста снижает галлюцинации (`core/semantic/decision.py:145`, `core/semantic/decision.py:147`).
- IntentRouter явно формирует `ACT/CHAT/ASK` и `act_hint` (target/danger/suggested_mode) (`core/intent_router.py:121`, `core/intent_router.py:124`, `core/intent_router.py:126`).
- Semantic и memory interpreter принудительно в strict-local privacy (`core/semantic/decision.py:219`, `core/semantic/decision.py:221`; `core/memory/interpreter.py:231`, `core/memory/interpreter.py:233`).
- Промпт ограничивает формат и перечисляет допустимые `plan_hint` (`prompts/semantic_decision.md:5`, `prompts/semantic_decision.md:15`, `prompts/semantic_decision.md:28`).
- Тесты покрывают memory-array rejection, parsing, маршрутизацию ACT/CHAT/ASK (`tests/test_semantic_routing.py:114`, `tests/test_semantic_routing.py:122`, `tests/test_intent_router.py:30`, `tests/test_intent_router.py:69`).

Критические проблемы (P0):
- Semantic failure ведёт к `run_failed` и HTTP 502 без fallback-маршрута: `apps/api/routes/runs.py:284`, `apps/api/routes/runs.py:298`, `apps/api/routes/runs.py:299`.

Быстрые улучшения (P1):
- Добавить controlled fallback-путь (например, `ASK_CLARIFY`) при `semantic_decision_llm_failed` вместо hard-fail.
- Добавить event на уровне `IntentRouter` с деталями decision-path (сейчас эмит в API-роуте, не в роутере).

### 2) Планирование (`core/planner.py`) + mapping kind->skill
Оценки: Готовность `7/10`, Надёжность `6/10`, Качество UX `6/10`, Наблюдаемость `5/10`, Тестируемость `8/10`.

Обоснование:
- Явный mapping `KIND_TO_SKILL` и список kinds (`core/planner.py:29`, `core/planner.py:42`).
- Main-path использует `plan_hint` из meta и отключает legacy по умолчанию (`core/planner.py:1182`, `core/planner.py:1184`, `core/planner.py:1190`; `tests/test_planner.py:141`).
- Есть sanitization входов шага (autopilot/memory/report) (`core/planner.py:734`, `core/planner.py:753`, `core/planner.py:767`, `core/planner.py:778`).
- `MEMORY_COMMIT` без `memory_item` кидает runtime error (`core/planner.py:1041`, `core/planner.py:1045`; подтверждено `tests/test_planner.py:83`, `tests/test_planner.py:91`).
- В коде есть semantic-actions helpers, но вызовов этих функций в конструкторе финального плана не найдено (`core/planner.py:244`, `core/planner.py:310`; `rg` по проекту показывает только определения, не вызовы).
- `CHAT_RESPONSE` мапится на `report` (`core/planner.py:43`), а `RunEngine` сохраняет только artifacts/sources/facts, не отдает chat-text (`core/run_engine.py:316`, `core/run_engine.py:397`).

Критические проблемы (P0):
- Потенциальный hard-fail ACT-плана при `plan_hint=[MEMORY_COMMIT]` и отсутствующем `memory_item` (`core/planner.py:1045`, `apps/api/routes/runs.py:426`, `apps/api/routes/runs.py:432`).

Быстрые улучшения (P1):
- Убрать/подключить dead-code ветку semantic-actions (`_build_steps_from_semantic`, `_append_semantic_memory_step`) в `create_plan_for_run`.
- Развести `CHAT_RESPONSE` и `report` на разные skill-контракты или добавить явный `chat_response` persistence path.

### 3) Brain/LLM routing (`core/brain/*`, providers, retries, budget, cloud/local)
Оценки: Готовность `8/10`, Надёжность `7/10`, Качество UX `7/10`, Наблюдаемость `9/10`, Тестируемость `8/10`.

Обоснование:
- Конфиг из env покрывает local/cloud/retries/backoff/budget/concurrency (`core/brain/router.py:43`, `core/brain/router.py:74`, `core/brain/router.py:76`).
- Есть очередь конкуренции (`BrainQueue`) и контроль inflight (`core/brain/router.py:81`, `core/brain/router.py:93`, `core/brain/router.py:101`).
- Есть cloud retry с exponential backoff+jitter для 429/5xx (`core/brain/router.py:413`, `core/brain/router.py:435`, `core/brain/router.py:450`).
- Есть budget guard (`per_run`, `per_step`) и событие `llm_budget_exceeded` (`core/brain/router.py:278`, `core/brain/router.py:283`, `core/brain/router.py:574`).
- Санитизация контекста и fallback на LOCAL при пустом cloud payload (`core/brain/router.py:211`, `core/brain/router.py:229`; `core/llm_routing.py:183`).
- Ошибки local LLM пишутся в artifacts с sanitize payload (`core/brain/providers.py:59`, `core/brain/providers.py:84`, `core/brain/providers.py:191`).
- Покрыто тестами: очередь, backoff, privacy route, audit events (`tests/test_brain_layer.py:22`, `tests/test_brain_layer.py:73`, `tests/test_privacy_routing.py:76`, `tests/test_privacy_routing.py:112`).

Критические проблемы (P0):
- Подтверждённых P0 по этому аспекту не найдено по текущим тестам/коду.

Быстрые улучшения (P1):
- Добавить retry-контур для локального провайдера не только при 500/simplified-payload, но и на transient connection faults.
- Добавить structured user-facing message по `budget_exceeded` в API/UI, сейчас это в основном event-level.

### 4) Контекст/профиль/память в system (`core/chat_context.py`, `apps/api/routes/runs.py` и др.)
Оценки: Готовность `7/10`, Надёжность `6/10`, Качество UX `7/10`, Наблюдаемость `6/10`, Тестируемость `7/10`.

Обоснование:
- Профиль строится из `user_memories` (name/style/profile block) (`core/chat_context.py:120`, `core/chat_context.py:123`, `core/chat_context.py:124`).
- Фолбек имени делается regex-парсингом из текста записи (`core/chat_context.py:25`, `core/chat_context.py:47`).
- API при `create_run` подтягивает profile + history и memory_interpretation (`apps/api/routes/runs.py:317`, `apps/api/routes/runs.py:319`, `apps/api/routes/runs.py:323`).
- Система-подсказка чата включает user profile + style hints (`apps/api/routes/runs.py:240`, `apps/api/routes/runs.py:247`, `apps/api/routes/runs.py:249`).
- Ошибки memory interpreter логируются как `llm_request_failed` (без падения до этапа save) (`apps/api/routes/runs.py:332`, `apps/api/routes/runs.py:347`).
- Есть тесты profile/memory/chat history (`tests/test_profile_memory.py:53`, `tests/test_profile_memory.py:84`, `tests/test_chat_history.py:37`).

Критические проблемы (P0):
- Подтверждённых P0 по этому аспекту не найдено.

Быстрые улучшения (P1):
- Добавить детерминированный parser для `user_name` в meta вместо regex fallback из free-text.
- Добавить контракты на максимальный объём profile block в prompt и отдельный тест на clipping.

### 5) Memory store/DB (`memory/*`, WAL, схемы, migrations)
Оценки: Готовность `8/10`, Надёжность `6/10`, Качество UX `6/10`, Наблюдаемость `7/10`, Тестируемость `7/10`.

Обоснование:
- SQLite включён в WAL + synchronous NORMAL (`memory/db.py:22`, `memory/db.py:23`).
- Инициализация миграций и `schema_migrations` есть (`memory/db.py:27`, `memory/db.py:46`, `memory/db.py:57`).
- База событий и user_memories persist в одном store с lock (`memory/store.py:14`, `memory/store.py:1354`, `memory/store.py:1421`).
- Таблицы `user_memories` и `reminders` отдельными миграциями (`memory/migrations/006_user_memories.sql:1`, `memory/migrations/007_reminders.sql:1`).
- Миграции сортируются лексикографически по имени файла (`memory/db.py:50`), при этом есть дубли префиксов `002_*`, `003_*` (вывод `ls -1 memory/migrations`).
- CRUD памяти покрыт тестами (`tests/test_memory_v1.py:50`, `tests/test_memory_v1.py:75`, `tests/test_memory_v1.py:117`).

Критические проблемы (P0):
- Подтверждённых P0 по этому аспекту не найдено.

Быстрые улучшения (P1):
- Нормализовать нумерацию миграций (уникальный монотонный prefix) и добавить тест порядка применения.
- Добавить миграционный smoke-test на чистой БД + обновление с прошлых версий.

### 6) Reminders (`core/reminders/*` + `skills/reminder_create`)
Оценки: Готовность `7/10`, Надёжность `6/10`, Качество UX `6/10`, Наблюдаемость `7/10`, Тестируемость `8/10`.

Обоснование:
- Парсер поддерживает несколько шаблонов (`через`, `сегодня/завтра в`, `в HH:MM`) (`core/reminders/parser.py:51`, `core/reminders/parser.py:64`, `core/reminders/parser.py:89`).
- Scheduler делает claim due reminders и доставку с retry для Telegram (`core/reminders/scheduler.py:73`, `core/reminders/scheduler.py:108`, `core/reminders/scheduler.py:116`).
- При отсутствии Telegram-конфига есть fallback в local delivery (`core/reminders/scheduler.py:100`, `core/reminders/scheduler.py:104`).
- Эмитятся события `reminder_due/sent/failed/created` (`core/reminders/scheduler.py:95`, `core/reminders/scheduler.py:113`, `skills/reminder_create/skill.py:41`).
- В loop scheduler исключения глушатся и поток живёт (`core/reminders/scheduler.py:79`, `core/reminders/scheduler.py:83`).
- Тесты parser/store/api/scheduler присутствуют (`tests/test_reminders.py:47`, `tests/test_reminders.py:64`, `tests/test_reminders.py:84`, `tests/test_reminders.py:104`).

Критические проблемы (P0):
- Подтверждённых P0 по этому аспекту не найдено.

Быстрые улучшения (P1):
- Добавить явный event/log при исключениях в `_loop` вместо silent pass.
- Расширить парсер на даты/календарные форматы и добавить негативные тест-кейсы.

### 7) Web research (`skills/web_research` + `core/providers/search_client.py`)
Оценки: Готовность `7/10`, Надёжность `5/10`, Качество UX `6/10`, Наблюдаемость `4/10`, Тестируемость `7/10`.

Обоснование:
- Есть два режима (candidates/deep), ограничения раундов/источников и LLM-judge+answer (`skills/web_research/skill.py:16`, `skills/web_research/skill.py:481`, `skills/web_research/skill.py:562`, `skills/web_research/skill.py:576`).
- Search provider конфигурируется через `ddgs/yandex/stub` (`core/providers/search_client.py:87`, `core/providers/search_client.py:98`, `core/providers/search_client.py:108`).
- Нет retry/backoff в `fetch_url` и `search_client`; ошибка возвращается сразу (`core/providers/web_fetch.py:38`, `core/providers/web_fetch.py:46`; `core/providers/search_client.py:59`).
- Deep mode явно падает на `stub` без urls (`skills/web_research/skill.py:500`, `skills/web_research/skill.py:501`).
- При отсутствии пакета `ddgs` выбрасывается runtime error (`core/providers/search_client.py:130`, `core/providers/search_client.py:134`).
- Наблюдаемость ограничена: внутри deep-loop нет event emission по раундам/поисковым фейлам, в основном возвращаются assumptions (`skills/web_research/skill.py:437`, `skills/web_research/skill.py:516`, `skills/web_research/skill.py:558`).
- Тесты есть для provider mapping и deep сценариев (`tests/test_search_client.py:8`, `tests/test_search_client.py:29`, `tests/test_web_research_deep.py:33`, `tests/test_web_research_deep.py:153`).

Пример потенциального фейла (обязательный, т.к. Надёжность < 6):
- Если в окружении нет `ddgs`, `build_search_client` падает `RuntimeError`, deep run вернёт fail-результат с `search_client_failed` (`core/providers/search_client.py:130`, `core/providers/search_client.py:134`, `skills/web_research/skill.py:496`, `skills/web_research/skill.py:498`).

Критические проблемы (P0):
- Отсутствие failover-провайдера поиска при падении/отсутствии `ddgs` приводит к полной недоступности deep research (`core/providers/search_client.py:130`, `skills/web_research/skill.py:498`).

Быстрые улучшения (P1):
- Добавить retry/backoff для `fetch_url` и `client.search` + circuit breaker на домен.
- Эмитить `task_progress`/`source_found` события на каждом раунде deep-loop (с reason-кодами ошибок).

### 8) Autopilot computer / bridge (`skills/autopilot_computer` + `core/bridge` + tauri bridge endpoints)
Оценки: Готовность `7/10`, Надёжность `5/10`, Качество UX `6/10`, Наблюдаемость `8/10`, Тестируемость `6/10`.

Обоснование:
- Executor поддерживает approvals, retries, user-action-required и rich events (`core/executor/computer_executor.py:172`, `core/executor/computer_executor.py:237`, `core/executor/computer_executor.py:715`, `core/executor/computer_executor.py:906`).
- Skill `autopilot_computer` делает loop detect, approve flow, artifacts (`skills/autopilot_computer/skill.py:224`, `skills/autopilot_computer/skill.py:232`, `skills/autopilot_computer/skill.py:378`, `skills/autopilot_computer/skill.py:414`).
- Bridge-клиент Python делает прямой POST и падает на HTTP >=400, без retry (`core/bridge/desktop_bridge.py:33`, `core/bridge/desktop_bridge.py:35`).
- Tauri bridge открывает localhost HTTP с CORS `*` и без auth-проверки (`apps/desktop/src-tauri/src/bridge.rs:71`, `apps/desktop/src-tauri/src/bridge.rs:103`, `apps/desktop/src-tauri/src/bridge.rs:105`).
- Через bridge доступны shell/OS-control endpoints (`apps/desktop/src-tauri/src/bridge.rs:90`, `apps/desktop/src-tauri/src/bridge.rs:174`, `apps/desktop/src-tauri/src/bridge.rs:181`).
- Проверка permissions упрощённая (fallback на `Enigo::new`) (`apps/desktop/src-tauri/src/autopilot/permissions.rs:31`, `apps/desktop/src-tauri/src/autopilot/permissions.rs:34`).
- Тесты покрывают executor-loop и autopilot events, но не e2e bridge security (`tests/test_executor_loop.py:93`, `tests/test_executor_loop.py:151`, `tests/test_autopilot_events.py:53`).

Пример потенциального фейла (обязательный, т.к. Надёжность < 6):
- При недоступном bridge любой `autopilot_capture/act` вызывает `RuntimeError` и шаг падает без ретраев (`core/bridge/desktop_bridge.py:26`, `core/bridge/desktop_bridge.py:33`, `core/bridge/desktop_bridge.py:35`).

Критические проблемы (P0):
- Локальный HTTP bridge без auth и с `Access-Control-Allow-Origin: *` + shell/OS endpoints = высокий риск для локального хоста (`apps/desktop/src-tauri/src/bridge.rs:71`, `apps/desktop/src-tauri/src/bridge.rs:105`, `apps/desktop/src-tauri/src/bridge.rs:174`).

Быстрые улучшения (P1):
- Добавить bridge auth token (header) и reject по умолчанию без токена.
- Добавить client-side retry policy и классификацию bridge-ошибок в `DesktopBridge._post`.

### 9) OCR (`core/ocr/*`) и интеграция в executor
Оценки: Готовность `6/10`, Надёжность `6/10`, Качество UX `5/10`, Наблюдаемость `7/10`, Тестируемость `6/10`.

Обоснование:
- OCR provider на Tesseract с проверкой бинаря/зависимостей (`core/ocr/engine.py:25`, `core/ocr/engine.py:29`, `core/ocr/engine.py:32`).
- Есть in-memory cache `OCRCache` (`core/ocr/engine.py:69`, `core/ocr/engine.py:73`, `core/ocr/engine.py:76`).
- Executor сначала проверяет cache и эмитит `ocr_cached_hit`, иначе `ocr_performed` (`core/executor/computer_executor.py:660`, `core/executor/computer_executor.py:664`, `core/executor/computer_executor.py:682`).
- OCR участвует в success-check verify (`core/executor/computer_executor.py:648`, `core/executor/computer_executor.py:651`).
- Если провайдер недоступен, OCR тихо отключается (`core/ocr/engine.py:80`, `core/ocr/engine.py:84`).
- Есть точечный тест cache behavior (`tests/test_ocr_cache.py:30`, `tests/test_ocr_cache.py:43`, `tests/test_ocr_cache.py:48`).

Критические проблемы (P0):
- Подтверждённых P0 по этому аспекту не найдено.

Быстрые улучшения (P1):
- Добавить user-facing сигнал в UI при `ocr provider unavailable` вместо silent fallback.
- Добавить e2e тесты OCR-интеграции с реальными изображениями/языками.

### 10) Safety approvals (`core/safety/*` + schemas/events approval*)
Оценки: Готовность `7/10`, Надёжность `6/10`, Качество UX `7/10`, Наблюдаемость `8/10`, Тестируемость `7/10`.

Обоснование:
- Типы approval и map danger->approval централизованы (`core/safety/approvals.py:5`, `core/safety/approvals.py:14`, `core/safety/approvals.py:42`).
- Preview/proposed_actions формируются единообразно (`core/safety/approvals.py:51`, `core/safety/approvals.py:87`, `core/safety/approvals.py:123`).
- Схемы approval событий есть и строгие (`schemas/events/approval_requested.schema.json:4`, `schemas/events/approval_requested.schema.json:38`, `schemas/events/approval_resolved.schema.json:24`).
- Runtime эмитит полный цикл approval событий в executor/runner (`core/executor/computer_executor.py:743`, `core/executor/computer_executor.py:770`, `core/skills/runner.py:73`, `core/skills/runner.py:107`).
- API endpoints approve/reject также эмитят approval events (`apps/api/routes/runs.py:640`, `apps/api/routes/runs.py:648`, `apps/api/routes/runs.py:661`).
- Контрактные тесты проверяют присутствие approval events (`tests/test_contracts.py:153`, `tests/test_contracts.py:203`, `tests/test_contracts.py:204`).

Критические проблемы (P0):
- Подтверждённых P0 по этому аспекту не найдено.

Быстрые улучшения (P1):
- Исключить дублирование/рассинхрон эмиссии approval events между API approve/reject и executor/runner paths.
- Добавить единый idempotency-контракт на approve/reject endpoint.

### 11) Event bus + schemas/events (`core/event_bus.py`, `schemas/events/*`)
Оценки: Готовность `8/10`, Надёжность `7/10`, Качество UX `6/10`, Наблюдаемость `9/10`, Тестируемость `8/10`.

Обоснование:
- Event types грузятся из `schemas/events/*.schema.json`; есть fallback default set (`core/event_bus.py:48`, `core/event_bus.py:61`).
- `emit` валидирует тип события и пишет в store (`core/event_bus.py:68`, `core/event_bus.py:69`, `core/event_bus.py:71`).
- Глобальный `schemas/event.schema.json` фиксирует enum по всем типам (`schemas/event.schema.json:19`, `schemas/event.schema.json:22`, `schemas/event.schema.json:82`).
- Sync-тест проверяет равенство schema files vs enum vs allowed types (`tests/test_event_types_sync.py:9`, `tests/test_event_types_sync.py:18`, `tests/test_event_types_sync.py:19`).
- Contract test валидирует event payload на SSE (`tests/test_contracts.py:149`, `tests/test_contracts.py:150`).

Критические проблемы (P0):
- Подтверждённых P0 по этому аспекту не найдено.

Быстрые улучшения (P1):
- Добавить версионирование event payload schema (например `x-schema-version`) для безопасной эволюции UI.
- Добавить CI check для обратной совместимости payload обязательных полей.

### 12) API слой (`apps/api/*`: auth, runs, run_events/SSE, projects, memory, reminders)
Оценки: Готовность `7/10`, Надёжность `6/10`, Качество UX `7/10`, Наблюдаемость `7/10`, Тестируемость `8/10`.

Обоснование:
- App wiring и bootstrap store/engine/scheduler есть (`apps/api/main.py:40`, `apps/api/main.py:43`, `apps/api/main.py:46`, `apps/api/main.py:48`).
- Auth: local/strict, token hash+salt, сравнение через hmac (`apps/api/auth.py:20`, `apps/api/auth.py:64`, `apps/api/auth.py:109`).
- В local mode loopback клиент проходит без токена (`apps/api/auth.py:78`, `apps/api/auth.py:83`, `apps/api/auth.py:87`).
- Runs route включает intent, memory interpreter, chat/act split, события ошибок (`apps/api/routes/runs.py:283`, `apps/api/routes/runs.py:323`, `apps/api/routes/runs.py:436`, `apps/api/routes/runs.py:452`).
- SSE endpoint работает через polling events_since (`apps/api/routes/run_events.py:35`, `apps/api/routes/run_events.py:44`).
- CRUD routes для `projects/memory/reminders/skills` присутствуют (`apps/api/routes/projects.py:12`, `apps/api/routes/memory.py:20`, `apps/api/routes/reminders.py:23`, `apps/api/routes/skills.py:15`).
- Тесты API/контрактов есть (`tests/test_contracts.py:106`, `tests/test_memory_v1.py:75`, `tests/test_reminders.py:104`, `tests/test_smoke.py:109`).

Критические проблемы (P0):
- По умолчанию запуск выставляет `ASTRA_AUTH_MODE=local`, а local mode разрешает loopback без токена (`scripts/run.sh:20`, `apps/api/auth.py:78`, `apps/api/auth.py:83`).

Быстрые улучшения (P1):
- В desktop default перейти на strict + явный bootstrap токена.
- Для SSE добавить heartbeat event и метрику лага (сейчас только polling sleep 0.5s).

### 13) Desktop UI слой (`apps/desktop/*`: api client, eventStream, appStore, overlay)
Оценки: Готовность `7/10`, Надёжность `6/10`, Качество UX `8/10`, Наблюдаемость `6/10`, Тестируемость `6/10`.

Обоснование:
- API client имеет нормализацию auth/network/server ошибок (`apps/desktop/src/shared/api/client.ts:26`, `apps/desktop/src/shared/api/client.ts:39`, `apps/desktop/src/shared/api/client.ts:53`).
- SSE manager реализует reconnect/backoff/heartbeat/dedup (`apps/desktop/src/shared/api/eventStream.ts:19`, `apps/desktop/src/shared/api/eventStream.ts:109`, `apps/desktop/src/shared/api/eventStream.ts:128`, `apps/desktop/src/shared/api/eventStream.ts:98`).
- App store поддерживает fallback polling при reconnect/offline (`apps/desktop/src/shared/store/appStore.ts:823`, `apps/desktop/src/shared/store/appStore.ts:1214`, `apps/desktop/src/shared/store/appStore.ts:1220`).
- Overlay получает статус/последние сообщения/pending approvals (`apps/desktop/src/app/AppShell.tsx:175`, `apps/desktop/src/app/AppShell.tsx:205`, `apps/desktop/src/app/AppShell.tsx:238`, `apps/desktop/src/app/OverlayApp.tsx:198`).
- Уведомления и reminders lifecycle есть (`apps/desktop/src/shared/store/appStore.ts:1458`, `apps/desktop/src/shared/store/appStore.ts:1529`, `apps/desktop/src/shared/store/appStore.ts:1552`).
- Unit tests есть, но покрывают ограниченный набор (`apps/desktop/src/__tests__/auth_controller.test.ts:43`, `apps/desktop/src/__tests__/notifications_store.test.ts:5`, `apps/desktop/src/__tests__/overlay_utils.test.ts:5`, `apps/desktop/src/__tests__/ui_utils.test.ts:6`).

Критические проблемы (P0):
- Подтверждённых P0 по этому аспекту не найдено.

Быстрые улучшения (P1):
- Добавить e2e тесты UI-потока (SSE reconnect + approval flow + reminder notifications).
- Добавить telemetry слой для client-side SSE ошибок/latency (сейчас mostly local store state).

### 14) Скрипты запуска/doctor/qa (`scripts/*`)
Оценки: Готовность `8/10`, Надёжность `6/10`, Качество UX `7/10`, Наблюдаемость `6/10`, Тестируемость `4/10`.

Обоснование:
- `run.sh` поднимает venv/api/desktop и умеет foreground/background (`scripts/run.sh:7`, `scripts/run.sh:88`, `scripts/run.sh:126`, `scripts/run.sh:143`).
- `doctor.sh` проверяет prereq/runtime, OCR, Ollama, auth/API/SSE (`scripts/doctor.sh:54`, `scripts/doctor.sh:70`, `scripts/doctor.sh:96`, `scripts/doctor.sh:191`, `scripts/doctor.sh:315`).
- `qa.sh` объединяет doctor+pytest+scenario runner (`scripts/qa.sh:29`, `scripts/qa.sh:33`, `scripts/qa.sh:36`).
- `check.sh` гоняет ruff/pytest/lint/build (`scripts/check.sh:15`, `scripts/check.sh:16`, `scripts/check.sh:18`).
- `run_smoke.py` и `run_scenarios.py` сохраняют артефакты и проверяют инварианты (`scripts/run_smoke.py:110`, `scripts/run_smoke.py:250`, `scripts/run_scenarios.py:170`, `scripts/run_scenarios.py:273`).
- По факту `doctor prereq` сейчас FAIL из-за недоступного Ollama (командный вывод).

Критические проблемы (P0):
- Подтверждённых P0 в самом коде scripts не найдено; критичный runtime-факт: локальный LLM prereq не выполнен (`./scripts/doctor.sh prereq` -> `FAIL Ollama not reachable...`).

Быстрые улучшения (P1):
- Добавить machine-readable JSON output в `doctor.sh` для CI gating.
- Разделить `run.sh` на install/init и run (сейчас `pip install` + `npm install` на каждый запуск: `scripts/run.sh:62`, `scripts/run.sh:63`, `scripts/run.sh:65`).

## Шаг 6: Итог

### Top 10 P0 по проекту
1. Desktop bridge не требует auth и открыт через CORS `*`, при этом содержит shell/OS-control endpoints (`apps/desktop/src-tauri/src/bridge.rs:103`, `apps/desktop/src-tauri/src/bridge.rs:105`, `apps/desktop/src-tauri/src/bridge.rs:174`).
2. API в default-run работает в `local` auth mode, loopback запросы проходят без токена (`scripts/run.sh:20`, `apps/api/auth.py:78`, `apps/api/auth.py:83`).
3. Планировщик может аварийно падать на `MEMORY_COMMIT` без `memory_item` (`core/planner.py:1045`, `tests/test_planner.py:91`), что валит ACT run (`apps/api/routes/runs.py:426`, `apps/api/routes/runs.py:432`).
4. Web research deep-mode полностью недоступен при отсутствии `ddgs` (runtime error без failover) (`core/providers/search_client.py:130`, `skills/web_research/skill.py:498`).
5. Web research deep-mode явно запрещает `stub` без urls, что даёт hard fail сценария (`skills/web_research/skill.py:500`, `skills/web_research/skill.py:501`).
6. Bridge client падает на любой HTTP>=400 без ретраев (`core/bridge/desktop_bridge.py:33`, `core/bridge/desktop_bridge.py:35`), что напрямую срывает autopilot step.
7. `CHAT_RESPONSE` kind сопоставлен со skill `report`, что может ломать ожидаемый контракт «ответ пользователю» в плановых ACT-chain (`core/planner.py:43`, `core/planner.py:1083`, `core/run_engine.py:316`).
8. Миграции имеют дубли числовых префиксов (`002_*`, `003_*`) при лексикографическом применении, что рискованно для эволюции схемы (`memory/db.py:50`, `ls -1 memory/migrations`).
9. `doctor prereq` фиксирует отсутствующий Ollama, что блокирует локальные LLM paths в runtime (`./scripts/doctor.sh prereq` вывод `FAIL Ollama not reachable ...`).
10. Локальные shell-операции доступны через bridge endpoint `POST /shell/execute` без уровня авторизации на самом bridge (`apps/desktop/src-tauri/src/bridge.rs:174`, `apps/desktop/src-tauri/src/bridge.rs:187`).

### Top 10 P1
1. Внедрить auth-token handshake между Python bridge client и Tauri bridge endpoint.
2. Перевести desktop default в `strict` auth mode, оставить `local` только явным флагом dev.
3. Добавить fallback в planner при `planner_memory_item_missing`: downgrade до `ASK_CLARIFY` или skip MEMORY_COMMIT.
4. Добавить multi-provider fallback в search client: `ddgs -> yandex -> explicit urls`.
5. Добавить retry/backoff в `web_fetch.fetch_url` и `DDGSMetaSearchClient.search`.
6. Интегрировать/удалить dead semantic-actions ветку planner (`_build_steps_from_semantic`, `_append_semantic_memory_step`).
7. Развести `CHAT_RESPONSE` и `report` skill-контракты.
8. Нормализовать нумерацию миграций и добавить migration-order тест.
9. Добавить structured heartbeat/lag метрики в SSE API + UI diagnostics.
10. Разделить scripts на install/init/run и сделать `doctor` JSON output для CI.

### Что НЕИЗВЕСТНО и что проверить
- `НЕИЗВЕСТНО`: реальная безопасность bridge в прод-конфиге (возможны внешние сетевые ограничения ОС/firewall). Проверить:
  - `lsof -nP -iTCP:43124 -sTCP:LISTEN`
  - `curl -i http://127.0.0.1:43124/autopilot/permissions`
- `НЕИЗВЕСТНО`: e2e стабильность autoplay/overlay на реальном desktop UI (аудит опирался на unit tests и код, не на интерактивный прогон). Проверить:
  - `npm --prefix apps/desktop run tauri dev`
  - сценарий `scripts/run_smoke.py` и просмотр `artifacts/smoke/*`.
- `НЕИЗВЕСТНО`: устойчивость deep web research под нестабильной сетью и rate-limit в реальном окружении. Проверить:
  - интеграционный прогон с `search.provider=ddgs`/`yandex`
  - capture событий `llm_request_failed`, `source_fetched` по run id.
- `НЕИЗВЕСТНО`: миграционная совместимость на старых версиях базы. Проверить:
  - чистая БД + апгрейд с исторического snapshot
  - diff `schema_migrations` и smoke CRUD.
- `НЕИЗВЕСТНО`: runtime влияние deprecated `jsonschema.RefResolver`. Проверить:
  - обновление `jsonschema` и прогон `tests/test_contracts.py`.

### План стабилизации на 1–2 недели
1. День 1–2: закрыть security perimeter.
   - Bridge auth token + reject без токена.
   - Перевести default auth mode на strict в desktop run-path.
2. День 3–4: стабилизировать planner/search.
   - Fallback при `planner_memory_item_missing`.
   - Search failover + retries для `web_fetch`.
3. День 5–6: контрактное выравнивание.
   - Развести `CHAT_RESPONSE` и `report`.
   - Решить судьбу dead semantic-actions path.
4. День 7–8: база и миграции.
   - Уникальные migration prefixes, migration-order тесты, upgrade smoke.
5. День 9–10: observability и QA.
   - SSE heartbeat/lag метрики + UI diagnostics.
   - Расширить e2e smoke (`run_smoke.py`, approvals flow, web research reliability).

## Список источников

### Команды
- `find core skills apps/api apps/desktop memory schemas prompts scripts -maxdepth 2 -type d | rg -v 'node_modules|dist|target|__pycache__' | sort`
- `ls -1 skills`
- `find skills -maxdepth 2 -type f -name "skill.py" -print | sort`
- `rg -n "class .*Skill|skill\s*=|def run\(|def execute\(" -S skills core`
- `python3 -m pytest -q`
- `npm --prefix apps/desktop run test`
- `npm --prefix apps/desktop run lint`
- `./scripts/doctor.sh prereq`
- `rg -n "TODO|FIXME|HACK|TEMP|stub|NEED|legacy|fallback|re\.compile\(|TRIGGERS|any\(phrase in|in normalized" -S core skills apps/api memory prompts`
- `ls -1 memory/migrations | sort`
- `rg -n "analyze_user_message|collect_memory_facts|extract_web_research|extract_reminders|semantic_actions" -S core apps skills`
- `ls -1 scripts | sort`
- множество целевых `nl -ba <file> | sed -n ...` и `rg -n ...` для подтверждения строк в разделах ниже.

### File:line (основные)
- `core/intent_router.py:86`
- `core/intent_router.py:108`
- `core/semantic/decision.py:76`
- `core/semantic/decision.py:145`
- `core/semantic/decision.py:205`
- `prompts/semantic_decision.md:5`
- `prompts/semantic_decision.md:15`
- `prompts/semantic_intent_actions_system.txt:1`
- `core/planner.py:42`
- `core/planner.py:90`
- `core/planner.py:244`
- `core/planner.py:310`
- `core/planner.py:734`
- `core/planner.py:1045`
- `core/planner.py:1072`
- `core/planner.py:1158`
- `core/brain/router.py:43`
- `core/brain/router.py:81`
- `core/brain/router.py:211`
- `core/brain/router.py:229`
- `core/brain/router.py:278`
- `core/brain/router.py:404`
- `core/brain/providers.py:59`
- `core/brain/providers.py:191`
- `core/llm_routing.py:93`
- `core/llm_routing.py:183`
- `core/llm_routing.py:250`
- `core/chat_context.py:120`
- `core/chat_context.py:123`
- `core/memory/interpreter.py:199`
- `apps/api/routes/runs.py:253`
- `apps/api/routes/runs.py:283`
- `apps/api/routes/runs.py:323`
- `apps/api/routes/runs.py:436`
- `apps/api/routes/runs.py:454`
- `apps/api/routes/runs.py:640`
- `apps/api/routes/run_events.py:15`
- `apps/api/routes/run_events.py:30`
- `apps/api/routes/run_events.py:46`
- `apps/api/main.py:40`
- `apps/api/auth.py:78`
- `apps/api/auth.py:83`
- `apps/api/auth.py:109`
- `memory/db.py:22`
- `memory/db.py:50`
- `memory/store.py:14`
- `memory/store.py:1197`
- `memory/store.py:1225`
- `memory/store.py:1354`
- `memory/migrations/001_init.sql:1`
- `memory/migrations/006_user_memories.sql:1`
- `memory/migrations/007_reminders.sql:1`
- `core/reminders/parser.py:51`
- `core/reminders/scheduler.py:73`
- `core/reminders/scheduler.py:108`
- `skills/reminder_create/skill.py:19`
- `core/providers/search_client.py:87`
- `core/providers/search_client.py:130`
- `core/providers/web_fetch.py:38`
- `skills/web_research/manifest.json:8`
- `skills/web_research/skill.py:481`
- `skills/web_research/skill.py:500`
- `skills/web_research/skill.py:516`
- `skills/web_research/skill.py:562`
- `skills/web_research/skill.py:630`
- `core/executor/computer_executor.py:172`
- `core/executor/computer_executor.py:376`
- `core/executor/computer_executor.py:601`
- `core/executor/computer_executor.py:715`
- `core/bridge/desktop_bridge.py:33`
- `apps/desktop/src-tauri/src/bridge.rs:71`
- `apps/desktop/src-tauri/src/bridge.rs:103`
- `apps/desktop/src-tauri/src/bridge.rs:174`
- `apps/desktop/src-tauri/src/autopilot/permissions.rs:31`
- `core/ocr/engine.py:25`
- `core/ocr/engine.py:69`
- `core/ocr/engine.py:80`
- `core/safety/approvals.py:42`
- `core/safety/approvals.py:51`
- `schemas/events/approval_requested.schema.json:4`
- `schemas/events/approval_resolved.schema.json:24`
- `core/event_bus.py:48`
- `core/event_bus.py:68`
- `schemas/event.schema.json:19`
- `apps/desktop/src/shared/api/client.ts:26`
- `apps/desktop/src/shared/api/eventStream.ts:109`
- `apps/desktop/src/shared/store/appStore.ts:76`
- `apps/desktop/src/shared/store/appStore.ts:1209`
- `apps/desktop/src/app/AppShell.tsx:175`
- `apps/desktop/src/app/OverlayApp.tsx:198`
- `scripts/run.sh:20`
- `scripts/run.sh:62`
- `scripts/doctor.sh:54`
- `scripts/doctor.sh:96`
- `scripts/qa.sh:29`
- `scripts/check.sh:15`
- `scripts/run_smoke.py:110`
- `scripts/run_scenarios.py:170`
- `tests/test_planner.py:83`
- `tests/test_planner.py:91`
- `tests/test_intent_router.py:30`
- `tests/test_semantic_routing.py:114`
- `tests/test_brain_layer.py:22`
- `tests/test_privacy_routing.py:76`
- `tests/test_event_types_sync.py:9`
- `tests/test_contracts.py:149`
- `tests/test_memory_v1.py:75`
- `tests/test_reminders.py:104`
- `tests/test_executor_loop.py:151`
- `tests/test_autopilot_events.py:53`
- `tests/test_ocr_cache.py:30`
- `apps/desktop/src/__tests__/auth_controller.test.ts:43`
- `apps/desktop/src/__tests__/notifications_store.test.ts:5`
