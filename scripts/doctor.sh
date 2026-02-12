#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

API_PORT="${ASTRA_API_PORT:-8055}"
API_BASE="${ASTRA_API_BASE:-http://127.0.0.1:${API_PORT}/api/v1}"
BRIDGE_PORT="${ASTRA_DESKTOP_BRIDGE_PORT:-43124}"
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

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  PYTHON_BIN=""
fi

# Env presence (no values)
for var in ASTRA_API_PORT ASTRA_BASE_DIR ASTRA_DATA_DIR ASTRA_DESKTOP_BRIDGE_PORT ASTRA_VAULT_PATH ASTRA_VAULT_PASSPHRASE ASTRA_LOCAL_SECRETS_PATH OPENAI_API_KEY ASTRA_SESSION_TOKEN ASTRA_LLM_LOCAL_BASE_URL ASTRA_LLM_LOCAL_CHAT_MODEL ASTRA_LLM_LOCAL_CODE_MODEL ASTRA_LLM_CLOUD_MODEL ASTRA_CLOUD_ENABLED ASTRA_AUTO_CLOUD_ENABLED ASTRA_LLM_MAX_CONCURRENCY ASTRA_LLM_MAX_RETRIES ASTRA_LLM_BACKOFF_BASE_MS ASTRA_LLM_BUDGET_PER_RUN ASTRA_LLM_BUDGET_PER_STEP; do
  if [ -n "${!var-}" ]; then
    ok "env $var is set"
  else
    warn "env $var is not set"
  fi
done

# Ollama health + models
OLLAMA_BASE="${ASTRA_LLM_LOCAL_BASE_URL:-http://127.0.0.1:11434}"
OLLAMA_TAGS=$(curl -s --max-time 2 "${OLLAMA_BASE}/api/tags" || true)
if [ -n "$OLLAMA_TAGS" ]; then
  ok "Ollama /api/tags"
else
  fail "Ollama not reachable at ${OLLAMA_BASE} (GET /api/tags)"
fi

if [ -n "$OLLAMA_TAGS" ] && [ -n "$PYTHON_BIN" ]; then
  REQ_CHAT_MODEL="${ASTRA_LLM_LOCAL_CHAT_MODEL:-qwen2.5:3b-instruct}"
  REQ_CODE_MODEL="${ASTRA_LLM_LOCAL_CODE_MODEL:-qwen2.5-coder:3b}"
  MISSING_MODELS=$($PYTHON_BIN - <<PY
import json
data=json.loads('''$OLLAMA_TAGS''')
models={m.get('name') for m in data.get('models', [])}
missing=[]
for name in ["$REQ_CHAT_MODEL","$REQ_CODE_MODEL"]:
    if name and name not in models:
        missing.append(name)
print(",".join(missing))
PY
)
  if [ -z "$MISSING_MODELS" ]; then
    ok "Ollama models present (${REQ_CHAT_MODEL}, ${REQ_CODE_MODEL})"
  else
    fail "Ollama missing models: ${MISSING_MODELS}"
  fi
fi

# Cloud key check
CLOUD_ENABLED="${ASTRA_CLOUD_ENABLED:-true}"
if [[ "$CLOUD_ENABLED" =~ ^(0|false|no|off)$ ]]; then
  warn "Cloud disabled (ASTRA_CLOUD_ENABLED=${CLOUD_ENABLED})"
else
  if [ -n "${OPENAI_API_KEY-}" ]; then
    ok "OPENAI_API_KEY is set"
  else
    fail "OPENAI_API_KEY is not set (cloud enabled)"
  fi
fi

# Port checks
if lsof -nP -iTCP:"$API_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  ok "API port ${API_PORT} is listening"
else
  fail "API port ${API_PORT} is not listening"
fi

if lsof -nP -iTCP:"$BRIDGE_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  ok "Desktop bridge port ${BRIDGE_PORT} is listening"
else
  warn "Desktop bridge port ${BRIDGE_PORT} is not listening"
fi

# API health
AUTH_STATUS=$(curl -s -o /tmp/astra_auth_status.json -w "%{http_code}" "${API_BASE}/auth/status" || true)
if [ "$AUTH_STATUS" = "200" ]; then
  ok "GET /auth/status"
else
  fail "GET /auth/status -> HTTP ${AUTH_STATUS}"
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
if [ -n "$TOKEN" ]; then
  BOOTSTRAP_STATUS=$(curl -s -o /tmp/astra_bootstrap.json -w "%{http_code}" \
    -H "Content-Type: application/json" \
    -X POST "${API_BASE}/auth/bootstrap" \
    -d "{\"token\":\"${TOKEN}\"}" || true)
  if [ "$BOOTSTRAP_STATUS" = "200" ]; then
    ok "POST /auth/bootstrap"
    TOKEN_VALID=1
    mkdir -p .astra
    echo "$TOKEN" > "$TOKEN_FILE"
  elif [ "$BOOTSTRAP_STATUS" = "409" ]; then
    fail "POST /auth/bootstrap -> token already set; export ASTRA_SESSION_TOKEN"
  else
    fail "POST /auth/bootstrap -> HTTP ${BOOTSTRAP_STATUS}"
  fi
else
  fail "no token available for auth checks"
fi

PROJECT_ID=""
RUN_ID=""
if [ "$TOKEN_VALID" -eq 1 ]; then
  PROJECT_JSON=$(curl -s -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    -X POST "${API_BASE}/projects" \
    -d '{"name":"doctor","tags":["doctor"],"settings":{}}' || true)
  if [ -n "$PROJECT_JSON" ] && [ -n "$PYTHON_BIN" ]; then
    PROJECT_ID=$($PYTHON_BIN - <<PY
import json
try:
  data=json.loads("""$PROJECT_JSON""")
  print(data.get("id",""))
except Exception:
  print("")
PY
)
  fi
  if [ -n "$PROJECT_ID" ]; then
    ok "POST /projects"
  else
    fail "POST /projects (auth)"
  fi
fi

if [ -n "$PROJECT_ID" ] && [ "$TOKEN_VALID" -eq 1 ]; then
  RUN_JSON=$(curl -s -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" \
    -X POST "${API_BASE}/projects/${PROJECT_ID}/runs" \
    -d '{"query_text":"doctor smoke","mode":"plan_only"}' || true)
  if [ -n "$RUN_JSON" ] && [ -n "$PYTHON_BIN" ]; then
    RUN_ID=$($PYTHON_BIN - <<PY
import json
try:
  data=json.loads("""$RUN_JSON""")
  print(data.get("id",""))
except Exception:
  print("")
PY
)
  fi
  if [ -n "$RUN_ID" ]; then
    ok "POST /projects/{id}/runs"
  else
    fail "POST /projects/{id}/runs"
  fi
fi

if [ -n "$RUN_ID" ] && [ "$TOKEN_VALID" -eq 1 ]; then
  SSE_OUT=$(curl -s --max-time 3 "${API_BASE}/runs/${RUN_ID}/events?token=${TOKEN}&once=1" || true)
  if echo "$SSE_OUT" | grep -q "^event:"; then
    ok "GET /runs/{id}/events (SSE)"
  else
    fail "GET /runs/{id}/events (SSE)"
  fi
fi

if lsof -nP -iTCP:5173 -sTCP:LISTEN -t >/dev/null 2>&1; then
  ok "Vite dev server (5173) is listening"
else
  warn "Vite dev server (5173) is not listening"
fi

if [ "$FAILS" -gt 0 ]; then
  echo "\nDoctor: FAIL (${FAILS})"
  exit 1
fi

echo "\nDoctor: OK"
exit 0
