# Semantic Brain

## Где находится SemanticDecision
- Модель и валидация: `core/semantic/decision.py`
- Prompt: `prompts/semantic_decision.md`
- Точка входа intent-routing: `core/intent_router.py`
- Интеграция с API-пайплайном: `apps/api/routes/runs.py`

## Контракт JSON
SemanticDecision принимает только строгий JSON-объект:
- `intent`: `CHAT | ACT | ASK_CLARIFY`
- `confidence`: число `0..1`
- `memory_item`: `null` или объект `{kind, text, evidence}`
- `plan_hint`: массив `kind` из planner (`CHAT_RESPONSE`, `MEMORY_COMMIT`, `REMINDER_CREATE`, `BROWSER_RESEARCH_UI`, `COMPUTER_ACTIONS`, `DOCUMENT_WRITE`, `FILE_ORGANIZE`, `CODE_ASSIST`, `CLARIFY_QUESTION`, `SMOKE_RUN`)
- `response_style_hint`: `string | null`
- `user_visible_note`: `string | null`

Жёсткие правила:
- Никаких fallback-парсеров.
- `memory_item` не может быть массивом.
- `memory_item.evidence` обязана быть подстрокой исходного сообщения.
- На одно пользовательское сообщение сохраняется максимум один memory item.
- Legacy детекторы в planner отключены по умолчанию; включаются только через `ASTRA_LEGACY_DETECTORS=1`.

## Что считается памятью
Памятью считается нормализованный `memory_item.text`, который проходит через `skills/memory_save` и записывается в `user_memories` (`memory/store.py`).

Пайплайн:
1. `user_message`
2. `SemanticDecision` (LLM)
3. `memory_save` (если `memory_item != null`)
4. `planner.create_plan_for_run`
5. выполнение/ответ

## Как память подмешивается в ответы
Перед chat-ответом API берёт записи `store.list_user_memories(limit=50)`, собирает компактный профиль через `core/chat_context.py::build_profile_block` и добавляет его в `system`-сообщение. Профиль не отправляется как `user`-сообщение.

## Как мокать LLM в тестах
Варианты:
1. Мок низкого уровня semantic-решения:
- патчить `core.intent_router.decide_semantic` и возвращать `SemanticDecision`.
2. Мок чат-генерации:
- патчить `apps.api.routes.runs.get_brain` на фейковый brain с `LLMResponse(status="ok", text="...")`.
3. Проверка строгого парсинга:
- вызывать `core.semantic.decision.decide_semantic(..., brain=FakeBrain(...))` и проверять `SemanticDecisionError`.

## Команды проверки
- Поиск старых ограничителей:
  - `rg -n "re\.compile\(|_PATTERN|_PATTERNS|is_\w+_question|is_\w+_request|any\(phrase in|\bin normalized\b" -S core skills apps/api memory`
- Проверка semantic-модуля:
  - `rg -n "semantic_decision|SemanticDecision|prompts/semantic" -S core prompts`
- Python-тесты:
  - `python3 -m pytest -q tests/test_intent_router.py tests/test_planner.py tests/test_memory_v1.py tests/test_profile_memory.py tests/test_semantic_routing.py`
- Полный Python-ран:
  - `python3 -m pytest -q`
- Desktop проверки:
  - `npm --prefix apps/desktop run lint`
  - `npm --prefix apps/desktop run test`
  - `npm --prefix apps/desktop run build`
