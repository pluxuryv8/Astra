#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck disable=SC1091
source "$ROOT_DIR/scripts/lib/address_config.sh"

MODE="${1:-runtime}"
if [[ "$MODE" != "prereq" && "$MODE" != "runtime" ]]; then
  echo "Usage: $0 [prereq|runtime]" >&2
  exit 1
fi

if ! apply_resolved_address_env; then
  echo "FAIL invalid address configuration (API/Bridge)" >&2
  exit 1
fi

API_PORT="$ASTRA_API_PORT"
API_BASE_URL="$ASTRA_API_BASE_URL"
BRIDGE_PORT="$ASTRA_BRIDGE_PORT"
BRIDGE_BASE_URL="$ASTRA_BRIDGE_BASE_URL"
TOKEN_FILE=".astra/doctor.token"

FAILS=0

ok() { echo "OK  $*"; }
warn() { echo "WARN $*"; }
fail() { echo "FAIL $*"; FAILS=$((FAILS+1)); }

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "missing command: $1"
    return 1
  fi
  return 0
}

need_cmd curl || true

API_PYTHON=""
if [ -x ".venv/bin/python3" ]; then
  API_PYTHON=".venv/bin/python3"
elif [ -x ".venv/bin/python" ]; then
  API_PYTHON=".venv/bin/python"
fi

PYTHON_BIN="$API_PYTHON"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    PYTHON_BIN=""
  fi
fi

