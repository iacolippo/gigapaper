from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.db import SNAPSHOT_DIR

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("/{stem}/{filename}")
def get_snapshot(stem: str, filename: str):
    """Serves a snapshot taken during an import."""
    # Both parts come from a URL, so keep them to a single safe path segment.
    if not stem.isalnum() or Path(filename).name != filename or not filename.endswith(".png"):
        raise HTTPException(404, "Snapshot not found")

    path = SNAPSHOT_DIR / stem / filename
    if not path.is_file():
        raise HTTPException(404, "Snapshot not found")
    return FileResponse(path, media_type="image/png")
