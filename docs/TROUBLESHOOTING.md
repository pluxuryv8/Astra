# Troubleshooting

Документ сфокусирован на двух главных симптомах качества:

- мусорный/грязный/нерелевантный ответ;
- слишком долгий ответ.

## 1) Симптом: мусорный или нерелевантный ответ

### Что проверить первым

1. `runtime_metrics` у run:

```bash
API=http://127.0.0.1:8055/api/v1
RUN_ID=<run_id>

curl -sS "$API/runs/$RUN_ID" | jq '.meta.runtime_metrics'
```

2. Последние события `chat_response_generated` и `llm_request_failed`:

```bash
curl -sS "$API/runs/$RUN_ID/events/download" \
  | jq -c 'select(.type=="chat_response_generated" or .type=="llm_request_failed")'
```

### Как читать `runtime_metrics`

- `fallback_path=semantic_resilience`:
  semantic-слой упал, ответ уже деградированный.
- `fallback_path=chat_llm_fallback`:
  chat LLM не дала нормальный результат, вернулся fallback-текст.
- `fallback_path=chat_web_research` или `chat_llm_fallback_web_research`:
  включился auto web research; проверяй глубину и лимиты web-поиска.
- `auto_web_research_triggered=true` + `auto_web_research_reason`:
  видно, почему авто-поиск сработал (`uncertain_response`, `off_topic`, `ru_language_mismatch`, `llm_error:*`, `empty_response`).

### Частые причины и фиксы

- LLM недоступна/нестабильна:

```bash
curl -sS http://127.0.0.1:11434/api/tags
```

- Слишком агрессивный/долгий web research:
  уменьшить `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_ROUNDS`, `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_PAGES`, `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_SOURCES`.

- Маршрутизация неудачно выбрала path:
  временно включить QA-режим для диагностики:

```bash
export ASTRA_QA_MODE=true
```

## 2) Симптом: ответ слишком долгий

### Быстрая диагностика

1. Смотри общую latency в runtime метриках:

```bash
curl -sS "$API/runs/$RUN_ID" | jq '.meta.runtime_metrics'
```

2. Смотри latency конкретного финального события:

```bash
curl -sS "$API/runs/$RUN_ID/events/download" \
  | jq -c 'select(.type=="chat_response_generated") | .payload | {provider, latency_ms, runtime_metrics}'
```

### Интерпретация

- `response_latency_ms` высокая и `auto_web_research_triggered=true`:
  тормозит web research, это ожидаемо.
- `response_latency_ms` высокая и `fallback_path=chat_llm_fallback`:
  были проблемы LLM + fallback.
- `decision_latency_ms` непропорционально высокая:
  нужно проверить нагрузку semantic/LLM path.

### Что крутить сначала

1. Уменьшить web research лимиты:
- `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_ROUNDS`
- `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_PAGES`
- `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_SOURCES`

2. Проверить таймауты и модельный роутер:
- `ASTRA_LLM_LOCAL_TIMEOUT_S`
- `ASTRA_LLM_CHAT_TIER_TIMEOUT_S`
- `ASTRA_LLM_MAX_CONCURRENCY`

3. Проверить fast path:
- `ASTRA_CHAT_FAST_PATH_ENABLED=true`
- `ASTRA_CHAT_FAST_PATH_MAX_CHARS` (не занижать слишком сильно)

## 3) Инфра-проблемы, которые маскируются под “плохой ответ”

### `Ollama not reachable`

```bash
curl -sS http://127.0.0.1:11434/api/tags
./scripts/models.sh verify
```

### `401` / `invalid_token`

```bash
curl -i http://127.0.0.1:8055/api/v1/auth/status
```

### SSE не стримит события

```bash
curl -N "http://127.0.0.1:8055/api/v1/runs/$RUN_ID/events?once=1"
```

## 4) Минимальный набор команд диагностики

```bash
./scripts/astra status
./scripts/doctor.sh prereq
./scripts/doctor.sh runtime
./scripts/astra logs api
./scripts/astra logs desktop
```
