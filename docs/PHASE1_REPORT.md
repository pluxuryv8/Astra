# Фаза 1 — Отчёт (мозги, качество ответа, latency)

Дата: 2026-02-22  
Покрытие: промпты 6–16 из `docs/план Б`

## 1. Что изменилось по intent accuracy

- Усилен переход `fast_chat_path` vs semantic path на границах простых/сложных запросов.
- Введён явный `chat_response_mode` (`direct_answer` / `step_by_step_plan`) и reason.
- Добавлен более устойчивый degraded-путь при semantic/LLM сбоях с reason-codes в events.
- Добавлена адаптивная inference-настройка (`fast/balanced/complex`) под сложность запроса.

Проверка (intent gate):

```bash
PYTHONPATH=. pytest -q tests/test_intent_router.py tests/test_semantic_routing.py
```

Результат: `25 passed`.

## 2. Что изменилось по качеству ответа

- Добавлен deterministic pre-check + один безопасный retry для битых/нерелевантных ответов.
- Добавлена политика скрытого internal reasoning (без утечки `<think>`/internal notes в UI).
- Добавлен постпроцессор финального текста: краткий итог сверху, детали ниже, дедуп, чистка мусора.
- Добавлен анти-шаблонный слой (`template_like`) с регенерацией в рамках текущего budget/timeout.
- Усилен fallback-ответ при ошибках модели (полезный структурный ответ вместо «тишины»).
- Добавлен golden-набор сложных кейсов (декомпозиция, качество шагов, отсутствие мусора/токсичных вставок).
- Добавлена фильтрация токсичных мусорных строк в финальном постпроцессоре.

Проверка (brain quality gate):

```bash
PYTHONPATH=. pytest -q tests/test_brain_regressions.py tests/test_golden_complex_chat_cases.py
```

Результат: `4 passed, 1 xfailed`.  
`xfail` — известная проблема planner default-path (`COMPUTER_ACTIONS`) для сложных non-UI запросов.

## 3. Что изменилось по времени ответа (latency)

- Добавлен нагрузочный тест chat-path с отчётом `p50/p95`:
  - `tests/test_latency_chat_path.py`
- Для chat-path зафиксирована адаптивная настройка `max_tokens/temperature/top_p/repeat_penalty`:
  - короткие запросы: профиль `fast`
  - обычные: `balanced`
  - сложные: `complex`

Проверка (latency gate):

```bash
PYTHONPATH=. pytest -q -s tests/test_latency_chat_path.py
```

Текущий отчёт:

- short: elapsed `p50=19.9ms`, `p95=24.7ms`; runtime `p50=17.0ms`, `p95=17.7ms`
- medium: elapsed `p50=39.0ms`, `p95=40.9ms`; runtime `p50=33.0ms`, `p95=33.7ms`
- complex: elapsed `p50=64.6ms`, `p95=67.4ms`; runtime `p50=57.0ms`, `p95=58.0ms`

## 4. Общий статус quality gate

Полный набор:

```bash
pytest -q
```

Результат: `159 passed, 1 xfailed, 2 warnings`.

Итог фазы 1:

- Intent-path стал предсказуемее и лучше диагностируется.
- Качество финального текста существенно стабильнее на сложных кейсах.
- Latency измеряется и имеет явные p50/p95-гейты.

## 5. Остаточные риски

- Planner fallback на `COMPUTER_ACTIONS` (известный `xfail`) всё ещё требует отдельного закрытия.
- Метрики intent accuracy пока тестовые (offline gate), а не production dashboard.
