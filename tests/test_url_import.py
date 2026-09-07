import re

import pytest

from tests.conftest import MINIMAL_PDF

ARTICLE_HTML = """
<html><head><title>Ignore me</title></head><body>
  <nav>site nav that should not be imported</nav>
  <article>
    <h1>Deep RL Doesn't Work Yet</h1>
    <p>This is the first paragraph of the article body, long enough that the
    extractor treats it as real content rather than boilerplate noise.</p>
    <h2>A section</h2>
    <p>Another substantial paragraph so the extractor keeps the section, with
    a <a href="https://example.com/ref">link</a> inside it.</p>
    <script>window.pwned = true;</script>
  </article>
  <footer>footer junk</footer>
</body></html>
"""


@pytest.fixture()
def fake_get(monkeypatch):
    """Serves canned HTML in place of a real network fetch."""

    def _install(html="", status=200, exc=None):
        import httpx

        from app import importer

        def fake(url, **kwargs):
            if exc is not None:
                raise exc
            request = httpx.Request("GET", url)
            return httpx.Response(status, html=html, request=request)

        monkeypatch.setattr(importer.httpx, "get", fake)

    return _install


def test_import_url_stores_markdown(client, fake_get):
    fake_get(ARTICLE_HTML)

    resp = client.post("/api/papers/url", json={"url": "https://example.com/rl-hard"})
    assert resp.status_code == 201
    paper = resp.json()
    assert paper["kind"] == "markdown"
    assert paper["source_url"] == "https://example.com/rl-hard"
    assert paper["title"] == "Deep RL Doesn't Work Yet"

    # the stored file is markdown, with the page furniture stripped out
    resp = client.get(f"/api/papers/{paper['id']}/file")
    assert resp.status_code == 200
    body = resp.text
    assert "first paragraph of the article body" in body
    assert "site nav" not in body
    assert "footer junk" not in body

    # and it renders to sanitised html for the reader
    resp = client.get(f"/api/papers/{paper['id']}/html")
    assert resp.status_code == 200
    assert "<p>" in resp.text
    assert "<script" not in resp.text
    assert "window.pwned" not in resp.text


def test_import_url_into_folder(client, fake_get):
    fake_get(ARTICLE_HTML)
    folder = client.post("/api/folders", json={"name": "Reading"}).json()

    paper = client.post(
        "/api/papers/url", json={"url": "https://example.com/a", "folder_id": folder["id"]}
    ).json()
    assert paper["folder_id"] == folder["id"]
    assert len(client.get("/api/papers", params={"folder_id": folder["id"]}).json()) == 1


def test_imported_article_can_be_highlighted_and_deleted(client, fake_get):
    fake_get(ARTICLE_HTML)
    paper = client.post("/api/papers/url", json={"url": "https://example.com/a"}).json()

    resp = client.post(
        f"/api/papers/{paper['id']}/highlights",
        json={
            "page_number": 1,
            "selected_text": "first paragraph",
            "rects": [{"x": 10, "y": 20, "width": 30, "height": 2}],
        },
    )
    assert resp.status_code == 201

    assert client.delete(f"/api/papers/{paper['id']}").status_code == 204
    assert client.get("/api/papers").json() == []


def test_reject_unreadable_and_bad_urls(client, fake_get):
    fake_get("<html><body></body></html>")
    resp = client.post("/api/papers/url", json={"url": "https://example.com/empty"})
    assert resp.status_code == 400
    assert "readable" in resp.json()["detail"]

    resp = client.post("/api/papers/url", json={"url": "ftp://example.com/thing"})
    assert resp.status_code == 400
    assert "http" in resp.json()["detail"]

    fake_get(status=404, html="<html></html>")
    resp = client.post("/api/papers/url", json={"url": "https://example.com/missing"})
    assert resp.status_code == 400
    assert "404" in resp.json()["detail"]


def test_html_endpoint_rejects_pdfs(client):
    paper = client.post(
        "/api/papers", files={"file": ("A Paper.pdf", MINIMAL_PDF, "application/pdf")}
    ).json()
    assert client.get(f"/api/papers/{paper['id']}/html").status_code == 400


def test_pdf_uploads_default_to_pdf_kind(client):
    paper = client.post(
        "/api/papers", files={"file": ("A Paper.pdf", MINIMAL_PDF, "application/pdf")}
    ).json()
    assert paper["kind"] == "pdf"
    assert paper["source_url"] is None


FOOTNOTE_HTML = """
<html><body><article>
  <p>The inactive parameter count is dominated by the expert weights, which is
  the point of the whole exercise and worth stating at length.<sup><a
  id="fnref1" href="#fn1">1</a></sup></p>
  <p><img src="/assets/real-diagram.png" alt="a real diagram" /></p>
  <p>A second substantial paragraph so the extractor keeps this section of the
  document rather than treating it as boilerplate noise.</p>
  <div class="fnotes"><p id="fn1"><sup>1</sup> The footnote body itself, long
  enough to be kept by the extractor when it scores this block.</p></div>
</article></body></html>
"""


def test_footnote_markers_do_not_become_broken_images(client, fake_get):
    fake_get(FOOTNOTE_HTML)
    paper = client.post(
        "/api/papers/url", json={"url": "https://example.com/study.html"}
    ).json()

    md = client.get(f"/api/papers/{paper['id']}/file").text
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
    # the real diagram survives, absolutised; the footnote link does not
    assert "https://example.com/assets/real-diagram.png" in images
    assert not [src for src in images if "#fn1" in src]

    html = client.get(f"/api/papers/{paper['id']}/html").text
    rendered = re.findall(r'<img[^>]*src="([^"]*)"', html)
    assert rendered == ["https://example.com/assets/real-diagram.png"]


def test_images_that_cannot_be_images_are_dropped(client):
    from app.importer import render_html

    html = render_html(
        "![a](https://example.com/page.html)\n\n"
        "![b](#anchor)\n\n"
        "![c](https://example.com/photo.png)\n"
    )
    assert re.findall(r'<img[^>]*src="([^"]*)"', html) == ["https://example.com/photo.png"]
