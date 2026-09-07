#!/usr/bin/env bash
# Sets up gigapaper (venv + deps) and starts the dev server.
#
# Usage:
#   ./run.sh              start the server on http://127.0.0.1:8000
#   PORT=8137 ./run.sh    start on a different port
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PORT="${PORT:-8000}"
VENV=.venv

if [ ! -d "$VENV" ]; then
  echo "Creating virtualenv in $VENV..."
  python3 -m venv "$VENV"
fi

PY="$VENV/bin/python"
PIP="$VENV/bin/pip"

# Install/refresh the app plus the snapshot extra (interactive-diagram capture
# on URL import). Cheap no-op if already satisfied.
"$PIP" install -q -e ".[snapshots,dev]"

# Snapshotting (capturing interactive diagrams when importing a URL) needs a
# real browser. gigapaper already falls back to system Chrome/Edge if
# Playwright's own Chromium isn't installed, so only download one (~150MB) if
# neither is available — most Macs already have Chrome and need nothing here.
if ! "$PY" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    for kwargs in ({}, {'channel': 'chrome'}, {'channel': 'msedge'}):
        try:
            p.chromium.launch(**kwargs).close()
            raise SystemExit(0)
        except Exception:
            continue
    raise SystemExit(1)
" >/dev/null 2>&1; then
  echo "No browser found for Playwright; installing Chromium (used only when importing a URL)..."
  "$PY" -m playwright install chromium || echo "  (skipping — URL imports will still work, just without diagram snapshots)"
fi

URL="http://127.0.0.1:$PORT"
echo "Starting gigapaper on $URL"

# Open the browser once the server is up, without blocking the server itself.
(
  for _ in $(seq 1 50); do
    curl -s -o /dev/null "$URL" && break
    sleep 0.2
  done
  open "$URL" 2>/dev/null || true
) &

exec "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$PORT" --reload
