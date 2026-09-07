def test_create_list_rename_delete_folder(client):
    resp = client.post("/api/folders", json={"name": "Deep Learning"})
    assert resp.status_code == 201
    folder = resp.json()
    assert folder["name"] == "Deep Learning"

    resp = client.get("/api/folders")
    assert resp.status_code == 200
    assert [f["name"] for f in resp.json()] == ["Deep Learning"]

    resp = client.patch(f"/api/folders/{folder['id']}", json={"name": "ML"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "ML"

    resp = client.delete(f"/api/folders/{folder['id']}")
    assert resp.status_code == 204
    assert client.get("/api/folders").json() == []


def test_rename_missing_folder_404(client):
    resp = client.patch("/api/folders/999", json={"name": "x"})
    assert resp.status_code == 404


def test_delete_folder_unfiles_its_papers(client):
    folder = client.post("/api/folders", json={"name": "NLP"}).json()
    from tests.conftest import MINIMAL_PDF

    paper = client.post(
        "/api/papers",
        params={"folder_id": folder["id"]},
        files={"file": ("paper.pdf", MINIMAL_PDF, "application/pdf")},
    ).json()

    client.delete(f"/api/folders/{folder['id']}")

    resp = client.get("/api/papers")
    assert resp.json()[0]["folder_id"] is None
    assert resp.json()[0]["id"] == paper["id"]
