"""The API is unauthenticated on localhost, so writes must not be driveable
by another page in the same browser."""

from tests.conftest import MINIMAL_PDF

FOREIGN = "https://deepseek-v3.ezyang.com"


def test_cross_origin_write_is_rejected(client):
    resp = client.post(
        "/api/folders", json={"name": "from another site"}, headers={"Origin": FOREIGN}
    )
    assert resp.status_code == 403
    assert client.get("/api/folders").json() == []


def test_cross_origin_multipart_upload_is_rejected(client):
    # multipart is a "simple" request: no preflight protects this one
    resp = client.post(
        "/api/papers",
        files={"file": ("x.pdf", MINIMAL_PDF, "application/pdf")},
        headers={"Origin": FOREIGN},
    )
    assert resp.status_code == 403
    assert client.get("/api/papers").json() == []


def test_cross_origin_delete_is_rejected(client):
    folder = client.post("/api/folders", json={"name": "Keep"}).json()
    resp = client.delete(f"/api/folders/{folder['id']}", headers={"Origin": FOREIGN})
    assert resp.status_code == 403
    assert len(client.get("/api/folders").json()) == 1


def test_same_origin_write_is_allowed(client):
    resp = client.post(
        "/api/folders", json={"name": "Mine"}, headers={"Origin": "http://testserver"}
    )
    assert resp.status_code == 201


def test_write_without_an_origin_is_allowed(client):
    # curl and other non-browser clients send no Origin
    assert client.post("/api/folders", json={"name": "From curl"}).status_code == 201


def test_reads_are_never_blocked(client):
    assert client.get("/api/papers", headers={"Origin": FOREIGN}).status_code == 200
