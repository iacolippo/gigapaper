import { pdfjsLib } from "./pdfjs.js";

export const DEFAULT_SCALE = 1.4;

/**
 * Renders a PDF into `container` and wires up highlight creation/rendering.
 *
 * Options:
 *   onSelect(pageNumber, rects, text, pageElement) — a finished text selection.
 *   highlights — an in-flight fetch; pass it so highlights can be painted page
 *     by page instead of waiting for the whole document.
 *   onPageReady(pageNumber) — that page is on screen and can be scrolled to.
 *   scale — starting zoom.
 *
 * Returns { rendering, renderHighlights(highlights), setScale(scale) }.
 */
export function renderPdf(container, url, { onSelect, highlights = null, onPageReady, scale = DEFAULT_SCALE } = {}) {
  container.innerHTML = "";
  const pageLayers = new Map();
  const pages = new Map(); // pageNumber -> the elements to redraw on a zoom
  let byPage = new Map();

  // On the container, not on each page: a selection dragged across a page break
  // ends its mouseup on a different page than it started on (or in the gap
  // between them), which a per-page listener would either miss or misattribute.
  container.addEventListener("mouseup", () => handleSelection(container, onSelect));

  const paintPage = (pageNumber) => {
    const layer = pageLayers.get(pageNumber);
    if (!layer) return;
    layer.clearHighlights();
    for (const { highlight, rects } of byPage.get(pageNumber) ?? []) {
      layer.addHighlight(highlight, rects);
    }
  };
  const paintAll = () => {
    for (const pageNumber of pageLayers.keys()) paintPage(pageNumber);
  };

  // The highlight fetch runs alongside the document load. Whichever finishes
  // first, each page gets its highlights the moment both exist.
  Promise.resolve(highlights ?? [])
    .then((fetched) => {
      byPage = groupByPage(fetched);
      paintAll();
    })
    .catch(() => {});

  // Returned synchronously so the caller holds a usable handle straight away:
  // highlights become clickable long before the last page has rendered.
  const rendering = (async () => {
    const pdf = await pdfjsLib.getDocument(url).promise;
    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
      const parts = await createPage(pdf, pageNumber, container);
      pages.set(pageNumber, parts);
      pageLayers.set(pageNumber, makeHighlightLayer(parts.highlightLayer));
      await drawPage(parts, scale);
      paintPage(pageNumber);
      onPageReady?.(pageNumber);
    }
    return pdf.numPages;
  })();

  // Zooming redraws pages that already exist, so it has to queue behind the
  // first render rather than fight it for the same canvases.
  let work = rendering;

  return {
    rendering,
    renderHighlights(fetched) {
      byPage = groupByPage(fetched);
      paintAll();
    },
    // Highlight rects are stored as percentages of their page, so the highlight
    // layers need no redrawing here — they scale with the page they sit in.
    setScale(next) {
      scale = next;
      work = work.then(async () => {
        for (const parts of pages.values()) await drawPage(parts, scale);
      });
      return work;
    },
  };
}

/**
 * Buckets highlights by the page each of their rects lives on. A highlight that
 * spans a page break contributes its own rects to each page it touches, so both
 * halves paint (and stay clickable) in their own page's layer.
 */
function groupByPage(highlights) {
  const byPage = new Map();
  for (const h of highlights) {
    const rectsByPage = new Map();
    for (const rect of h.rects) {
      const pageNumber = rect.page ?? h.page_number;
      const bucket = rectsByPage.get(pageNumber);
      if (bucket) bucket.push(rect);
      else rectsByPage.set(pageNumber, [rect]);
    }
    for (const [pageNumber, rects] of rectsByPage) {
      const bucket = byPage.get(pageNumber);
      if (bucket) bucket.push({ highlight: h, rects });
      else byPage.set(pageNumber, [{ highlight: h, rects }]);
    }
  }
  return byPage;
}

