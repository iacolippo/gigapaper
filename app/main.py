from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import Base, engine, ensure_schema, migrate_legacy_comments
from app.paths import resource_dir
from app.routers import folders, highlights, papers, snapshots

Base.metadata.create_all(bind=engine)
ensure_schema()
migrate_legacy_comments()

app = FastAPI(title="gigapaper")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def reject_cross_origin_writes(request: Request, call_next):
    """Blocks writes driven by another site.

    The API is unauthenticated and bound to localhost, so any page in the
    browser can reach it. Preflight already stops cross-origin JSON and DELETE,
    but a multipart POST is a "simple" request and goes straight through — so
    check Origin, which the browser sets on every cross-origin request and
    cannot be forged by page script. Tools without an Origin (curl, the test
    client) are unaffected.
    """
    if request.method in UNSAFE_METHODS:
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host', '')}":
            return JSONResponse({"detail": "Cross-origin write rejected"}, status_code=403)
    return await call_next(request)


app.include_router(folders.router)
app.include_router(papers.router)
app.include_router(highlights.router)
app.include_router(snapshots.router)

STATIC_DIR = resource_dir() / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
