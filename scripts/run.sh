#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="foreground"
if [ "${1:-}" = "--background" ]; then
  MODE="background"
fi

# Load .env if present (not committed)
if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib/address_config.sh"

export ASTRA_AUTH_MODE="${ASTRA_AUTH_MODE:-local}"

if ! command -v node >/dev/null 2>&1; then
  echo "Нужен Node.js (node). Установи Node и повтори запуск." >&2
  exit 1
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "Нужен Rust (cargo). Установи rustup и повтори запуск." >&2
  exit 1
fi

PYTHON_BIN=""
if command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="python3.11"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "Нужен Python 3.11+ (рекомендуется 3.11)." >&2
  exit 1
fi

if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

PYTHON_VENV="$VIRTUAL_ENV/bin/python3"
if [ ! -x "$PYTHON_VENV" ]; then
  PYTHON_VENV="$VIRTUAL_ENV/bin/python"
fi
if [ ! -x "$PYTHON_VENV" ]; then
  echo "В .venv не найден python. Пересоздай .venv" >&2
  exit 1
fi

"$PYTHON_VENV" -m pip install -U pip >/dev/null
"$PYTHON_VENV" -m pip install -r apps/api/requirements.txt >/dev/null

npm --prefix apps/desktop install >/dev/null

if ! apply_resolved_address_env; then
  echo "Некорректная адресная конфигурация (API/Bridge)." >&2
  exit 1
fi

API_PORT="$ASTRA_API_PORT"
API_BASE_URL="$ASTRA_API_BASE_URL"
BRIDGE_PORT="$ASTRA_BRIDGE_PORT"
VITE_PORT=5173

if [ -z "${ASTRA_DATA_DIR:-}" ]; then
  export ASTRA_DATA_DIR="$ROOT_DIR/.astra"
fi
export VITE_ASTRA_BASE_DIR="$ROOT_DIR"
export VITE_ASTRA_DATA_DIR="$ASTRA_DATA_DIR"

LOG_DIR="${ASTRA_LOG_DIR:-.astra/logs}"
mkdir -p "$LOG_DIR"
PUBLIC_LOG_LINK="logs"

if [ -e "$PUBLIC_LOG_LINK" ] && [ ! -L "$PUBLIC_LOG_LINK" ]; then
  rm -rf "$PUBLIC_LOG_LINK"
fi
ln -sfn "$LOG_DIR" "$PUBLIC_LOG_LINK"

check_api() {
  curl -sS --max-time 2 "${API_BASE_URL}/auth/status" >/dev/null 2>&1
}

wait_for_api_health() {
  local tries="${1:-120}"
  local delay="${2:-0.25}"
  for _ in $(seq 1 "$tries"); do
    if check_api; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

wait_for_port() {
  local port="$1"
  local tries="${2:-120}"
  local delay="${3:-0.25}"
  for _ in $(seq 1 "$tries"); do
    if lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

if [ "$MODE" = "background" ]; then
  if check_api; then
    echo "API уже доступен по ${API_BASE_URL}"
  else
    nohup "$PYTHON_VENV" -m uvicorn apps.api.main:app --host 127.0.0.1 --port "$API_PORT" >"$LOG_DIR/api.log" 2>&1 &
    API_PID=$!
    echo "$API_PID" > .astra/api.pid

    if ! wait_for_api_health 120 0.25; then
      echo "API не поднялся. Проверь: $LOG_DIR/api.log" >&2
      if [ -n "${API_PID:-}" ] && kill -0 "$API_PID" >/dev/null 2>&1; then
        kill "$API_PID" >/dev/null 2>&1 || true
      fi
      exit 1
    fi
  fi

  source "$HOME/.cargo/env" >/dev/null 2>&1 || true
  nohup npm --prefix apps/desktop run tauri dev >"$LOG_DIR/tauri.log" 2>&1 &
  TAURI_PID=$!
  echo "$TAURI_PID" > .astra/tauri.pid

  if ! check_api; then
    echo "API недоступен перед запуском desktop. Проверь: $LOG_DIR/api.log" >&2
    if kill -0 "$TAURI_PID" >/dev/null 2>&1; then
      kill "$TAURI_PID" >/dev/null 2>&1 || true
    fi
    exit 1
  fi

  if ! wait_for_port "$VITE_PORT" 160 0.25; then
    echo "Vite не поднялся на порту ${VITE_PORT}. Проверь: $LOG_DIR/tauri.log" >&2
    if kill -0 "$TAURI_PID" >/dev/null 2>&1; then
      kill "$TAURI_PID" >/dev/null 2>&1 || true
    fi
    exit 1
  fi

  if ! wait_for_port "$BRIDGE_PORT" 160 0.25; then
    echo "Bridge не поднялся на порту ${BRIDGE_PORT}. Проверь: $LOG_DIR/tauri.log" >&2
    if kill -0 "$TAURI_PID" >/dev/null 2>&1; then
      kill "$TAURI_PID" >/dev/null 2>&1 || true
    fi
    exit 1
  fi

  for _ in $(seq 1 30); do
    if ! kill -0 "$TAURI_PID" >/dev/null 2>&1; then
      echo "Desktop процесс завершился сразу после старта. Проверь: $LOG_DIR/tauri.log" >&2
      exit 1
    fi
    if ! lsof -nP -iTCP:"$VITE_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "Vite перестал слушать порт ${VITE_PORT} сразу после запуска. Проверь: $LOG_DIR/tauri.log" >&2
      kill "$TAURI_PID" >/dev/null 2>&1 || true
      exit 1
    fi
    if ! lsof -nP -iTCP:"$BRIDGE_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
      echo "Bridge перестал слушать порт ${BRIDGE_PORT} сразу после запуска. Проверь: $LOG_DIR/tauri.log" >&2
      kill "$TAURI_PID" >/dev/null 2>&1 || true
      exit 1
    fi
    sleep 1
  done

  echo "Randarc-Astra запущена в фоне. API=${API_BASE_URL} Bridge=${ASTRA_BRIDGE_BASE_URL} Логи: $LOG_DIR"
  exit 0
fi

cleanup() {
  if [ -n "${API_PID:-}" ] && kill -0 "$API_PID" >/dev/null 2>&1; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if check_api; then
  echo "API уже доступен по ${API_BASE_URL}"
else
  "$PYTHON_VENV" -m uvicorn apps.api.main:app --host 127.0.0.1 --port "$API_PORT" >"$LOG_DIR/api.log" 2>&1 &
  API_PID=$!

  if ! wait_for_api_health 120 0.25; then
    echo "API не поднялся. Проверь: $LOG_DIR/api.log" >&2
    if [ -n "${API_PID:-}" ] && kill -0 "$API_PID" >/dev/null 2>&1; then
      kill "$API_PID" >/dev/null 2>&1 || true
    fi
    exit 1
  fi
fi

source "$HOME/.cargo/env" >/dev/null 2>&1 || true

npm --prefix apps/desktop run tauri dev
