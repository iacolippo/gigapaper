import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.db import DOC_DIR, PDF_DIR, SNAPSHOT_DIR, get_db
from app.importer import ImportError_, fetch_article, render_html
from app.models import Paper
from app.schemas import PaperImport, PaperOut, PaperUpdate

router = APIRouter(prefix="/api/papers", tags=["papers"])


def _path_for(paper: Paper) -> Path:
    return (DOC_DIR if paper.kind == "markdown" else PDF_DIR) / paper.filename


@router.get("", response_model=list[PaperOut])
def list_papers(folder_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Paper)
    if folder_id is not None:
        query = query.filter(Paper.folder_id == folder_id)
    return query.order_by(Paper.uploaded_at.desc()).all()


@router.post("", response_model=PaperOut, status_code=201)
async def upload_paper(
    file: UploadFile, folder_id: int | None = None, db: Session = Depends(get_db)
):
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    stored_name = f"{uuid.uuid4().hex}.pdf"
    dest = PDF_DIR / stored_name
    dest.write_bytes(await file.read())

    paper = Paper(title=Path(file.filename).stem, filename=stored_name, folder_id=folder_id)
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


@router.post("/url", response_model=PaperOut, status_code=201)
def import_paper_from_url(payload: PaperImport, db: Session = Depends(get_db)):
    # One id ties the document to the snapshots taken alongside it, so deleting
    # the paper can clean both up.
    stem = uuid.uuid4().hex
    try:
        title, body = fetch_article(
            payload.url, SNAPSHOT_DIR / stem, f"/api/snapshots/{stem}"
        )
    except ImportError_ as exc:
        shutil.rmtree(SNAPSHOT_DIR / stem, ignore_errors=True)
        raise HTTPException(400, str(exc)) from exc

    stored_name = f"{stem}.md"
    (DOC_DIR / stored_name).write_text(body, encoding="utf-8")

    paper = Paper(
        title=title,
        filename=stored_name,
        kind="markdown",
        source_url=payload.url,
        folder_id=payload.folder_id,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)
    return paper


@router.get("/{paper_id}/file")
def get_paper_file(paper_id: int, db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404, "Paper not found")
    media_type = "text/markdown" if paper.kind == "markdown" else "application/pdf"
    return FileResponse(_path_for(paper), media_type=media_type)


@router.get("/{paper_id}/html", response_class=HTMLResponse)
def get_paper_html(paper_id: int, db: Session = Depends(get_db)):
    """The stored Markdown, rendered for the reader. Markdown papers only."""
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404, "Paper not found")
    if paper.kind != "markdown":
        raise HTTPException(400, "This paper is a PDF; read it from /file")
    return HTMLResponse(render_html(_path_for(paper).read_text(encoding="utf-8")))


@router.patch("/{paper_id}", response_model=PaperOut)
def update_paper(paper_id: int, payload: PaperUpdate, db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404, "Paper not found")
    if payload.title is not None:
        paper.title = payload.title
    if "folder_id" in payload.model_fields_set:
        paper.folder_id = payload.folder_id
    if payload.read is not None:
        paper.read_at = datetime.now(UTC) if payload.read else None
    if payload.last_page is not None:
        paper.last_page = payload.last_page
        paper.last_offset = min(max(payload.last_offset or 0.0, 0.0), 1.0)
    db.commit()
    db.refresh(paper)
    return paper


@router.delete("/{paper_id}", status_code=204)
def delete_paper(paper_id: int, db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404, "Paper not found")
    _path_for(paper).unlink(missing_ok=True)
    if paper.kind == "markdown":
        shutil.rmtree(SNAPSHOT_DIR / Path(paper.filename).stem, ignore_errors=True)
    db.delete(paper)
    db.commit()