/** Builds a page's empty scaffolding; `drawPage` fills it at a given zoom. */
async function createPage(pdf, pageNumber, container) {
  const page = await pdf.getPage(pageNumber);

  const wrap = document.createElement("div");
  wrap.className = "pdf-page-wrap";
  wrap.dataset.pageNumber = String(pageNumber);
  container.appendChild(wrap);

  const canvas = document.createElement("canvas");
  wrap.appendChild(canvas);

  const textLayerDiv = document.createElement("div");
  textLayerDiv.className = "textLayer";
  wrap.appendChild(textLayerDiv);

  const highlightLayer = document.createElement("div");
  highlightLayer.className = "highlight-layer";
  wrap.appendChild(highlightLayer);

  return { page, wrap, canvas, textLayerDiv, highlightLayer };
}

/** (Re)paints one page at `scale`. Called again for every zoom change. */
async function drawPage({ page, wrap, canvas, textLayerDiv }, scale) {
  const viewport = page.getViewport({ scale });

  wrap.style.width = `${viewport.width}px`;
  wrap.style.height = `${viewport.height}px`;
  // PDF.js sizes the text layer and every span with
  // `calc(var(--scale-factor) * ...)`. Without this the calc is invalid, the
  // layer collapses to zero width, and its clipped spans can't be selected.
  wrap.style.setProperty("--scale-factor", String(scale));

  canvas.width = viewport.width;
  canvas.height = viewport.height;
  await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;

  textLayerDiv.innerHTML = ""; // a zoom re-lays every span out at the new size
  textLayerDiv.style.width = `${viewport.width}px`;
  textLayerDiv.style.height = `${viewport.height}px`;
  const textContent = await page.getTextContent();
  await new pdfjsLib.TextLayer({ textContentSource: textContent, container: textLayerDiv, viewport }).render();
}

/**
 * Renders an imported article as a single fixed-width page, so the same
 * selection and highlight machinery works on it. The width is fixed on
 * purpose: highlight rects are stored as percentages of the page, and a
 * reflowing column would move them.
 */
