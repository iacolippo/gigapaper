from tests.conftest import MINIMAL_PDF


def _create_paper(client):
    resp = client.post("/api/papers", files={"file": ("paper.pdf", MINIMAL_PDF, "application/pdf")})
    return resp.json()


def _create_highlight(client, paper_id, comment="first thoughts"):
    payload = {
        "page_number": 1,
        "selected_text": "some text",
        "rects": [{"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}],
    }
    if comment is not None:
        payload["comment"] = comment
    return client.post(f"/api/papers/{paper_id}/highlights", json=payload).json()


def test_create_list_update_delete_highlight(client):
    paper = _create_paper(client)

    resp = client.post(
        f"/api/papers/{paper['id']}/highlights",
        json={
            "page_number": 1,
            "selected_text": "transformers are great",
            "rects": [{"x": 10.0, "y": 20.0, "width": 30.0, "height": 5.0}],
            "comment": "key insight",
        },
    )
    assert resp.status_code == 201
    highlight = resp.json()
    assert highlight["selected_text"] == "transformers are great"
    # `page` is null on a rect that sits on the highlight's own page; it is only
    # filled in for a highlight that spans a page break.
    assert highlight["rects"] == [
        {"x": 10.0, "y": 20.0, "width": 30.0, "height": 5.0, "page": None}
    ]
    # a comment supplied while selecting becomes the highlight's first comment
    assert [c["body"] for c in highlight["comments"]] == ["key insight"]

    resp = client.get(f"/api/papers/{paper['id']}/highlights")
    assert len(resp.json()) == 1

    resp = client.patch(
        f"/api/papers/{paper['id']}/highlights/{highlight['id']}", json={"color": "#ff0000"}
    )
    assert resp.json()["color"] == "#ff0000"

    resp = client.delete(f"/api/papers/{paper['id']}/highlights/{highlight['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/papers/{paper['id']}/highlights").json() == []


def test_highlight_without_comment_is_optional(client):
    paper = _create_paper(client)
    resp = client.post(
        f"/api/papers/{paper['id']}/highlights",
        json={
            "page_number": 1,
            "selected_text": "some text",
            "rects": [{"x": 0.0, "y": 0.0, "width": 10.0, "height": 2.0}],
        },
    )
    assert resp.status_code == 201
    assert resp.json()["comments"] == []


def test_highlight_spanning_a_page_break_keeps_each_rect_page(client):
    paper = _create_paper(client)
    resp = client.post(
        f"/api/papers/{paper['id']}/highlights",
        json={
            "page_number": 2,
            "selected_text": "a sentence broken over the page break",
            "rects": [
                {"x": 10.0, "y": 90.0, "width": 60.0, "height": 2.0, "page": 2},
                {"x": 10.0, "y": 5.0, "width": 40.0, "height": 2.0, "page": 3},
            ],
        },
    )
    assert resp.status_code == 201
    assert [r["page"] for r in resp.json()["rects"]] == [2, 3]
    # and it survives the round trip through the database
    stored = client.get(f"/api/papers/{paper['id']}/highlights").json()[0]
    assert [r["page"] for r in stored["rects"]] == [2, 3]


def test_create_highlight_for_missing_paper_404(client):
    resp = client.post(
        "/api/papers/999/highlights",
        json={"page_number": 1, "selected_text": "x", "rects": []},
    )
    assert resp.status_code == 404


def test_multiple_comments_accumulate_in_order(client):
    paper = _create_paper(client)
    highlight = _create_highlight(client, paper["id"], comment="first")
    base = f"/api/papers/{paper['id']}/highlights/{highlight['id']}/comments"

    for body in ("second", "third"):
        assert client.post(base, json={"body": body}).status_code == 201

    listed = client.get(f"/api/papers/{paper['id']}/highlights").json()[0]
    assert [c["body"] for c in listed["comments"]] == ["first", "second", "third"]


def test_edit_and_delete_a_single_comment(client):
    paper = _create_paper(client)
    highlight = _create_highlight(client, paper["id"], comment="first")
    base = f"/api/papers/{paper['id']}/highlights/{highlight['id']}/comments"
    second = client.post(base, json={"body": "second"}).json()

    resp = client.patch(f"{base}/{second['id']}", json={"body": "second, revised"})
    assert resp.status_code == 200
    assert resp.json()["body"] == "second, revised"

    assert client.delete(f"{base}/{second['id']}").status_code == 204
    listed = client.get(f"/api/papers/{paper['id']}/highlights").json()[0]
    assert [c["body"] for c in listed["comments"]] == ["first"]


def test_comments_are_scoped_to_their_highlight(client):
    paper = _create_paper(client)
    mine = _create_highlight(client, paper["id"], comment="mine")
    other = _create_highlight(client, paper["id"], comment="other")
    comment_id = other["comments"][0]["id"]

    # a comment id from another highlight must not be reachable
    wrong = f"/api/papers/{paper['id']}/highlights/{mine['id']}/comments/{comment_id}"
    assert client.patch(wrong, json={"body": "hijacked"}).status_code == 404
    assert client.delete(wrong).status_code == 404


def test_blank_comments_are_rejected(client):
    paper = _create_paper(client)
    highlight = _create_highlight(client, paper["id"], comment=None)
    base = f"/api/papers/{paper['id']}/highlights/{highlight['id']}/comments"

    assert client.post(base, json={"body": "   "}).status_code == 400
    assert client.post("/api/papers/999/highlights/999/comments", json={"body": "x"}).status_code == 404


def test_deleting_a_highlight_removes_its_comments(client):
    paper = _create_paper(client)
    highlight = _create_highlight(client, paper["id"], comment="first")
    base = f"/api/papers/{paper['id']}/highlights/{highlight['id']}/comments"
    client.post(base, json={"body": "second"})

    assert client.delete(f"/api/papers/{paper['id']}/highlights/{highlight['id']}").status_code == 204

    from app.db import SessionLocal
    from app.models import Comment

    with SessionLocal() as db:
        assert db.query(Comment).count() == 0
