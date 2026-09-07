from datetime import UTC, datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Folder(Base):
    __tablename__ = "folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    papers: Mapped[list["Paper"]] = relationship(back_populates="folder")


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(255))
    # "pdf" for uploads, "markdown" for articles imported from a URL.
    kind: Mapped[str] = mapped_column(String(16), default="pdf", server_default="pdf")
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("folders.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(default=_utcnow)
    # Null until the paper is marked read; holds when that happened.
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)

    folder: Mapped["Folder | None"] = relationship(back_populates="papers")
    highlights: Mapped[list["Highlight"]] = relationship(
        back_populates="paper", cascade="all, delete-orphan"
    )


class Highlight(Base):
    __tablename__ = "highlights"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"))
    page_number: Mapped[int] = mapped_column()
    selected_text: Mapped[str] = mapped_column(Text)
    rects: Mapped[str] = mapped_column(Text)  # JSON-encoded list of {x,y,width,height} in % of page
    color: Mapped[str] = mapped_column(String(20), default="#ffe066")
    # Superseded by the comments table; kept so old databases still load, and
    # emptied by migrate_legacy_comments() once its value has been moved over.
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    paper: Mapped["Paper"] = relationship(back_populates="highlights")
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="highlight",
        cascade="all, delete-orphan",
        order_by="Comment.created_at",
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    highlight_id: Mapped[int] = mapped_column(ForeignKey("highlights.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    highlight: Mapped["Highlight"] = relationship(back_populates="comments")
