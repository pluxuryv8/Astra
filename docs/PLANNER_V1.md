# Planner v1

## Что делает
- Строит исполнимый план шагов по запросу пользователя.
- Использует `IntentRouter`: `CHAT` → один шаг ответа, `ACT` → действия на компьютере, `ASK_CLARIFY` → план не строится.
- В план добавляются `success_criteria`, `danger_flags` и `requires_approval`.
- `shell` в MVP не используется.
- `memory_save` добавляется только при явной команде “запомни/сохрани”.

## Kinds шагов
- `CHAT_RESPONSE`
- `CLARIFY_QUESTION`
- `BROWSER_RESEARCH_UI`
- `COMPUTER_ACTIONS`
- `DOCUMENT_WRITE`
- `FILE_ORGANIZE`
- `CODE_ASSIST`
- `MEMORY_COMMIT`

## Как строится план
1. Rules-first: шаблоны для типовых задач (плейлист, сортировка, VSCode, доклад).
2. LLM fallback: если шаблон не найден — запрос к Brain с JSON-планом.
3. Опасные шаги помечаются `danger_flags` + `requires_approval=true`.
4. При паролях/кодах добавляется `CLARIFY_QUESTION` с просьбой ввода вручную.

## Память
- `MEMORY_COMMIT` добавляется только если запрос содержит триггер: “запомни/сохрани/в память/зафиксируй”.
- Иначе запись в память не планируется.

## Примеры
**Плейлист**
- `BROWSER_RESEARCH_UI`: открыть сервис музыки
- `COMPUTER_ACTIONS`: создать плейлист
- `COMPUTER_ACTIONS`: добавить треки

**Рабочий стол**
- `FILE_ORGANIZE`: открыть рабочий стол
- `FILE_ORGANIZE`: сгруппировать иконки

**VSCode**
- `COMPUTER_ACTIONS`: открыть VSCode
- `CODE_ASSIST`: открыть проект
- `CODE_ASSIST`: собрать ошибки

## Где встроено
- Планировщик: `core/planner.py`
- Создание плана: `core/run_engine.py` (emit `plan_created`, `step_planned`)
- API entrypoint: `apps/api/routes/runs.py`
