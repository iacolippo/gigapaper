from tests.conftest import MINIMAL_PDF


def test_upload_list_move_delete_paper(client):
    resp = client.post(
        "/api/papers", files={"file": ("Attention Is All You Need.pdf", MINIMAL_PDF, "application/pdf")}
    )
    assert resp.status_code == 201
    paper = resp.json()
    assert paper["title"] == "Attention Is All You Need"
    assert paper["folder_id"] is None

    resp = client.get(f"/api/papers/{paper['id']}/file")
    assert resp.status_code == 200
    assert resp.content == MINIMAL_PDF

    folder = client.post("/api/folders", json={"name": "Transformers"}).json()
    resp = client.patch(f"/api/papers/{paper['id']}", json={"folder_id": folder["id"]})
    assert resp.status_code == 200
    assert resp.json()["folder_id"] == folder["id"]

    resp = client.get("/api/papers", params={"folder_id": folder["id"]})
    assert len(resp.json()) == 1

    resp = client.delete(f"/api/papers/{paper['id']}")
    assert resp.status_code == 204
    assert client.get("/api/papers").json() == []


def test_reject_non_pdf_upload(client):
    resp = client.post("/api/papers", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 400


def test_mark_paper_read_and_unread(client):
    paper = client.post(
        "/api/papers", files={"file": ("A Paper.pdf", MINIMAL_PDF, "application/pdf")}
    ).json()
    assert paper["read_at"] is None

    resp = client.patch(f"/api/papers/{paper['id']}", json={"read": True})
    assert resp.status_code == 200
    marked = resp.json()["read_at"]
    assert marked is not None

    # the flag survives a listing, and unrelated edits leave it alone
    listed = client.get("/api/papers").json()[0]
    assert listed["read_at"] == marked

    folder = client.post("/api/folders", json={"name": "Read"}).json()
    resp = client.patch(f"/api/papers/{paper['id']}", json={"folder_id": folder["id"]})
    assert resp.json()["read_at"] == marked

    resp = client.patch(f"/api/papers/{paper['id']}", json={"read": False})
    assert resp.json()["read_at"] is None
