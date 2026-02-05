#!/usr/bin/env bash
set -euo pipefail

PLIST="$HOME/Library/LaunchAgents/com.randarc.astra.plist"

launchctl unload "$PLIST" >/dev/null 2>&1 || true
rm -f "$PLIST"

if [ -f .astra/tauri.pid ] || [ -f .astra/api.pid ]; then
  ./scripts/stop.sh
fi

echo "Автостарт удалён"