export function renderArticle(container, url, { onSelect, highlights = null, onPageReady } = {}) {
  container.innerHTML = "";
  let layer = null;
  let current = [];

  const paint = (fetched) => {
    current = fetched;
    if (!layer) return; // the page is still loading; painted on arrival
    layer.clearHighlights();
    for (const h of current) layer.addHighlight(h, h.rects);
  };

  container.addEventListener("mouseup", () => handleSelection(container, onSelect));

  const rendering = (async () => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Could not load article: ${response.status}`);
    const html = await response.text();

    const wrap = document.createElement("div");
    wrap.className = "pdf-page-wrap article-page";
    wrap.dataset.pageNumber = "1";
    container.appendChild(wrap);

    const body = document.createElement("article");
    body.className = "article-body";
    body.innerHTML = html;
    wrap.appendChild(body);

    const highlightLayer = document.createElement("div");
    highlightLayer.className = "highlight-layer";
    wrap.appendChild(highlightLayer);

    layer = makeHighlightLayer(highlightLayer);
    paint(current);
    onPageReady?.(1);
    return 1;
  })();

  Promise.resolve(highlights ?? []).then(paint).catch(() => {});

  // An article has no zoom of its own: it is already laid out as a column of
  // body text at a comfortable measure.
  return { rendering, renderHighlights: paint, setScale: null };
}

/**
 * Turns the live selection into per-page rects. Each rect is assigned to the
 * page it visually falls on, so a selection dragged across a page break yields
 * one highlight whose rects carry the page they belong to.
 */
function handleSelection(container, onSelect) {
  const selection = window.getSelection();
  const text = selection.toString().trim();
  if (!text || selection.rangeCount === 0 || !container.contains(selection.anchorNode)) return;

  const wraps = Array.from(container.querySelectorAll(".pdf-page-wrap")).map((wrap) => ({
    wrap,
    pageNumber: Number(wrap.dataset.pageNumber ?? 1),
    box: wrap.getBoundingClientRect(),
  }));

  const range = selection.getRangeAt(0);
  const rects = [];
  let lastWrap = null;
  for (const r of textRects(range)) {
    if (r.width <= 0 || r.height <= 0) continue;
    // Match on the rect's centre: a line box can overhang its page's border by
    // a hair, but never by half its own height.
    const midY = r.top + r.height / 2;
    const page = wraps.find(({ box }) => midY >= box.top && midY <= box.bottom);
    if (!page) continue;
    rects.push({ page: page.pageNumber, ...toPercentRect(r, page.box) });
    lastWrap = page.wrap;
  }

  if (rects.length === 0) return;
  // Drop the page selection before handing off: a caret in the comment box is
  // itself a document selection, so clearing afterwards would wipe it and the
  // box would look focused without being ready to type into.
  selection.removeAllRanges();
  // The highlight belongs to the page it starts on; the popover anchors to the
  // last rect, so it opens beside where the drag ended.
  onSelect(rects[0].page, rects, text, lastWrap);
}

/**
 * The line boxes of the selected text, and nothing else. Asking the range
 * itself for its rects would also hand back the boxes of whole elements it
 * encloses — once a selection crosses a page break that includes the page
 * wrappers, which would paint two entire pages in highlight colour.
 */
function textRects(range) {
  const root = range.commonAncestorContainer;
  const walker = document.createTreeWalker(
    root.nodeType === Node.TEXT_NODE ? root.parentNode : root,
    NodeFilter.SHOW_TEXT
  );
  const rects = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!range.intersectsNode(node)) continue;
    const part = document.createRange();
    part.selectNodeContents(node);
    if (node === range.startContainer) part.setStart(node, range.startOffset);
    if (node === range.endContainer) part.setEnd(node, range.endOffset);
    if (part.collapsed) continue;
    rects.push(...part.getClientRects());
  }
  return rects;
}

function toPercentRect(rect, wrapRect) {
  return {
    x: ((rect.left - wrapRect.left) / wrapRect.width) * 100,
    y: ((rect.top - wrapRect.top) / wrapRect.height) * 100,
    width: (rect.width / wrapRect.width) * 100,
    height: (rect.height / wrapRect.height) * 100,
  };
}

// How much of the stored colour to keep when painting it over the text. Enough
// to read as a highlight, light enough to read the words through.
const HIGHLIGHT_ALPHA = 0.45;

/**
 * The stored colour, made see-through.
 *
 * A highlight sits on top of the words: on a PDF the glyphs are pixels on the
 * canvas underneath, and on an article they are text underneath. Painting the
 * colour at full strength therefore hides what it highlights. `mix-blend-mode:
 * multiply` used to solve that, but WKWebView — the engine behind the desktop
 * app — reports support for it and then composites it as an opaque block,
 * burying the text. Translucency needs no blending and looks the same in every
 * engine.
 *
 * Unrecognised colour formats are passed through untouched: a highlight that
 * is too strong beats one that does not paint at all.
 */
function translucent(color) {
  const hex = /^#([\da-f]{3}|[\da-f]{6})$/i.exec(color?.trim() ?? "");
  if (!hex) return color;
  const digits = hex[1].length === 3 ? [...hex[1]].map((d) => d + d) : hex[1].match(/../g);
  const [r, g, b] = digits.map((pair) => parseInt(pair, 16));
  return `rgba(${r}, ${g}, ${b}, ${HIGHLIGHT_ALPHA})`;
}

function makeHighlightLayer(highlightLayer) {
  return {
    clearHighlights() {
      highlightLayer.innerHTML = "";
    },
    addHighlight(highlight, rects) {
      for (const rect of rects) {
        const div = document.createElement("div");
        const commented = (highlight.comments?.length ?? 0) > 0;
        div.className = "highlight-rect" + (commented ? " has-comment" : "");
        div.style.left = `${rect.x}%`;
        div.style.top = `${rect.y}%`;
        div.style.width = `${rect.width}%`;
        div.style.height = `${rect.height}%`;
        div.style.background = translucent(highlight.color);
        div.title = highlight.comments?.length
          ? highlight.comments.map((c) => c.body).join("\n\n")
          : highlight.selected_text;
        div.dataset.highlightId = highlight.id;
        highlightLayer.appendChild(div);
      }
    },
  };
}
