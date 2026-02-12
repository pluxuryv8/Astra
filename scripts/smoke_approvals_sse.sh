#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

API_PORT="${ASTRA_API_PORT:-8055}"
API_BASE="${ASTRA_API_BASE:-http://127.0.0.1:${API_PORT}/api/v1}"
TOKEN_FILE=".astra/doctor.token"

ok() { echo "OK  $*"; }
warn() { echo "WARN $*"; }
fail() { echo "FAIL $*"; exit 1; }

if ! command -v curl >/dev/null 2>&1; then
  fail "curl not found"
fi

TOKEN="${ASTRA_SESSION_TOKEN-}"
TOKEN_SOURCE="env"
if [ -z "$TOKEN" ] && [ -f "$TOKEN_FILE" ]; then
  TOKEN=$(cat "$TOKEN_FILE" 2>/dev/null || true)
  TOKEN_SOURCE="file"
fi

HTTP_STATUS=$(curl -s -o /tmp/astra_smoke_auth.json -w "%{http_code}" "${API_BASE}/auth/status" || true)
if [ "$HTTP_STATUS" != "200" ]; then
  fail "API auth status failed (HTTP ${HTTP_STATUS})"
fi
ok "GET /auth/status"

if [ -z "$TOKEN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    TOKEN=$(python3 - <<'PY'
import secrets
print(secrets.token_hex(16))
PY
)
  elif command -v openssl >/dev/null 2>&1; then
    TOKEN=$(openssl rand -hex 16)
  else
    fail "No token and no generator available"
  fi

  BOOTSTRAP_STATUS=$(curl -s -o /tmp/astra_smoke_bootstrap.json -w "%{http_code}" \
    -H "Content-Type: application/json" \
    -X POST "${API_BASE}/auth/bootstrap" \
    -d "{\"token\":\"${TOKEN}\"}" || true)
  if [ "$BOOTSTRAP_STATUS" != "200" ]; then
    fail "POST /auth/bootstrap -> HTTP ${BOOTSTRAP_STATUS} (set ASTRA_SESSION_TOKEN if already set)"
  fi
  ok "POST /auth/bootstrap"
else
  ok "Using token from ${TOKEN_SOURCE}"
  PROJECT_PROBE=$(curl -s -o /tmp/astra_smoke_probe.json -w "%{http_code}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -X POST "${API_BASE}/projects" \
    -d '{"name":"smoke-probe","tags":["smoke"],"settings":{}}' || true)
  if [ "$PROJECT_PROBE" = "401" ]; then
    fail "Token rejected (401). Set ASTRA_SESSION_TOKEN to the active token or re-bootstrap."
  fi
fi

PROJECT_JSON=$(curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -X POST "${API_BASE}/projects" \
  -d '{"name":"smoke-approvals","tags":["smoke"],"settings":{}}' || true)

PROJECT_ID=$(python3 - <<PY
import json
try:
  data=json.loads('''$PROJECT_JSON''')
  print(data.get('id',''))
except Exception:
  print('')
PY
)
[ -n "$PROJECT_ID" ] || fail "POST /projects failed"
ok "POST /projects"

RUN_JSON=$(curl -s \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -X POST "${API_BASE}/projects/${PROJECT_ID}/runs" \
  -d '{"query_text":"Открой браузер и отправь тестовое сообщение (smoke)","mode":"execute_confirm"}' || true)

RUN_ID=$(python3 - <<PY
import json
try:
  data=json.loads('''$RUN_JSON''')
  run=data.get('run') or {}
  print(run.get('id',''))
except Exception:
  print('')
PY
)
[ -n "$RUN_ID" ] || fail "POST /projects/{id}/runs failed"
ok "POST /projects/{id}/runs"

START_STATUS=$(curl -s -o /tmp/astra_smoke_start.json -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -X POST "${API_BASE}/runs/${RUN_ID}/start" || true)
if [ "$START_STATUS" != "200" ]; then
  fail "POST /runs/{id}/start -> HTTP ${START_STATUS}"
fi
ok "POST /runs/{id}/start"

APPROVAL_ID=""
for _ in {1..20}; do
  APPROVALS_JSON=$(curl -s -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/runs/${RUN_ID}/approvals" || true)
  APPROVAL_ID=$(python3 - <<PY
import json
try:
  data=json.loads('''$APPROVALS_JSON''')
  print(data[0]['id'] if data else '')
except Exception:
  print('')
PY
)
  if [ -n "$APPROVAL_ID" ]; then
    break
  fi
  sleep 0.2
  done

[ -n "$APPROVAL_ID" ] || fail "Approval not created"
ok "Approval created: ${APPROVAL_ID}"

SSE_OUT=$(curl -sN -H "Authorization: Bearer ${TOKEN}" "${API_BASE}/runs/${RUN_ID}/events?once=1" || true)
if echo "$SSE_OUT" | grep -q "approval_requested"; then
  ok "SSE contains approval_requested"
else
  warn "SSE did not include approval_requested (check events output)"
fi

REJECT_STATUS=$(curl -s -o /tmp/astra_smoke_reject.json -w "%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -X POST "${API_BASE}/approvals/${APPROVAL_ID}/reject" || true)
if [ "$REJECT_STATUS" != "200" ]; then
  warn "POST /approvals/{id}/reject -> HTTP ${REJECT_STATUS}"
else
  ok "POST /approvals/{id}/reject"
fi

echo "Smoke: OK"
