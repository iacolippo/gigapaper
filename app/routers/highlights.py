import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Comment, Highlight, Paper
from app.schemas import (
    CommentCreate,
    CommentOut,
    CommentUpdate,
    HighlightCreate,
    HighlightOut,
    HighlightUpdate,
)

router = APIRouter(prefix="/api/papers/{paper_id}/highlights", tags=["highlights"])


def _to_out(highlight: Highlight) -> HighlightOut:
    return HighlightOut(
        id=highlight.id,
        paper_id=highlight.paper_id,
        page_number=highlight.page_number,
        selected_text=highlight.selected_text,
        rects=json.loads(highlight.rects),
        color=highlight.color,
        created_at=highlight.created_at,
        comments=[CommentOut.model_validate(c) for c in highlight.comments],
    )


@router.get("", response_model=list[HighlightOut])
def list_highlights(paper_id: int, db: Session = Depends(get_db)):
    highlights = db.query(Highlight).filter(Highlight.paper_id == paper_id).all()
    return [_to_out(h) for h in highlights]


@router.post("", response_model=HighlightOut, status_code=201)
def create_highlight(paper_id: int, payload: HighlightCreate, db: Session = Depends(get_db)):
    if db.get(Paper, paper_id) is None:
        raise HTTPException(404, "Paper not found")
    highlight = Highlight(
        paper_id=paper_id,
        page_number=payload.page_number,
        selected_text=payload.selected_text,
        rects=json.dumps([r.model_dump(exclude_none=True) for r in payload.rects]),
        color=payload.color,
    )
    # A note written while selecting becomes the highlight's first comment.
    if payload.comment and payload.comment.strip():
        highlight.comments.append(Comment(body=payload.comment.strip()))
    db.add(highlight)
    db.commit()
    db.refresh(highlight)
    return _to_out(highlight)


@router.patch("/{highlight_id}", response_model=HighlightOut)
def update_highlight(
    paper_id: int, highlight_id: int, payload: HighlightUpdate, db: Session = Depends(get_db)
):
    highlight = db.get(Highlight, highlight_id)
    if highlight is None or highlight.paper_id != paper_id:
        raise HTTPException(404, "Highlight not found")
    if payload.color is not None:
        highlight.color = payload.color
    db.commit()
    db.refresh(highlight)
    return _to_out(highlight)


@router.delete("/{highlight_id}", status_code=204)
def delete_highlight(paper_id: int, highlight_id: int, db: Session = Depends(get_db)):
    highlight = db.get(Highlight, highlight_id)
    if highlight is None or highlight.paper_id != paper_id:
        raise HTTPException(404, "Highlight not found")
    db.delete(highlight)
    db.commit()


def _get_comment(paper_id: int, highlight_id: int, comment_id: int, db: Session) -> Comment:
    comment = db.get(Comment, comment_id)
    if (
        comment is None
        or comment.highlight_id != highlight_id
        or comment.highlight.paper_id != paper_id
    ):
        raise HTTPException(404, "Comment not found")
    return comment


@router.post("/{highlight_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    paper_id: int, highlight_id: int, payload: CommentCreate, db: Session = Depends(get_db)
):
    highlight = db.get(Highlight, highlight_id)
    if highlight is None or highlight.paper_id != paper_id:
        raise HTTPException(404, "Highlight not found")
    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "A comment needs some text")

    comment = Comment(highlight_id=highlight_id, body=body)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return comment


@router.patch("/{highlight_id}/comments/{comment_id}", response_model=CommentOut)
def edit_comment(
    paper_id: int,
    highlight_id: int,
    comment_id: int,
    payload: CommentUpdate,
    db: Session = Depends(get_db),
):
    comment = _get_comment(paper_id, highlight_id, comment_id, db)
    body = payload.body.strip()
    if not body:
        raise HTTPException(400, "A comment needs some text")
    comment.body = body
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{highlight_id}/comments/{comment_id}", status_code=204)
def delete_comment(
    paper_id: int, highlight_id: int, comment_id: int, db: Session = Depends(get_db)
):
    comment = _get_comment(paper_id, highlight_id, comment_id, db)
    db.delete(comment)
    db.commit()
