# Randarc‑Astra: текущее состояние фронта и бэка

Дата: 5 февраля 2026

## Фронт (HUD‑оверлей)

Окно одно. Это главный интерфейс, всегда поверх остальных окон.

### Внешний вид

- Прозрачное окно без рамок, тёмный графитовый стеклянный фон.
- Лёгкий космический градиент и тонкая фоновая сетка.
- Мягкие анимации появления карточек и статуса.
- Перетаскивание за шапку, размер окна можно менять вручную.
- Авто‑высота включена по умолчанию (можно выключить в настройках).
- Кнопка `Скрыть` убирает HUD без остановки процесса.

### Idle‑состояние

- Сверху: `Astra`.
- Приветствие: «Чем займёмся?».
- Одно поле ввода команды + `Enter` запускает.

### Выполнение

- Карточка `Сейчас`: текущий шаг, размышление, цель.
- Карточка `Задачи`: список шагов плана + статусы (думает/делает/готово/ошибка).
- Карточка `Действия`: последние действия автопилота.
- Карточка `Журнал`: последние события.
- Карточка `Подтверждение`: появляется при pending approvals.
- Нижняя панель: покрытие, конфликты, свежесть, подтверждения + экспорт.

### Настройки внутри HUD

Открываются поверх интерфейса без отдельного окна.

- Проект: выбор из списка (UI создания отсутствует).
- Режим запуска: plan_only / research / execute_confirm / autopilot_safe.
- Автопилот: интервал цикла, максимум действий/циклов, авторазмер.
- OpenAI: модель + пароль хранилища + ключ (сохранение локально).
- Разрешения macOS: проверка Screen Recording и Accessibility.

Где смотреть: `apps/desktop/src/App.tsx`, `apps/desktop/src/app.css`.

## Бэк (API + ядро)

### API (FastAPI)

Базовый префикс: `/api/v1`.

- Проекты: `GET /projects`, `POST /projects`, `GET /projects/{id}`, `PUT /projects/{id}`.
- Запуски: `POST /projects/{id}/runs`, `POST /runs/{id}/plan`, `POST /runs/{id}/start`, `POST /runs/{id}/cancel`, `POST /runs/{id}/pause`, `POST /runs/{id}/resume`.
- Повторы: `POST /runs/{id}/tasks/{task_id}/retry`, `POST /runs/{id}/steps/{step_id}/retry`.
- Снимок состояния: `GET /runs/{id}/snapshot`, `GET /runs/{id}/snapshot/download`.
- События: `GET /runs/{id}/events` (SSE), `GET /runs/{id}/events/download` (NDJSON).
- Артефакты: `GET /artifacts/{id}/download`.
- Навыки: `GET /skills`, `GET /skills/{name}/manifest`, `POST /skills/reload`.
- Секреты: `POST /secrets/unlock`, `POST /secrets/openai`, `GET /secrets/status`.
- Аутентификация: локальный токен, проверяется в `Authorization: Bearer`.

Где смотреть: `apps/api/main.py`, `apps/api/routes/*.py`.

### Ядро

- RunEngine: создание плана, запуск, исполнение шагов, пауза/отмена.
- EventBus: запись событий в базу и выдача через SSE.
- SkillRunner: валидирует входы по схемам и запускает навыки.
- Planner: фиксированный план (MVP) на основе текста команды.

Где смотреть: `core/run_engine.py`, `core/event_bus.py`, `core/planner.py`, `core/skills/runner.py`.

### Хранилище

- SQLite база: `.astra/astra.db`.
- Миграции: `memory/migrations/*.sql`.
- Таблицы: проекты, запуски, план, задачи, источники, факты, конфликты, артефакты, события, approvals.

Где смотреть: `memory/db.py`, `memory/store.py`, `memory/migrations/`.

### Хранилище секретов

- Локальный зашифрованный vault: `.astra/vault.bin`.
- Шифрование: NaCl SecretBox + Argon2id (pynacl).
- Пароль хранится в связке ключей macOS.

Где смотреть: `memory/vault.py`, `core/secrets.py`, `apps/api/routes/secrets.py`.

### Навыки

Активные навыки:

- `autopilot_computer` — цикл “скрин → решение → действия” через LLM и desktop‑bridge.
- `computer` — управление мышью/клавиатурой.
- `shell` — выполнение команд.
- `web_research` — поиск/источники.
- `extract_facts` — извлечение фактов.
- `conflict_scan` — поиск конфликтов.
- `report` — итоговый отчёт.
- `memory_save` — сохранение результатов в память.

Где смотреть: `skills/*/skill.py`, `skills/*/manifest.json`.

### Desktop‑bridge

- Локальный HTTP‑bridge для операций автопилота.
- Адрес: `127.0.0.1:43124` (можно изменить через `ASTRA_DESKTOP_BRIDGE_PORT`).
- Методы: `/autopilot/capture`, `/autopilot/act`, `/autopilot/permissions`, `/computer/*`, `/shell/*`.

Где смотреть: `apps/desktop/src-tauri/src/bridge.rs`.

## Что важно для постановки задач

- Интерфейс сейчас единый: HUD‑оверлей.
- UI не даёт создавать проект вручную. При отсутствии проектов создаётся дефолтный “Основной”.
- Запуск возможен только при наличии проекта и настроенного LLM.
- Автопилот работает через захват экрана + план действий в JSON.
