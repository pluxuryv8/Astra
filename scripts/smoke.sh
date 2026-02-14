#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

./scripts/astra dev

PYTHON_BIN=""
if [ -x ".venv/bin/python3" ]; then
  PYTHON_BIN=".venv/bin/python3"
elif [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if [ -z "$PYTHON_BIN" ]; then
  echo "FAIL: python not found" >&2
  exit 1
fi

"$PYTHON_BIN" scripts/run_smoke.py "$@"
