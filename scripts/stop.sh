#!/usr/bin/env bash
set -euo pipefail

API_PORT="${ASTRA_API_PORT:-8055}"

if [ -f .astra/api.pid ]; then
  kill "$(cat .astra/api.pid)" >/dev/null 2>&1 || true
  rm -f .astra/api.pid
fi

if [ -f .astra/tauri.pid ]; then
  kill "$(cat .astra/tauri.pid)" >/dev/null 2>&1 || true
  rm -f .astra/tauri.pid
fi

pids=$(lsof -nP -iTCP:"$API_PORT" -sTCP:LISTEN -t 2>/dev/null || true)
if [ -n "$pids" ]; then
  kill $pids >/dev/null 2>&1 || true
  echo "Остановлен API на порту $API_PORT"
fi

pids=$(lsof -nP -iTCP:5173 -sTCP:LISTEN -t 2>/dev/null || true)
if [ -n "$pids" ]; then
  kill $pids >/dev/null 2>&1 || true
  echo "Остановлен Vite (порт 5173)"
fi

pids=$(pgrep -f "tauri dev" || true)
if [ -n "$pids" ]; then
  kill $pids >/dev/null 2>&1 || true
  echo "Остановлен Tauri dev"
fi
