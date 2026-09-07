# gigapaper

A local reading room for research papers. Import PDFs or articles from a URL,
highlight passages, and hang threaded comments off them — all served from a
FastAPI app on your own machine, with the library stored in a single SQLite
database and a folder of files.

Nothing leaves the machine: there is no account, no sync, and no telemetry.

## Quickstart

```bash
./run.sh
```

That creates a virtualenv, installs the app, and starts the server on
<http://127.0.0.1:8000>, opening your browser once it is up. Use a different
port with `PORT=8137 ./run.sh`.

Requires Python 3.11+.

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
  main.py         FastAPI app, static mount, cross-origin write guard
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
```

The reader is plain ES modules and hand-written CSS — no build step, no
bundler. Editing a file in `static/` and reloading is the whole dev loop.

## Your data

Everything lives under `storage/`:

| | |
|---|---|
| `storage/gigapaper.db` | papers, folders, highlights, comments |
| `storage/pdfs/` | uploaded PDFs |
| `storage/docs/` | imported articles, as Markdown |
| `storage/snapshots/` | captured interactive diagrams |

It is deliberately `.gitignore`d — back it up by copying the directory. Point
the app somewhere else with `GIGAPAPER_DATA_DIR=/path/to/library ./run.sh`.

## Development

```bash
.venv/bin/python -m pytest    # the test suite
.venv/bin/ruff check .        # lint
```

Snapshotting interactive diagrams needs a browser. `run.sh` uses system Chrome
or Edge if either is installed and only downloads Playwright's own Chromium
when neither is — URL imports still work without one, just without the diagram
captures.
