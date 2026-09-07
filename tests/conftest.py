import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAPAPER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GIGAPAPER_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")

    # Modules under app.* cache paths/engine at import time, so import fresh per test.
    import sys

    for mod in list(sys.modules):
        if mod.startswith("app"):
            del sys.modules[mod]

    from fastapi.testclient import TestClient

    from app import snapshots
    from app.main import app

    # Snapshotting drives a real browser. Off by default; tests that want it
    # patch `app.snapshots.capture` themselves.
    monkeypatch.setattr(snapshots, "capture", lambda url, out_dir: [])

    with TestClient(app) as c:
        yield c


MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \ntrailer<</Size 4/Root 1 0 R>>\n%%EOF"
)
