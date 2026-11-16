#!/bin/bash
# Video Downloader by Tanvir: app launcher
APP="$(cd "$(dirname "$0")/../.." && pwd)"
RES="$APP/Contents/Resources"
SUP="$HOME/Library/Application Support/Video Downloader"
LOG="$HOME/Library/Logs/Video Downloader.log"
mkdir -p "$SUP" "$HOME/Library/Logs"

case "$APP" in
  */AppTranslocation/*)
    osascript -e 'display alert "Move Video Downloader to Applications first" message "Drag Video Downloader into your Applications folder, then open it from there."'
    exit 0;;
esac

xattr -dr com.apple.quarantine "$APP" 2>/dev/null
chmod +x "$RES/bin/"* 2>/dev/null

if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ]; then UVBIN="$RES/bin/uv"; else UVBIN="$RES/bin/uv-x86_64"; fi
export UV="$UVBIN"
export VD_UV="$UV"
export VD_SUPPORT="$SUP"
export VD_DIR="$HOME/Movies/Video Downloader"
export UV_PYTHON_INSTALL_DIR="$SUP/python"
export UV_CACHE_DIR="$SUP/cache"
export PYTHONUNBUFFERED=1
export PATH="$SUP/venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
PY="$SUP/venv/bin/python"

[ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 2000000 ] && mv -f "$LOG" "$LOG.old"
exec >>"$LOG" 2>&1
echo "=== $(date) ==="

PKGS=("yt-dlp[default]" deno imageio-ffmpeg pywebview gallery-dl)
if [ ! -x "$PY" ] || [ ! -f "$SUP/.ready-v1" ]; then
  osascript -e 'display notification "First launch: setting up. This takes about a minute, then the window opens by itself." with title "Video Downloader"' &
  rm -rf "$SUP/venv"
  if "$UV" venv --python 3.13 "$SUP/venv" && "$UV" pip install --python "$PY" "${PKGS[@]}"; then
    touch "$SUP/.ready-v1" "$SUP/.ready-v2" "$SUP/.last-update"
  else
    osascript -e 'display alert "Video Downloader could not finish setting up" message "Check that you are online, then open the app again. If it keeps failing, see READ ME FIRST in the download, under Problems."'
    exit 1
  fi
fi
if [ ! -f "$SUP/.ready-v2" ]; then
  osascript -e 'display notification "Adding photo downloads. The window opens in a few seconds." with title "Video Downloader"' &
  "$UV" pip install --python "$PY" -U "${PKGS[@]}" && touch "$SUP/.ready-v2"
fi

exec "$PY" -u "$RES/app/app.py" --window
