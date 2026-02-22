# Configuration (Quality Controls Only)

Этот файл содержит только переменные окружения, которые напрямую влияют на качество ответа, стабильность и latency.

## 1) Chat generation (`apps/api/routes/runs.py`)

| Variable | Default | Effect |
|---|---:|---|
| `ASTRA_LLM_CHAT_TEMPERATURE` | `0.35` | Креативность/вариативность chat-ответа (ограничивается в диапазон `0.1..1.0`). |
| `ASTRA_LLM_CHAT_TOP_P` | `0.9` | Nucleus sampling для chat-ответа (ограничивается `0.0..1.0`). |
| `ASTRA_LLM_CHAT_REPEAT_PENALTY` | `1.15` | Снижение повторов в тексте (минимум `1.0`). |
| `ASTRA_LLM_OLLAMA_NUM_PREDICT` | `256` | Максимум токенов ответа для chat-path (ограничивается `64..2048`). |
| `ASTRA_OWNER_DIRECT_MODE` | `true` | Режим системного промпта для owner-ответов. |

## 2) Intent и быстрый путь (`apps/api/routes/runs.py`, `core/planner.py`)

| Variable | Default | Effect |
|---|---:|---|
| `ASTRA_CHAT_FAST_PATH_ENABLED` | `true` | Включает fast chat-path без полного semantic roundtrip для коротких сообщений. |
| `ASTRA_CHAT_FAST_PATH_MAX_CHARS` | `220` | Лимит длины запроса для fast path (ограничивается `60..600`). |
| `ASTRA_QA_MODE` | `false` | Принудительный QA-режим (выключает fast path и делает поведение более детерминированным). |
| `ASTRA_LEGACY_DETECTORS` | `false` | Включает legacy-детекторы в planner (может влиять на route/plan поведение). |

## 3) Auto web research (`apps/api/routes/runs.py`)

| Variable | Default | Effect |
|---|---:|---|
| `ASTRA_CHAT_AUTO_WEB_RESEARCH_ENABLED` | `true` | Включает авто-переход в web research при uncertain/off-topic/ошибках LLM. |
| `ASTRA_CHAT_AUTO_WEB_RESEARCH_DEPTH` | `brief` | Глубина web research: `brief`, `normal`, `deep`. |
| `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_ROUNDS` | `2` | Максимум раундов поиска (ограничивается `1..4`). |
| `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_SOURCES` | `6` | Максимум источников в auto-режиме (ограничивается `1..16`). |
| `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_PAGES` | `4` | Максимум страниц для fetch (ограничивается `1..12`). |

## 4) LLM router и устойчивость (`core/brain/router.py`)

| Variable | Default | Effect |
|---|---:|---|
| `ASTRA_LLM_LOCAL_BASE_URL` | `http://127.0.0.1:11434` | URL Ollama/local LLM endpoint. |
| `ASTRA_LLM_LOCAL_CHAT_MODEL` | `llama2-uncensored:7b` | Базовая chat-модель. |
| `ASTRA_LLM_LOCAL_CHAT_MODEL_FAST` | `llama2-uncensored:7b` | Fast-tier chat-модель. |
| `ASTRA_LLM_LOCAL_CHAT_MODEL_COMPLEX` | `wizardlm-uncensored:13b` | Complex-tier chat-модель. |
| `ASTRA_LLM_LOCAL_TIMEOUT_S` | `30` | Таймаут запроса к локальной LLM. |
| `ASTRA_LLM_OLLAMA_NUM_CTX` | `4096` | Контекстное окно для запроса к Ollama. |
| `ASTRA_LLM_OLLAMA_NUM_PREDICT` | `256` | Базовое ограничение длины генерации на уровне роутера. |
| `ASTRA_LLM_FAST_QUERY_MAX_CHARS` | `120` | Порог символов для fast-tier маршрутизации. |
| `ASTRA_LLM_FAST_QUERY_MAX_WORDS` | `18` | Порог слов для fast-tier маршрутизации. |
| `ASTRA_LLM_COMPLEX_QUERY_MIN_CHARS` | `260` | Порог символов для complex-tier маршрутизации. |
| `ASTRA_LLM_COMPLEX_QUERY_MIN_WORDS` | `45` | Порог слов для complex-tier маршрутизации. |
| `ASTRA_LLM_MAX_CONCURRENCY` | `1` | Максимум одновременных LLM-вызовов (стабильность vs throughput). |
| `ASTRA_LLM_CHAT_PRIORITY_EXTRA_SLOTS` | `1` | Резерв слотов под chat-запросы при загрузке. |
| `ASTRA_LLM_CHAT_TIER_TIMEOUT_S` | `20` | Таймаут fast/complex-tier до fallback на base chat model. |
| `ASTRA_LLM_BUDGET_PER_RUN` | `none` | Лимит LLM-вызовов на run. |
| `ASTRA_LLM_BUDGET_PER_STEP` | `none` | Лимит LLM-вызовов на step. |

## 5) Практический baseline (качество сначала)

Рекомендуемый старт для твоего текущего фокуса на качестве:

```env
ASTRA_CHAT_FAST_PATH_ENABLED=true
ASTRA_CHAT_FAST_PATH_MAX_CHARS=220
ASTRA_CHAT_AUTO_WEB_RESEARCH_ENABLED=true
ASTRA_CHAT_AUTO_WEB_RESEARCH_DEPTH=brief
ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_ROUNDS=2
ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_SOURCES=6
ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_PAGES=4
ASTRA_LLM_CHAT_TEMPERATURE=0.35
ASTRA_LLM_CHAT_TOP_P=0.9
ASTRA_LLM_CHAT_REPEAT_PENALTY=1.15
ASTRA_LLM_LOCAL_TIMEOUT_S=30
ASTRA_LLM_MAX_CONCURRENCY=1
ASTRA_LLM_CHAT_TIER_TIMEOUT_S=20
```

Если при этом latency слишком высокая, сначала уменьшай `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_ROUNDS` и `ASTRA_CHAT_AUTO_WEB_RESEARCH_MAX_PAGES`, а не температуру/стиль.
