#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.randarc.astra.plist"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.randarc.astra</string>
  <key>ProgramArguments</key>
  <array>
    <string>${ROOT_DIR}/scripts/run.sh</string>
    <string>--background</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${ROOT_DIR}/.astra/logs/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT_DIR}/.astra/logs/launchd.err.log</string>
</dict>
</plist>
PLIST

mkdir -p "${ROOT_DIR}/.astra/logs"

launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST"
launchctl kickstart -k gui/"$UID"/com.randarc.astra || true

echo "Автостарт установлен. Файл: $PLIST"
