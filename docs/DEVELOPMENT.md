# Development Workflow

## Python env

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements-dev.txt
```

`requirements-dev.txt` now includes runtime API deps via `-r apps/api/requirements.txt`, so one install command is enough for local tests/dev.

## Local run

```bash
./scripts/astra dev
```

Sources: `scripts/astra:266`, `scripts/astra:148`, `scripts/run.sh:128`, `scripts/run.sh:142`.

## Stop and logs

```bash
./scripts/astra stop
./scripts/astra logs
./scripts/astra logs api
./scripts/astra logs desktop
```

Sources: `scripts/astra:270`, `scripts/astra:276`, `scripts/astra:245`, `scripts/astra:248`.

## Tests

Fast local check (lighter CPU):

```bash
pytest -q --ignore=tests/test_smoke.py --ignore=tests/test_contracts.py
```

Targeted regressions:

```bash
pytest -q tests/test_brain_regressions.py
```

Full suite:

```bash
pytest -q
```

## Quality gate

Базовый gate для quality/latency (Phase 1):

1. Intent gate

```bash
PYTHONPATH=. pytest -q tests/test_intent_router.py tests/test_semantic_routing.py
```

Критерий: все тесты зелёные (`25 passed` в текущем baseline).

2. Brain quality gate

```bash
PYTHONPATH=. pytest -q tests/test_brain_regressions.py tests/test_golden_complex_chat_cases.py
```

Критерий: нет новых падений по регрессиям и golden-кейсам.  
Допускается только известный `xfail` по planner default-path (до отдельного фикса).

3. Chat latency gate (p50/p95 report)

```bash
PYTHONPATH=. pytest -q -s tests/test_latency_chat_path.py
```

Критерий: тест печатает p50/p95 и остаётся в порогах (по умолчанию):

- `short p95 <= 700ms`
- `medium p95 <= 950ms`
- `complex p95 <= 1400ms`

Пороги можно переопределить через:

- `ASTRA_TEST_CHAT_LATENCY_SAMPLES`
- `ASTRA_TEST_CHAT_LATENCY_SHORT_P95_MS`
- `ASTRA_TEST_CHAT_LATENCY_MEDIUM_P95_MS`
- `ASTRA_TEST_CHAT_LATENCY_COMPLEX_P95_MS`

4. Full suite gate

```bash
pytest -q
```

Критерий: без новых падений относительно текущего baseline.

Дополнительный gate для desktop/infra:

```bash
npm --prefix apps/desktop run test
npm --prefix apps/desktop run lint
./scripts/doctor.sh prereq
./scripts/doctor.sh runtime
```

Sources: `apps/desktop/package.json:11`, `apps/desktop/package.json:12`, `apps/desktop/package.json:13`, `scripts/doctor.sh:12`.

## Useful scripts

- `./scripts/check.sh` — базовые проверки (`scripts/check.sh:1`).
- `./scripts/smoke.sh` — smoke flow (`scripts/smoke.sh:1`).
- `./scripts/models.sh install|verify|clean` — модели Ollama (`scripts/models.sh:1`).
- `python scripts/diag_addresses.py` — диагностика адресов/env/token (`scripts/diag_addresses.py:1`).

## Notes

- Desktop frontend требует явные `VITE_ASTRA_API_BASE_URL` и `VITE_ASTRA_BRIDGE_BASE_URL` (`apps/desktop/src/shared/api/config.ts:47`, `apps/desktop/src/shared/api/config.ts:55`).
- Startup scripts синхронизируют эти значения из `ASTRA_*` (`scripts/lib/address_config.sh:155`, `scripts/lib/address_config.sh:156`).
