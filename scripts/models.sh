#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ASTRA_DATA_DIR:-$ROOT_DIR/.astra}"
MODELS_DIR="$DATA_DIR/models"
CHAT_MODEL="${ASTRA_LLM_LOCAL_CHAT_MODEL:-saiga-nemo-12b}"
CODE_MODEL="${ASTRA_LLM_LOCAL_CODE_MODEL:-deepseek-coder-v2:16b-lite-instruct-q8_0}"
DEFAULT_SAIGA_URL="https://huggingface.co/IlyaGusev/saiga_nemo_12b_gguf/resolve/main/saiga_nemo_12b.Q4_K_M.gguf"
SAIGA_URL="${ASTRA_SAIGA_GGUF_URL:-$DEFAULT_SAIGA_URL}"
SAIGA_GGUF_PATH="$MODELS_DIR/saiga_nemo_12b.gguf"
REPO_MODELFILE="$ROOT_DIR/models/Modelfile.saiga-nemo-12b"

ok() { echo "OK  $*"; }
warn() { echo "WARN $*"; }
fail() { echo "FAIL $*"; exit 1; }

ensure_ollama() {
  if ! command -v ollama >/dev/null 2>&1; then
    fail "ollama not found. Install Ollama and retry."
  fi
  if ! ollama list >/dev/null 2>&1; then
    fail "ollama is not reachable. Start ollama and retry (ollama serve)."
  fi
  ok "ollama is available"
}

ensure_modelfile() {
  if [ ! -f "$REPO_MODELFILE" ]; then
    fail "Missing Modelfile: $REPO_MODELFILE"
  fi
}

resolve_modelfile() {
  mkdir -p "$MODELS_DIR"
  local target="$MODELS_DIR/Modelfile.saiga-nemo-12b"
  local abs_path
  abs_path="$(cd "$(dirname "$SAIGA_GGUF_PATH")" && pwd)/$(basename "$SAIGA_GGUF_PATH")"
  sed "s|__SAIGA_GGUF_PATH__|$abs_path|g" "$REPO_MODELFILE" > "$target"
  echo "$target"
}

install_saiga() {
  if [ -z "$SAIGA_URL" ]; then
    fail "ASTRA_SAIGA_GGUF_URL is empty. Provide a GGUF URL."
  fi
  mkdir -p "$MODELS_DIR"
  if [ -s "$SAIGA_GGUF_PATH" ]; then
    ok "GGUF already present: $SAIGA_GGUF_PATH"
  else
    ok "Downloading Saiga Nemo 12B GGUF"
    curl -fL --retry 3 --retry-delay 2 -o "$SAIGA_GGUF_PATH" "$SAIGA_URL"
    if [ ! -s "$SAIGA_GGUF_PATH" ]; then
      fail "Downloaded file is empty: $SAIGA_GGUF_PATH"
    fi
    ok "Downloaded: $SAIGA_GGUF_PATH"
  fi

  local modelfile
  modelfile="$(resolve_modelfile)"
  ok "Creating Ollama model: $CHAT_MODEL"
  ollama create "$CHAT_MODEL" -f "$modelfile"
}

install_deepseek() {
  ok "Pulling Ollama model: $CODE_MODEL"
  ollama pull "$CODE_MODEL"
}

verify_models() {
  local list
  list="$(ollama list | awk 'NR>1 {print $1}')"
  local missing=0
  local chat_expected="$CHAT_MODEL"
  local chat_tagged="$CHAT_MODEL"
  if [[ "$CHAT_MODEL" != *:* ]]; then
    chat_tagged="${CHAT_MODEL}:latest"
  fi
  if ! printf "%s\n" "$list" | grep -Fxq "$chat_expected" && ! printf "%s\n" "$list" | grep -Fxq "$chat_tagged"; then
    warn "Missing chat model: $CHAT_MODEL"
    missing=1
  fi
  local code_expected="$CODE_MODEL"
  local code_tagged="$CODE_MODEL"
  if [[ "$CODE_MODEL" != *:* ]]; then
    code_tagged="${CODE_MODEL}:latest"
  fi
  if ! printf "%s\n" "$list" | grep -Fxq "$code_expected" && ! printf "%s\n" "$list" | grep -Fxq "$code_tagged"; then
    warn "Missing code model: $CODE_MODEL"
    missing=1
  fi
  if [ "$missing" -eq 0 ]; then
    ok "Models present: $CHAT_MODEL, $CODE_MODEL"
    return 0
  fi
  return 1
}

cmd_install() {
  ensure_ollama
  ensure_modelfile
  install_saiga
  install_deepseek
  ok "Ollama models installed"
  ollama list
  if ! verify_models; then
    fail "Model verification failed"
  fi
}

cmd_verify() {
  ensure_ollama
  if verify_models; then
    ok "PASS"
    return 0
  fi
  fail "FAIL: one or more models are missing"
}

cmd_clean() {
  if [ "${CONFIRM:-}" != "1" ]; then
    echo "This will remove downloaded GGUF files from: $MODELS_DIR"
    echo "Run: CONFIRM=1 $0 clean"
    exit 1
  fi
  if [ -f "$SAIGA_GGUF_PATH" ]; then
    rm -f "$SAIGA_GGUF_PATH"
    ok "Removed: $SAIGA_GGUF_PATH"
  else
    warn "No GGUF file found at: $SAIGA_GGUF_PATH"
  fi
}

case "${1:-}" in
  install)
    cmd_install
    ;;
  verify)
    cmd_verify
    ;;
  clean)
    cmd_clean
    ;;
  *)
    echo "Usage: $0 {install|verify|clean}"
    echo "Env: ASTRA_DATA_DIR, ASTRA_LLM_LOCAL_CHAT_MODEL, ASTRA_LLM_LOCAL_CODE_MODEL, ASTRA_SAIGA_GGUF_URL"
    exit 1
    ;;
 esac
