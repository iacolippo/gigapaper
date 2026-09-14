"""Where the app's files live, whether it runs from source or from a bundle.

Running from a checkout, everything sits next to the code: `static/` beside
`app/`, the library in `storage/`. Frozen into Gigapaper.app the two split
apart — the bundle is read-only and code-signed, so the library has to move to
the user's own data directory, and the bundled files come from wherever
PyInstaller unpacked them.
"""

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))

APP_NAME = "gigapaper"


def resource_dir() -> Path:
    """Root holding the read-only files shipped with the app (`static/`)."""
    if FROZEN:
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def default_data_dir() -> Path:
    """Root for the library: PDFs, articles, snapshots, the database.

    From a checkout this stays `storage/` next to the code, so a dev copy and
    an installed app never share a library by accident.
    """
    if not FROZEN:
        return Path(__file__).resolve().parent.parent / "storage"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / APP_NAME
