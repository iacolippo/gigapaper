from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FolderCreate(BaseModel):
    name: str


class FolderUpdate(BaseModel):
    name: str


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class PaperUpdate(BaseModel):
    folder_id: int | None = None
    title: str | None = None
    read: bool | None = None
    # Written as a pair: the page at the top of the viewport, and how far into
    # it the reader had scrolled.
    last_page: int | None = None
    last_offset: float | None = None


class PaperImport(BaseModel):
    url: str
    folder_id: int | None = None


class PaperOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    filename: str
    kind: str
    source_url: str | None
    folder_id: int | None
    uploaded_at: datetime
    read_at: datetime | None
    last_page: int | None
    last_offset: float | None


class Rect(BaseModel):
    x: float
    y: float
    width: float
    height: float
    # Set only when a highlight spans a page break, naming the page this rect
    # sits on; otherwise the rect belongs to the highlight's own page_number.
    page: int | None = None


class CommentCreate(BaseModel):
    body: str


class CommentUpdate(BaseModel):
    body: str


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    highlight_id: int
    body: str
    created_at: datetime


class HighlightCreate(BaseModel):
    page_number: int
    selected_text: str
    rects: list[Rect]
    color: str = "#ffe066"
    comment: str | None = None


class HighlightUpdate(BaseModel):
    color: str | None = None


class HighlightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    paper_id: int
    page_number: int
    selected_text: str
    rects: list[Rect]
    color: str
    created_at: datetime
    comments: list[CommentOut] = []