check_prereq() {
  echo "Doctor mode: prereq"
  ok "resolved API base URL: ${API_BASE_URL}"
  ok "resolved Bridge base URL: ${BRIDGE_BASE_URL}"

  # Env presence (no values)
  CLOUD_ENABLED="${ASTRA_CLOUD_ENABLED:-false}"
  for var in ASTRA_API_BASE_URL ASTRA_API_PORT ASTRA_BRIDGE_BASE_URL ASTRA_BRIDGE_PORT ASTRA_DESKTOP_BRIDGE_PORT ASTRA_BASE_DIR ASTRA_DATA_DIR ASTRA_VAULT_PATH ASTRA_VAULT_PASSPHRASE ASTRA_LOCAL_SECRETS_PATH OPENAI_API_KEY ASTRA_SESSION_TOKEN ASTRA_LLM_LOCAL_BASE_URL ASTRA_LLM_LOCAL_CHAT_MODEL ASTRA_LLM_LOCAL_CHAT_MODEL_FAST ASTRA_LLM_LOCAL_CHAT_MODEL_COMPLEX ASTRA_LLM_LOCAL_CODE_MODEL ASTRA_LLM_CLOUD_MODEL ASTRA_CLOUD_ENABLED ASTRA_AUTO_CLOUD_ENABLED ASTRA_LLM_MAX_CONCURRENCY ASTRA_LLM_MAX_RETRIES ASTRA_LLM_BACKOFF_BASE_MS ASTRA_LLM_BUDGET_PER_RUN ASTRA_LLM_BUDGET_PER_STEP ASTRA_REMINDERS_ENABLED ASTRA_TIMEZONE TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
    if [ "$var" = "OPENAI_API_KEY" ] && [[ "$CLOUD_ENABLED" =~ ^(0|false|no|off)$ ]]; then
      continue
    fi
    if [ -n "${!var-}" ]; then
      ok "env $var is set"
    else
      warn "env $var is not set"
    fi
  done

  # OCR checks (tesseract + python deps)
  if command -v tesseract >/dev/null 2>&1; then
    ok "OCR engine tesseract"
  else
    fail "OCR engine tesseract not found (install: brew install tesseract)"
  fi

  if [ -n "$PYTHON_BIN" ]; then
    OCR_DEPS=$($PYTHON_BIN - <<'PY'
try:
    import pytesseract  # noqa: F401
    from PIL import Image  # noqa: F401
    print("ok")
except Exception:
    print("missing")
PY
)
    if [ "$OCR_DEPS" = "ok" ]; then
      ok "OCR python deps (pytesseract, pillow)"
    else
      fail "OCR python deps missing (pip install pytesseract pillow)"
    fi
  else
    warn "OCR python deps check skipped (python not found)"
  fi

  # Ollama health + models
  OLLAMA_BASE="${ASTRA_LLM_LOCAL_BASE_URL:-http://127.0.0.1:11434}"
  OLLAMA_TAGS=$(curl -s --max-time 2 "${OLLAMA_BASE}/api/tags" || true)
  if [ -n "$OLLAMA_TAGS" ]; then
    ok "Ollama /api/tags"
  else
    fail "Ollama not reachable at ${OLLAMA_BASE} (GET /api/tags)"
  fi

  if [ -n "$OLLAMA_TAGS" ] && [ -n "$PYTHON_BIN" ]; then
    REQ_CHAT_MODEL="${ASTRA_LLM_LOCAL_CHAT_MODEL:-llama2-uncensored:7b}"
    REQ_CHAT_FAST_MODEL="${ASTRA_LLM_LOCAL_CHAT_MODEL_FAST:-llama2-uncensored:7b}"
    REQ_CHAT_COMPLEX_MODEL="${ASTRA_LLM_LOCAL_CHAT_MODEL_COMPLEX:-wizardlm-uncensored:13b}"
    REQ_CODE_MODEL="${ASTRA_LLM_LOCAL_CODE_MODEL:-deepseek-coder-v2:16b-lite-instruct-q8_0}"
    MISSING_MODELS=$($PYTHON_BIN - <<PY
import json
try:
    data=json.loads('''$OLLAMA_TAGS''')
except Exception:
    data={}
models={m.get('name') for m in data.get('models', []) if isinstance(m, dict)}
missing=[]
def normalize(name):
    return name if ":" in name else f"{name}:latest"
for name in ["$REQ_CHAT_MODEL","$REQ_CHAT_FAST_MODEL","$REQ_CHAT_COMPLEX_MODEL","$REQ_CODE_MODEL"]:
    if name and name not in models and normalize(name) not in models:
        missing.append(name)
print(",".join(missing))
PY
)
    if [ -z "$MISSING_MODELS" ]; then
      ok "Ollama models present (${REQ_CHAT_MODEL}, ${REQ_CHAT_FAST_MODEL}, ${REQ_CHAT_COMPLEX_MODEL}, ${REQ_CODE_MODEL})"
    else
      fail "Ollama missing models: ${MISSING_MODELS}. Install: ./scripts/models.sh install"
    fi
  fi

  if [ -n "$OLLAMA_TAGS" ] && [ -n "$PYTHON_BIN" ]; then
    CHAT_MODEL="${ASTRA_LLM_LOCAL_CHAT_MODEL:-llama2-uncensored:7b}"
    CHAT_MODEL_TEST="$CHAT_MODEL"
    if [[ "$CHAT_MODEL_TEST" != *:* ]]; then
      CHAT_MODEL_TEST="${CHAT_MODEL_TEST}:latest"
    fi
    CHAT_PAYLOAD=$($PYTHON_BIN - <<PY
import json
print(json.dumps({
  "model": "${CHAT_MODEL_TEST}",
  "messages": [{"role": "user", "content": "hi"}],
  "stream": False
}))
PY
)
    CHAT_TMP=$(mktemp)
    CHAT_STATUS=$(curl -s -o "$CHAT_TMP" -w "%{http_code}" --max-time 5 \
      -H "Content-Type: application/json" \
      -d "$CHAT_PAYLOAD" \
      "${OLLAMA_BASE}/api/chat" || true)
    if [ "$CHAT_STATUS" = "200" ]; then
      ok "Local LLM chat ok (${CHAT_MODEL})"
    else
      warn "Local LLM chat probe failed (${CHAT_MODEL}) status=${CHAT_STATUS}. Check ${OLLAMA_BASE}/api/chat"
    fi
    rm -f "$CHAT_TMP" >/dev/null 2>&1 || true
  fi

  # Cloud key check
  if [[ "$CLOUD_ENABLED" =~ ^(0|false|no|off)$ ]]; then
    ok "Cloud disabled (ASTRA_CLOUD_ENABLED=${CLOUD_ENABLED})"
  else
    if [ -n "${OPENAI_API_KEY-}" ]; then
      ok "OPENAI_API_KEY is set"
    else
      warn "OPENAI_API_KEY is not set (cloud enabled). Set key or disable cloud: ASTRA_CLOUD_ENABLED=false"
    fi
  fi

  # Reminders + Telegram
  REMINDERS_ENABLED="${ASTRA_REMINDERS_ENABLED:-true}"
  if [[ "$REMINDERS_ENABLED" =~ ^(0|false|no|off)$ ]]; then
    warn "Reminders disabled (ASTRA_REMINDERS_ENABLED=${REMINDERS_ENABLED})"
  else
    ok "Reminders enabled"
  fi

  if [ -n "${ASTRA_TIMEZONE-}" ]; then
    ok "ASTRA_TIMEZONE is set"
  else
    warn "ASTRA_TIMEZONE is not set (default: system timezone)"
  fi

  if [ -n "${TELEGRAM_BOT_TOKEN-}" ] && [ -n "${TELEGRAM_CHAT_ID-}" ]; then
    ok "Telegram delivery enabled"
  else
    warn "Telegram delivery disabled (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set)"
  fi
}

