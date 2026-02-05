#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

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
python -m pip install -U pip >/dev/null
python -m pip install -r apps/api/requirements.txt >/dev/null

read -s -p "Пароль хранилища (ASTRA_VAULT_PASSPHRASE): " passphrase
printf "\n"
read -s -p "OpenAI API key: " api_key
printf "\n"

export ASTRA_VAULT_PASSPHRASE="$passphrase"
python -m apps.api.vault_cli set OPENAI_API_KEY "$api_key"

unset api_key
unset passphrase

echo "Ключ сохранён."
