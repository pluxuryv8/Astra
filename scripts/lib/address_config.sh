#!/usr/bin/env bash
set -euo pipefail

DEFAULT_ASTRA_API_PORT="${DEFAULT_ASTRA_API_PORT:-8055}"
DEFAULT_ASTRA_BRIDGE_PORT="${DEFAULT_ASTRA_BRIDGE_PORT:-43124}"
DEFAULT_ASTRA_API_BASE_URL="${DEFAULT_ASTRA_API_BASE_URL:-http://127.0.0.1:${DEFAULT_ASTRA_API_PORT}/api/v1}"
DEFAULT_ASTRA_BRIDGE_BASE_URL="${DEFAULT_ASTRA_BRIDGE_BASE_URL:-http://127.0.0.1:${DEFAULT_ASTRA_BRIDGE_PORT}}"

trim_trailing_slash() {
  local value="${1:-}"
  while [ -n "$value" ] && [ "${value%/}" != "$value" ]; do
    value="${value%/}"
  done
  printf "%s" "$value"
}

extract_url_port() {
  local url="${1:-}"
  local without_scheme="${url#*://}"
  local host_port="${without_scheme%%/*}"
  if [ -z "$host_port" ]; then
    return 1
  fi
  if [[ "$host_port" == *:* ]]; then
    printf "%s" "${host_port##*:}"
    return 0
  fi
  return 1
}

validate_http_url() {
  local label="$1"
  local value="$2"
  local required_prefix="${3:-}"
  if [[ ! "$value" =~ ^https?://[^/]+ ]]; then
    echo "Invalid ${label}: ${value}" >&2
    return 1
  fi
  if [ -n "$required_prefix" ]; then
    local without_scheme="${value#*://}"
    local path="/"
    if [[ "$without_scheme" == */* ]]; then
      path="/${without_scheme#*/}"
      path="/${path#/}"
    fi
    path="${path%/}"
    if [ -z "$path" ]; then
      path="/"
    fi
    if [[ "$path" != ${required_prefix}* ]]; then
      echo "Invalid ${label} path: expected prefix ${required_prefix}, got ${path}" >&2
      return 1
    fi
  fi
  return 0
}

resolve_api_base_url() {
  local base="${ASTRA_API_BASE_URL:-${ASTRA_API_BASE:-}}"
  if [ -z "$base" ]; then
    local port="${ASTRA_API_PORT:-$DEFAULT_ASTRA_API_PORT}"
    base="http://127.0.0.1:${port}/api/v1"
  fi
  base="$(trim_trailing_slash "$base")"
  printf "%s" "$base"
}

resolve_api_port() {
  if [ -n "${ASTRA_API_PORT:-}" ]; then
    printf "%s" "${ASTRA_API_PORT}"
    return 0
  fi
  local from_base=""
  if from_base="$(extract_url_port "$(resolve_api_base_url)")"; then
    printf "%s" "$from_base"
    return 0
  fi
  printf "%s" "$DEFAULT_ASTRA_API_PORT"
}

resolve_bridge_base_url() {
  local base="${ASTRA_BRIDGE_BASE_URL:-}"
  if [ -z "$base" ]; then
    local port="${ASTRA_BRIDGE_PORT:-${ASTRA_DESKTOP_BRIDGE_PORT:-$DEFAULT_ASTRA_BRIDGE_PORT}}"
    base="http://127.0.0.1:${port}"
  fi
  base="$(trim_trailing_slash "$base")"
  printf "%s" "$base"
}

resolve_bridge_port() {
  if [ -n "${ASTRA_BRIDGE_PORT:-}" ]; then
    printf "%s" "${ASTRA_BRIDGE_PORT}"
    return 0
  fi
  if [ -n "${ASTRA_DESKTOP_BRIDGE_PORT:-}" ]; then
    printf "%s" "${ASTRA_DESKTOP_BRIDGE_PORT}"
    return 0
  fi
  local from_base=""
  if from_base="$(extract_url_port "$(resolve_bridge_base_url)")"; then
    printf "%s" "$from_base"
    return 0
  fi
  printf "%s" "$DEFAULT_ASTRA_BRIDGE_PORT"
}

apply_resolved_address_env() {
  local api_base
  local api_port
  local bridge_base
  local bridge_port
  local api_base_port=""
  local bridge_base_port=""

  api_base="$(resolve_api_base_url)"
  bridge_base="$(resolve_bridge_base_url)"
  api_port="$(resolve_api_port)"
  bridge_port="$(resolve_bridge_port)"

  validate_http_url "ASTRA_API_BASE_URL" "$api_base" "/api/v1"
  validate_http_url "ASTRA_BRIDGE_BASE_URL" "$bridge_base"

  if api_base_port="$(extract_url_port "$api_base")"; then
    if [ -n "$api_port" ] && [ "$api_base_port" != "$api_port" ]; then
      echo "Address mismatch: ASTRA_API_BASE_URL port (${api_base_port}) != ASTRA_API_PORT (${api_port})" >&2
      return 1
    fi
  fi

  if bridge_base_port="$(extract_url_port "$bridge_base")"; then
    if [ -n "$bridge_port" ] && [ "$bridge_base_port" != "$bridge_port" ]; then
      echo "Address mismatch: ASTRA_BRIDGE_BASE_URL port (${bridge_base_port}) != ASTRA_BRIDGE_PORT (${bridge_port})" >&2
      return 1
    fi
  fi

  export ASTRA_API_BASE_URL="$api_base"
  export ASTRA_API_BASE="$api_base"
  export ASTRA_API_PORT="$api_port"

  export ASTRA_BRIDGE_BASE_URL="$bridge_base"
  export ASTRA_BRIDGE_PORT="$bridge_port"
  export ASTRA_DESKTOP_BRIDGE_PORT="$bridge_port"

  if [ -n "${VITE_ASTRA_API_BASE_URL:-}" ] && [ "${VITE_ASTRA_API_BASE_URL}" != "$api_base" ]; then
    echo "Address mismatch: VITE_ASTRA_API_BASE_URL (${VITE_ASTRA_API_BASE_URL}) != ASTRA_API_BASE_URL (${api_base})" >&2
    return 1
  fi
  if [ -n "${VITE_ASTRA_BRIDGE_BASE_URL:-}" ] && [ "${VITE_ASTRA_BRIDGE_BASE_URL}" != "$bridge_base" ]; then
    echo "Address mismatch: VITE_ASTRA_BRIDGE_BASE_URL (${VITE_ASTRA_BRIDGE_BASE_URL}) != ASTRA_BRIDGE_BASE_URL (${bridge_base})" >&2
    return 1
  fi

  export VITE_ASTRA_API_BASE_URL="$api_base"
  export VITE_ASTRA_BRIDGE_BASE_URL="$bridge_base"
  export VITE_ASTRA_BRIDGE_PORT="$bridge_port"

  # Legacy compatibility for older UI paths.
  export VITE_API_PORT="$api_port"
  export VITE_DESKTOP_BRIDGE_PORT="$bridge_port"
  export VITE_ASTRA_DESKTOP_BRIDGE_PORT="$bridge_port"
}

address_summary() {
  local api_base="$1"
  local api_port="$2"
  local bridge_base="$3"
  local bridge_port="$4"
  printf "ASTRA_API_BASE_URL=%s\nASTRA_API_PORT=%s\nASTRA_BRIDGE_BASE_URL=%s\nASTRA_BRIDGE_PORT=%s\n" \
    "$api_base" "$api_port" "$bridge_base" "$bridge_port"
}