check_runtime() {
  echo "Doctor mode: runtime"
  ok "resolved API base URL: ${API_BASE_URL}"
  ok "resolved Bridge base URL: ${BRIDGE_BASE_URL}"

  API_RUNNING=0
  if lsof -nP -iTCP:"$API_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    ok "API port ${API_PORT} is listening"
    API_RUNNING=1
  else
    fail "Not running: API port ${API_PORT}. Start: ./scripts/run.sh OR source .venv/bin/activate && python -m uvicorn apps.api.main:app --host 127.0.0.1 --port ${API_PORT}"
  fi

  if lsof -nP -iTCP:"$BRIDGE_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    ok "Desktop bridge port ${BRIDGE_PORT} is listening"
  else
    fail "Not running: Desktop bridge port ${BRIDGE_PORT}. Start: npm --prefix apps/desktop run tauri dev"
  fi

  if lsof -nP -iTCP:5173 -sTCP:LISTEN -t >/dev/null 2>&1; then
    ok "Vite dev server (5173) is listening"
  else
    fail "Not running: Vite dev server (5173). Start: npm --prefix apps/desktop run tauri dev"
  fi

  if [ "$API_RUNNING" -eq 1 ]; then
    # API health
    AUTH_STATUS=$(curl -s -o /tmp/astra_auth_status.json -w "%{http_code}" "${API_BASE_URL}/auth/status" || true)
    if [ "$AUTH_STATUS" = "200" ]; then
      ok "GET /auth/status"
    else
      fail "GET /auth/status -> HTTP ${AUTH_STATUS}"
    fi

    TOKEN_REQUIRED="unknown"
    if [ "$AUTH_STATUS" = "200" ] && [ -n "$PYTHON_BIN" ]; then
      TOKEN_REQUIRED=$($PYTHON_BIN - <<'PY'
import json
from pathlib import Path

path = Path("/tmp/astra_auth_status.json")
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("unknown")
else:
    value = payload.get("token_required")
    if value is True:
        print("true")
    elif value is False:
        print("false")
    else:
        print("unknown")
PY
)
    fi

    TOKEN="${ASTRA_SESSION_TOKEN-}"
    if [ -z "$TOKEN" ] && [ -f "$TOKEN_FILE" ]; then
      TOKEN=$(cat "$TOKEN_FILE" 2>/dev/null || true)
      if [ -n "$TOKEN" ]; then
        ok "loaded token from ${TOKEN_FILE}"
      fi
    fi

    if [ -z "$TOKEN" ]; then
      if [ -n "$PYTHON_BIN" ]; then
        TOKEN=$($PYTHON_BIN - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
)
      elif command -v openssl >/dev/null 2>&1; then
        TOKEN=$(openssl rand -hex 16)
      else
        TOKEN=""
      fi
    fi

    TOKEN_VALID=0
    if [ "$TOKEN_REQUIRED" = "false" ]; then
      TOKEN_VALID=1
      ok "token bootstrap skipped (token_required=false)"
    elif [ -n "$TOKEN" ]; then
      BOOTSTRAP_STATUS=$(curl -s -o /tmp/astra_bootstrap.json -w "%{http_code}" \
        -H "Content-Type: application/json" \
        -X POST "${API_BASE_URL}/auth/bootstrap" \
        -d "{\"token\":\"${TOKEN}\"}" || true)
      if [ "$BOOTSTRAP_STATUS" = "200" ]; then
        ok "POST /auth/bootstrap"
        TOKEN_VALID=1
        mkdir -p .astra
        echo "$TOKEN" > "$TOKEN_FILE"
      elif [ "$BOOTSTRAP_STATUS" = "409" ]; then
        warn "POST /auth/bootstrap -> token already set; trying existing token"
        TOKEN_VALID=1
      else
        fail "POST /auth/bootstrap -> HTTP ${BOOTSTRAP_STATUS}"
      fi
    else
      fail "no token available for auth checks"
    fi

    PROJECT_ID=""
    RUN_ID=""
    AUTH_HEADERS=()
    if [ -n "$TOKEN" ]; then
      AUTH_HEADERS=(-H "Authorization: Bearer ${TOKEN}")
    fi
    if [ "$TOKEN_VALID" -eq 1 ]; then
      PROJECT_JSON=$(curl -s "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
        -X POST "${API_BASE_URL}/projects" \
        -d '{"name":"doctor","tags":["doctor"],"settings":{}}' || true)
      if [ -n "$PROJECT_JSON" ] && [ -n "$PYTHON_BIN" ]; then
        PROJECT_ID=$("$PYTHON_BIN" -c 'import json,sys
raw = sys.stdin.read()
try:
  data = json.loads(raw)
  print(data.get("id","") if isinstance(data, dict) else "")
except Exception:
  print("")' <<<"$PROJECT_JSON")
      fi
      if [ -n "$PROJECT_ID" ]; then
        ok "POST /projects"
      else
        fail "POST /projects (auth)"
      fi
    fi

    if [ -n "$PROJECT_ID" ] && [ "$TOKEN_VALID" -eq 1 ]; then
      RUN_JSON=$(curl -s "${AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
        -X POST "${API_BASE_URL}/projects/${PROJECT_ID}/runs" \
        -d '{"query_text":"doctor smoke","mode":"plan_only"}' || true)
      if [ -n "$RUN_JSON" ] && [ -n "$PYTHON_BIN" ]; then
        RUN_ID=$("$PYTHON_BIN" -c 'import json,sys
raw = sys.stdin.read()
try:
  data = json.loads(raw)
  if isinstance(data, dict):
    run = data.get("run") or {}
    print(run.get("id") or data.get("id") or "")
  else:
    print("")
except Exception:
  print("")' <<<"$RUN_JSON")
      fi
      if [ -n "$RUN_ID" ]; then
        ok "POST /projects/{id}/runs"
      else
        fail "POST /projects/{id}/runs"
      fi
    fi

    if [ -n "$RUN_ID" ] && [ "$TOKEN_VALID" -eq 1 ]; then
      SSE_URL="${API_BASE_URL}/runs/${RUN_ID}/events?once=1"
      if [ -n "$TOKEN" ]; then
        SSE_URL="${SSE_URL}&token=${TOKEN}"
      fi
      SSE_OUT=$(curl -s --max-time 3 "${SSE_URL}" || true)
      if echo "$SSE_OUT" | grep -q "^event:"; then
        ok "GET /runs/{id}/events (SSE)"
      else
        fail "GET /runs/{id}/events (SSE)"
      fi
    fi
  else
    warn "API health checks skipped (API not running)"
  fi
}

if [ "$MODE" = "prereq" ]; then
  check_prereq
else
  check_runtime
fi

if [ "$FAILS" -gt 0 ]; then
  echo "\nDoctor: FAIL (${FAILS})"
  exit 1
fi

echo "\nDoctor: OK"
exit 0
