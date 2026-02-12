# OCR + Verify v1

## Что делает
Executor Loop v1 проверяет успех шагов не только по изменению экрана, но и по тексту на экране:
- Быстрый сигнал: изменился ли экран (hash).
- При наличии текстовых критериев — запускает OCR и проверяет `success_criteria` / `success_checks`.

Файлы:
- OCR: `core/ocr/engine.py`
- Verify: `core/executor/computer_executor.py`
- Criteria parser: `core/executor/success_criteria.py`

## OCR безопасность
Текст экрана считается конфиденциальным:
- OCR‑текст помечается как `source_type=screenshot_text`, `sensitivity=confidential`.
- Политика принудительно выбирает LOCAL и вырезает `screenshot_text` при попытке облачного маршрута.

## Как включить/выключить OCR
По умолчанию OCR включён.

ENV:
- `ASTRA_OCR_ENABLED=true|false`
- `ASTRA_OCR_LANG=eng+rus`

Также можно задать в `project.settings.executor`:
- `ocr_enabled`
- `ocr_lang`

## Success Criteria
Поддерживаются структурные проверки:
- `contains: <text>`
- `not_contains: <text>`
- `regex: <pattern>`

Пример:
```
contains: Settings
not_contains: Error
```

Если доступно поле `success_checks`, оно имеет приоритет.

## Отладка
События:
- `ocr_performed` (hash + длительность)
- `ocr_cached_hit`
- `verification_result`
- `step_waiting`

В событиях нет полного текста OCR — только хеш и длина.

## Производительность
OCR выполняется только в `verify()`:
- на каждом цикле максимум один OCR (по итоговому наблюдению)
- при повторе на том же хеше используется кэш

## Проверка зависимостей
Tesseract должен быть доступен локально.
- Проверка: `tesseract --version`
- Установка (macOS): `brew install tesseract`
