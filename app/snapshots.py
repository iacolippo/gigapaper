"""Snapshots of interactive, script-drawn page elements.

Extraction to Markdown keeps text, so a diagram that a page draws with
JavaScript leaves nothing behind. This renders the page once, at import, in a
headless browser and photographs those elements so the stored article still
shows them.

The browser runs only here — never when reading. A stored snapshot is a PNG.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# Custom elements (a hyphenated tag) and canvases are what pages use to draw
# themselves; plain <img> already survives extraction.
CANDIDATE_JS = """() => {
  const wanted = el => el.tagName.includes('-') || el.tagName === 'CANVAS';
  const out = [];
  for (const el of document.querySelectorAll('*')) {
    if (!wanted(el)) continue;
    const box = el.getBoundingClientRect();
    if (box.width < 120 || box.height < 80) continue;
    // Skip layout shells: a wrapper around prose is not a diagram. Text length
    // is no guide — a diagram carries plenty of labels — but paragraphs are.
    if (el.querySelectorAll('p, h1, h2, h3').length > 3) continue;
    // Keep the outermost widget; its inner parts came along with it.
    if (out.some(o => o.el.contains(el))) continue;
    out.push({el, tag: el.tagName.toLowerCase()});
  }
  return out.map(o => o.tag);
}"""

# Widgets lay themselves out to the space available, and some are wider than
# their own box (an inner scroller, or content that simply overflows). Before
# photographing one, let it size to its content so nothing is cut off.
UNCLIP_JS = """(el) => {
  const saved = [];
  const relax = (node, extra) => {
    saved.push([node, node.getAttribute('style')]);
    Object.assign(node.style, {overflow: 'visible', maxWidth: 'none'}, extra);
  };
  relax(el, {width: 'max-content'});
  for (const kid of el.querySelectorAll('*')) {
    const cs = getComputedStyle(kid);
    if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') relax(kid, {});
  }
  el.__gpRestore = () => {
    for (const [node, style] of saved) {
      if (style === null) node.removeAttribute('style');
      else node.setAttribute('style', style);
    }
  };
}"""

RECLIP_JS = """(el) => { if (el.__gpRestore) { el.__gpRestore(); delete el.__gpRestore; } }"""

LAUNCH_ATTEMPTS = ({}, {"channel": "chrome"}, {"channel": "msedge"})
PAGE_TIMEOUT = 30_000
SETTLE_MS = 2_500


@dataclass
class Snapshot:
    tag: str
    index: int  # nth element of that tag, in document order
    filename: str


def capture(url: str, out_dir: Path) -> list[Snapshot]:
    """Photographs script-drawn elements on `url`. Returns [] if it can't."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.info("playwright not installed; importing %s without snapshots", url)
        return []

    try:
        with sync_playwright() as p:
            browser = _launch(p)
            if browser is None:
                log.info("no usable browser; importing %s without snapshots", url)
                return []
            try:
                return _capture_with(browser, url, out_dir)
            finally:
                browser.close()
    except Exception:
        log.warning("snapshotting %s failed; importing without it", url, exc_info=True)
        return []


def _launch(playwright):
    for options in LAUNCH_ATTEMPTS:
        try:
            return playwright.chromium.launch(**options)
        except Exception:  # noqa: BLE001 - try the next browser
            log.debug("browser launch failed for %s", options or "bundled")
            continue
    return None


def _capture_with(browser, url: str, out_dir: Path) -> list[Snapshot]:
    # Roomy viewport: a widget that sizes to the space available should be
    # captured at a generous width rather than a cramped one.
    page = browser.new_page(viewport={"width": 1600, "height": 1200})
    page.goto(url, wait_until="load", timeout=PAGE_TIMEOUT)
    try:
        page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT)
    except Exception:  # noqa: BLE001 - a chatty page still renders fine
        log.debug("networkidle never reached for %s", url)
    page.wait_for_timeout(SETTLE_MS)

    tags = page.evaluate(CANDIDATE_JS)
    if not tags:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshots: list[Snapshot] = []
    seen: dict[str, int] = {}

    for tag in tags:
        index = seen.get(tag, 0)
        seen[tag] = index + 1
        element = page.locator(tag).nth(index)
        try:
            element.scroll_into_view_if_needed(timeout=5_000)
            page.wait_for_timeout(600)  # let a lazily drawn element settle
            element.evaluate(UNCLIP_JS)
            page.wait_for_timeout(250)  # reflow after unclipping
            filename = f"{len(snapshots):02d}-{tag}.png"
            try:
                element.screenshot(path=str(out_dir / filename), timeout=10_000)
            finally:
                element.evaluate(RECLIP_JS)
        except Exception:  # noqa: BLE001 - skip the ones that will not sit still
            log.info("could not snapshot %s[%d] on %s", tag, index, url)
            continue
        snapshots.append(Snapshot(tag=tag, index=index, filename=filename))

    return snapshots
