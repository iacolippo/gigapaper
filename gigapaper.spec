# PyInstaller spec for Gigapaper.app. Build with ./build_app.sh.
#
# Playwright is left out by default: the pip package carries its own node
# driver (~134MB, more than the rest of the app put together) and it is only
# used to snapshot interactive diagrams when importing a URL. Without it,
# app/snapshots.py logs and imports the article without snapshots.
#
# Build with WITH_SNAPSHOTS=1 to include it. Its Chromium download is never
# bundled either way — snapshots.py falls back to system Chrome or Edge.

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

with_snapshots = os.environ.get("WITH_SNAPSHOTS") == "1"

datas = [("static", "static")]
hiddenimports = []

# trafilatura and its dependencies load data files (stopword lists, the
# justext models) and resolve some modules dynamically.
packages = ["trafilatura", "courlan", "justext", "htmldate"]
if with_snapshots:
    packages.append("playwright")

for pkg in packages:
    datas += collect_data_files(pkg)
    hiddenimports += collect_submodules(pkg)

a = Analysis(
    ["app/desktop.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hiddenimports + ["app.main", "uvicorn.logging", "uvicorn.protocols"],
    excludes=["pytest", "tkinter"] + ([] if with_snapshots else ["playwright"]),
)
pyz = PYZ(a.pure)

exe = EXE(pyz, a.scripts, exclude_binaries=True, name="gigapaper", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="gigapaper")
app = BUNDLE(
    coll,
    name="Gigapaper.app",
    icon="assets/gigapaper.icns",
    bundle_identifier="ai.lighton.gigapaper",
    info_plist={
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        # The window loads http://127.0.0.1 — cleartext, but never off-machine.
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
    },
)
