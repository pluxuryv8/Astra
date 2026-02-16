#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib/address_config.sh"

if ! apply_resolved_address_env; then
  echo "Некорректная адресная конфигурация (API/Bridge)." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Не найдена .venv. Сначала запусти: ./scripts/run.sh или создай venv вручную." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

API_BASE_URL="$ASTRA_API_BASE_URL"

echo "== API health =="
if ! curl -fsS "${API_BASE_URL}/auth/status" >/dev/null; then
  echo "API недоступен по ${API_BASE_URL}. Подними API перед check.sh." >&2
  exit 1
fi

python -m ruff check .
python -m pytest
python -m pytest -q \
  tests/test_semantic_routing.py::test_semantic_failure_degrades_to_chat_instead_of_502 \
  tests/test_planner.py::test_planner_web_research_from_plan_hint \
  tests/test_reminders.py::test_reminder_scheduler_telegram_delivery_marks_sent

npm --prefix apps/desktop run lint
npm --prefix apps/desktop run build
