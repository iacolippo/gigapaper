# gigapaper

A local reading room for research papers. Import PDFs or articles from a URL,
highlight passages, and hang threaded comments off them — a desktop app on
your own machine, with the library stored in a single SQLite database and a
folder of files.

Nothing leaves the machine: there is no account, no sync, and no telemetry.

## Quickstart

```bash
./build_app.sh
```

That builds `dist/Gigapaper.app` — drag it to /Applications and double-click.
It is unsigned, so the first launch needs a right-click > Open (or an
allow in System Settings > Privacy & Security).

Prefer a terminal? `./run.sh` starts the dev server on
<http://127.0.0.1:8000> and opens your browser; `PORT=8137 ./run.sh` picks a
different port.

Requires Python 3.11+.

## How it runs

There is still a server — it just stops being the interface. `app/desktop.py`
starts uvicorn on a free loopback port in a background thread and points a
native webview window at it, so there is no tab, no URL bar, and no port to
remember. Closing the window ends the process.

Installed as a package (`pip install -e ".[desktop]"`), the same thing is a
`gigapaper` command; `gigapaper --browser` skips the window and uses your
browser instead.

The packaged build leaves out Playwright, whose pip package carries a ~134MB
node driver — more than the rest of the app — so a build made this way imports
articles without capturing their interactive diagrams. Include it with
`WITH_SNAPSHOTS=1 ./build_app.sh`; either way its Chromium download stays out,
since the capture falls back to system Chrome or Edge.

The Dock icon is `assets/gigapaper.icns`, generated from `gigapaper.png` by
`tools/make_icon.py` and committed — building needs neither the script nor
Pillow. Re-run it only when the artwork changes.

## What it does

- **Import PDFs**, several at a time.
- **Import articles from a URL** — the page is extracted to Markdown and read
  in the same viewer as a PDF. Interactive diagrams on the source page are
  captured as snapshots so they survive the extraction, and a "view original"
  toggle frames the live page when you want the real thing.
- **Highlight text** in either format, including across a page break, and
  attach as many comments as you like to a highlight.
- **Margin notes**: every highlight gets a card parked beside it in a rail, in
  document order.
- **Organise** papers into folders, and mark them read — with an unread filter
  for the ones still waiting.

## Layout

```
app/
  desktop.py      the app entry point: uvicorn on a thread + a native window
  main.py         FastAPI app, static mount, cross-origin write guard
  paths.py        where files live from a checkout vs. from a bundle
  models.py       Paper, Folder, Highlight, Comment
  db.py           engine, storage paths, lightweight schema migrations
  importer.py     URL -> readable Markdown
  snapshots.py    Playwright capture of interactive diagrams
  routers/        papers, folders, highlights, snapshots
static/
  index.html      the whole UI
  js/viewer.js    PDF.js rendering, text selection, highlight painting
  js/app.js       library, viewer, notes rail, comment popover
tests/            pytest suite over the API
tools/            make_icon.py — gigapaper.png -> assets/gigapaper.icns
assets/           the generated app icon
gigapaper.spec    PyInstaller recipe for Gigapaper.app
```

The reader is plain ES modules and hand-written CSS — no build step, no
bundler. Editing a file in `static/` and reloading is the whole dev loop.

## Your data

Everything lives in one directory — `storage/` next to the code when running
from a checkout, `~/Library/Application Support/gigapaper` for the packaged
app, which cannot write inside its own bundle:

| | |
|---|---|
| `storage/gigapaper.db` | papers, folders, highlights, comments |
| `storage/pdfs/` | uploaded PDFs |
| `storage/docs/` | imported articles, as Markdown |
| `storage/snapshots/` | captured interactive diagrams |

`storage/` is deliberately `.gitignore`d — back the library up by copying the
directory. Point the app somewhere else with
`GIGAPAPER_DATA_DIR=/path/to/library`, which both the dev server and the
packaged app honour. The two locations are separate on purpose: a dev copy and
an installed app never share a library by accident.

## Development

```bash
.venv/bin/python -m pytest    # the test suite
.venv/bin/ruff check .        # lint
```

Snapshotting interactive diagrams needs a browser. `run.sh` uses system Chrome
or Edge if either is installed and only downloads Playwright's own Chromium
when neither is — URL imports still work without one, just without the diagram
captures.
