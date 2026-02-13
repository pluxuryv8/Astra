# Local LLM Debug (Ollama)

## Где лежат артефакты
- `artifacts/local_llm_failures/`

Каждый файл содержит:
- `request_payload` — финальный JSON, отправленный в `POST /api/chat`
- `response_status` и `response_text` — то, что вернул Ollama
- `run_id`, `step_id`, `purpose`, `model`

Данные в артефактах:
- **маскированы** (секреты заменяются на `[REDACTED]`)
- **обрезаны** до 5000 символов на строку, чтобы логи были безопасными

## Как реплицировать запрос
```bash
python3 scripts/replicate_ollama_request.py artifacts/local_llm_failures/<file>.json
```

Команда повторно отправит payload в `POST /api/chat` и выведет статус и ответ.

## Типовые причины 4xx/5xx
- `invalid JSON schema in format`  
  Причина: Ollama ждёт **чистый JSON Schema**, а не wrapper вида `{ "name": "...", "schema": {...} }`.
- Слишком большой prompt  
  Признаки: ошибки 413/500 при больших payloads.
- Несовместимые поля  
  `images`, `tools`, `options` могут быть не поддержаны конкретной моделью.

## Что делать
1) Повторить запрос через `replicate_ollama_request.py`.
2) Упростить payload (без `format/tools/options`) и проверить.
3) Перезапустить Ollama:
   - `ollama serve` (если нужно вручную)
4) Проверить базовую живость:
```bash
curl -s http://127.0.0.1:11434/api/tags
curl -s -X POST http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5:3b-instruct","messages":[{"role":"user","content":"hi"}],"stream":false}'
```

Если базовый `curl` работает, а payload из артефакта падает — проблема в формате запроса (см. выше).
