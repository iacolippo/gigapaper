import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = Path(os.environ.get("GIGAPAPER_DATA_DIR", Path(__file__).resolve().parent.parent / "storage"))
PDF_DIR = DATA_DIR / "pdfs"
DOC_DIR = DATA_DIR / "docs"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
DB_PATH = DATA_DIR / "gigapaper.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)
DOC_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("GIGAPAPER_DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema() -> None:
    """Add columns introduced after a database was first created.

    The app has no migration tool; this keeps an existing library usable
    when a release adds a nullable column.
    """
    added = {
        "kind": "ALTER TABLE papers ADD COLUMN kind VARCHAR(16) DEFAULT 'pdf' NOT NULL",
        "source_url": "ALTER TABLE papers ADD COLUMN source_url VARCHAR(2000)",
        "read_at": "ALTER TABLE papers ADD COLUMN read_at DATETIME",
    }
    with engine.begin() as conn:
        tables = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='papers'")
        ).fetchall()
        if not tables:
            return
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(papers)"))}
        for column, statement in added.items():
            if column not in existing:
                conn.execute(text(statement))


def migrate_legacy_comments() -> None:
    """Move each highlight's single `comment` into the comments table.

    Runs once per row: the value is cleared as it is copied, so a comment the
    user later deletes does not come back on the next start.
    """
    with engine.begin() as conn:
        tables = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='highlights'")
        ).fetchall()
        if not tables:
            return
        rows = conn.execute(
            text("SELECT id, comment, created_at FROM highlights WHERE comment IS NOT NULL")
        ).fetchall()
        for highlight_id, comment, created_at in rows:
            conn.execute(
                text(
                    "INSERT INTO comments (highlight_id, body, created_at)"
                    " VALUES (:hid, :body, :created)"
                ),
                {"hid": highlight_id, "body": comment, "created": created_at},
            )
        if rows:
            conn.execute(text("UPDATE highlights SET comment = NULL WHERE comment IS NOT NULL"))
