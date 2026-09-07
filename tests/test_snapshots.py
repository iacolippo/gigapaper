"""Snapshots stand in for page elements that JavaScript draws, which would
otherwise be lost when the article is reduced to Markdown."""

import re

import pytest

WIDGET_HTML = """
<html><body><article>
  <p>An opening paragraph with enough substance that the extractor keeps this
  block rather than discarding it as boilerplate around the real content.</p>
  <dsv3-anatomy style="min-height:700px" layer="params"></dsv3-anatomy>
  <p>A closing paragraph, also long enough to be treated as article text by
  the extractor when it scores the blocks on this page.</p>
</article></body></html>
"""


@pytest.fixture()
def fake_page(monkeypatch):
    """Serves canned HTML and fakes the browser that photographs it."""

    def _install(html=WIDGET_HTML, shots=("dsv3-anatomy",)):
        import httpx

        from app import importer, snapshots

        def fake_get(url, **kwargs):
            return httpx.Response(200, html=html, request=httpx.Request("GET", url))

        def fake_capture(url, out_dir):
            out_dir.mkdir(parents=True, exist_ok=True)
            captured = []
            seen: dict[str, int] = {}
            for i, tag in enumerate(shots):
                index = seen.get(tag, 0)
                seen[tag] = index + 1
                name = f"{i:02d}-{tag}.png"
                (out_dir / name).write_bytes(b"\x89PNG\r\n\x1a\n fake image bytes")
                captured.append(snapshots.Snapshot(tag=tag, index=index, filename=name))
            return captured

        monkeypatch.setattr(importer.httpx, "get", fake_get)
        monkeypatch.setattr(snapshots, "capture", fake_capture)

    return _install


def test_snapshot_replaces_the_widget_in_place(client, fake_page):
    fake_page()
    paper = client.post("/api/papers/url", json={"url": "https://example.com/a"}).json()

    md = client.get(f"/api/papers/{paper['id']}/file").text
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
    assert len(images) == 1
    assert images[0].startswith("/api/snapshots/")

    # it sits between the two paragraphs, where the widget was
    body = md.replace("\n", " ")
    assert body.index("An opening paragraph") < body.index("/api/snapshots/")
    assert body.index("/api/snapshots/") < body.index("A closing paragraph")

    # and it is served
    resp = client.get(images[0])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_import_still_works_when_snapshotting_is_unavailable(client, fake_page, monkeypatch):
    fake_page()
    from app import snapshots

    def exploding_capture(url, out_dir):
        raise RuntimeError("no browser here")

    monkeypatch.setattr(snapshots, "capture", exploding_capture)

    resp = client.post("/api/papers/url", json={"url": "https://example.com/b"})
    assert resp.status_code == 201
    md = client.get(f"/api/papers/{resp.json()['id']}/file").text
    assert "An opening paragraph" in md


def test_deleting_the_paper_removes_its_snapshots(client, fake_page):
    fake_page()
    paper = client.post("/api/papers/url", json={"url": "https://example.com/c"}).json()

    from app.db import SNAPSHOT_DIR

    stem = paper["filename"].removesuffix(".md")
    assert (SNAPSHOT_DIR / stem).is_dir()

    assert client.delete(f"/api/papers/{paper['id']}").status_code == 204
    assert not (SNAPSHOT_DIR / stem).exists()


def test_snapshot_paths_cannot_escape_the_store(client):
    for bad in ("/api/snapshots/..%2f..%2fetc/passwd.png",
                "/api/snapshots/abc/..%2f..%2fsecret.png",
                "/api/snapshots/abc/notes.txt"):
        assert client.get(bad).status_code == 404


TWO_WIDGETS_HTML = """
<html><body><article>
  <p>An opening paragraph with enough substance that the extractor keeps this
  block rather than discarding it as boilerplate around the real content.</p>
  <dsv3-anatomy style="min-height:700px" layer="params"></dsv3-anatomy>
  <p>A middle paragraph, again long enough that the extractor treats it as
  part of the article body rather than page furniture.</p>
  <dsv3-anatomy style="min-height:700px" layer="flops"></dsv3-anatomy>
  <p>A closing paragraph, also long enough to be treated as article text by
  the extractor when it scores the blocks on this page.</p>
</article></body></html>
"""


def test_every_widget_on_the_page_is_embedded(client, fake_page):
    """Replacing one element must not shift the others out of reach."""
    fake_page(html=TWO_WIDGETS_HTML, shots=("dsv3-anatomy", "dsv3-anatomy"))
    paper = client.post("/api/papers/url", json={"url": "https://example.com/two"}).json()

    md = client.get(f"/api/papers/{paper['id']}/file").text
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
    assert len(images) == 2, f"both widgets should be embedded, got {images}"
    assert images[0].endswith("00-dsv3-anatomy.png")
    assert images[1].endswith("01-dsv3-anatomy.png")

    # each sits where its widget was
    body = md.replace("\n", " ")
    assert body.index("An opening paragraph") < body.index(images[0])
    assert body.index(images[0]) < body.index("A middle paragraph")
    assert body.index("A middle paragraph") < body.index(images[1])
    assert body.index(images[1]) < body.index("A closing paragraph")

    for url in images:
        assert client.get(url).status_code == 200
