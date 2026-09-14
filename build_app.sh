#!/usr/bin/env bash
# Builds dist/Gigapaper.app — a double-clickable desktop build.
#
# Usage:
#   ./build_app.sh                    ~95MB, no interactive-diagram snapshots
#   WITH_SNAPSHOTS=1 ./build_app.sh   +134MB, snapshots via system Chrome/Edge
#   INSTALL=1 ./build_app.sh          also install into /Applications
#
# The result is unsigned: macOS will ask on first launch (right-click > Open,
# or System Settings > Privacy & Security). Signing is a separate step.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

VENV=.venv
[ -d "$VENV" ] || python3 -m venv "$VENV"

"$VENV/bin/pip" install -q -e ".[build]"
# A running copy holds its files open, which makes the rebuild fail halfway.
pkill -f "Gigapaper.app/Contents/MacOS/gigapaper" 2>/dev/null || true
for _ in $(seq 1 50); do
  pgrep -f "Gigapaper.app/Contents/MacOS/gigapaper" >/dev/null || break
  sleep 0.1
done

# Even once it is gone, a file handle or Spotlight's indexer can hold a file
# open for a moment longer, and rm then fails with "Directory not empty".
clear_tree() {
  for _ in $(seq 1 20); do
    rm -rf "$1" 2>/dev/null && [ ! -e "$1" ] && return 0
    sleep 0.25
  done
  echo "could not remove $1 — is it open somewhere?" >&2
  return 1
}

clear_tree build
clear_tree dist
"$VENV/bin/pyinstaller" --noconfirm --clean gigapaper.spec

echo
echo "Built dist/Gigapaper.app"

if [ "${INSTALL:-}" = "1" ]; then
  DEST=/Applications/Gigapaper.app
  clear_tree "$DEST"
  cp -R dist/Gigapaper.app "$DEST"
  # Unsigned builds are quarantined; clearing it skips the Gatekeeper prompt.
  xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true
  # Index it now instead of waiting for Spotlight to notice.
  mdimport "$DEST"
  echo "Installed $DEST — find it in Spotlight as \"Gigapaper\"."
else
  echo "Drag it to /Applications, or rerun with INSTALL=1 to do that here."
fi

echo "Your library lives in ~/Library/Application Support/gigapaper."
