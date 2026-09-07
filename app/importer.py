"""Import a web article as Markdown.

Fetches a URL, strips the page furniture down to the article body, and
converts it to Markdown, which is what gets stored on disk.
"""

import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx
import lxml.html
import markdown as markdown_lib
import trafilatura
from lxml_html_clean import Cleaner

from app import snapshots

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; gigapaper/0.1; +https://github.com/)"
TIMEOUT = 20.0
MAX_BYTES = 10 * 1024 * 1024

# Article HTML comes from an arbitrary site, so drop anything executable
# before it reaches the viewer.
_cleaner = Cleaner(
    scripts=True,
    javascript=True,
    embedded=True,
    frames=True,
    forms=True,
    style=True,
    inline_style=True,
    safe_attrs_only=True,
    safe_attrs=frozenset({"href", "src", "alt", "title"}),
)


class ImportError_(Exception):
    """A URL could not be turned into a readable document."""


def normalise_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ImportError_("Enter a URL to import.")
    if "://" not in url:
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ImportError_("Only http and https URLs can be imported.")
    if not parsed.netloc:
        raise ImportError_("That doesn't look like a URL.")
    return url


def fetch_article(
    url: str, asset_dir: Path | None = None, asset_url_prefix: str = ""
) -> tuple[str, str]:
    """Returns (title, markdown) for `url`.

    When `asset_dir` is given, script-drawn elements (interactive diagrams and
    the like) are photographed into it and swapped into the document as images,
    so they survive extraction instead of vanishing.
    """
    url = normalise_url(url)
    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise ImportError_(f"The site returned {exc.response.status_code}.") from exc
    except httpx.HTTPError as exc:
        raise ImportError_("Could not reach that URL.") from exc

    if len(response.content) > MAX_BYTES:
        raise ImportError_("That page is too large to import.")

    # Resolve relative image/link paths against the page they came from,
    # otherwise they resolve against gigapaper's own origin and 404.
    html = _prepare(response.text, str(response.url))
    if asset_dir is not None:
        html = _embed_snapshots(html, str(response.url), asset_dir, asset_url_prefix)
    body = trafilatura.extract(
        html, output_format="markdown", include_links=True, include_images=True
    )
    if not body or not body.strip():
        raise ImportError_("No readable article was found at that URL.")

    return _title_for(html, url), body


def render_html(md_text: str) -> str:
    """Renders stored Markdown to sanitised HTML for the viewer."""
    html = markdown_lib.markdown(
        md_text, extensions=["extra", "sane_lists", "smarty", "toc"]
    )
    return _cleaner.clean_html(_drop_non_images(f"<div>{html}</div>"))


def _prepare(html: str, base_url: str) -> str:
    """Fixes up markup that would otherwise survive extraction as junk."""
    try:
        tree = lxml.html.fromstring(html)
        _flatten_fragment_links(tree)
        tree.make_links_absolute(base_url, resolve_base_href=True)
        return lxml.html.tostring(tree, encoding="unicode")
    except Exception:  # noqa: BLE001 - fall back to the original markup
        return html


def _flatten_fragment_links(tree) -> None:
    """Replaces in-page links (``href="#fn1"``) with their own text.

    They point at anchors that do not survive extraction, and a footnote marker
    like ``<sup><a href="#fn1">1</a></sup>`` is otherwise turned into an image
    by the extractor — which then renders as a broken image.
    """
    for link in tree.xpath('//a[starts-with(@href, "#")]'):
        parent = link.getparent()
        if parent is None:
            continue
        text = (link.text_content() or "") + (link.tail or "")
        previous = link.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + text
        else:
            parent.text = (parent.text or "") + text
        parent.remove(link)


def _title_for(html: str, url: str) -> str:
    try:
        metadata = trafilatura.extract_metadata(html)
    except Exception:  # noqa: BLE001 - metadata is best-effort
        metadata = None
    if metadata and metadata.title:
        return metadata.title.strip()[:500]
    return urlparse(url).netloc or url


def _drop_non_images(html: str) -> str:
    """Removes ``<img>`` elements whose source cannot be an image.

    A page fragment or an .html document behind an ``<img>`` only ever renders
    as a broken image, so drop the element rather than show the reader a hole.
    """
    try:
        tree = lxml.html.fromstring(html)
    except Exception:  # noqa: BLE001 - leave questionable markup alone
        return html

    for image in tree.xpath("//img"):
        src = (image.get("src") or "").strip()
        path = urlparse(src).path.lower()
        if not src or src.startswith("#") or path.endswith((".html", ".htm")):
            image.drop_tree()
    return lxml.html.tostring(tree, encoding="unicode")


def _embed_snapshots(html: str, url: str, asset_dir: Path, url_prefix: str) -> str:
    """Replaces script-drawn elements with images of themselves.

    The swap happens before extraction so each picture keeps its place in the
    document, rather than being appended somewhere at the end.
    """
    try:
        captured = snapshots.capture(url, asset_dir)
    except Exception:
        log.warning("snapshotting %s failed; importing without it", url, exc_info=True)
        return html
    if not captured:
        return html

    try:
        tree = lxml.html.fromstring(html)
    except Exception:  # noqa: BLE001 - leave questionable markup alone
        return html

    # Resolve every element up front: replacing one removes it from the tree,
    # so re-querying afterwards would shift the indices of the rest.
    by_tag: dict[str, list] = {}
    for shot in captured:
        if shot.tag not in by_tag:
            by_tag[shot.tag] = tree.xpath(f"//{shot.tag}")

    for shot in captured:
        matches = by_tag[shot.tag]
        if shot.index >= len(matches):
            continue
        element = matches[shot.index]
        if element.getparent() is None:
            continue
        image = lxml.html.Element(
            "img",
            src=f"{url_prefix}/{shot.filename}",
            alt=f"{shot.tag} diagram from the original page",
        )
        # Wrap in a paragraph so the extractor treats it as its own block.
        holder = lxml.html.Element("p")
        holder.append(image)
        element.getparent().replace(element, holder)

    return lxml.html.tostring(tree, encoding="unicode")
