import { api } from "./api.js";
import { renderPdf, renderArticle, DEFAULT_SCALE } from "./viewer.js";
import { showPrompt, showConfirm, showAlert, isModalOpen } from "./modal.js";
import { getThumbnail, forgetThumbnail } from "./thumbnails.js";
import { guessTitle } from "./pdftitle.js";

const folderListEl = document.getElementById("folder-list");
const paperListEl = document.getElementById("paper-list");
const currentFolderTitleEl = document.getElementById("current-folder-title");
const paperListView = document.getElementById("paper-list-view");
const viewerView = document.getElementById("viewer-view");
const pdfContainer = document.getElementById("pdf-container");
const viewerTitleEl = document.getElementById("viewer-title");
const commentPopover = document.getElementById("comment-popover");
const commentInput = document.getElementById("comment-input");
const commentListEl = document.getElementById("comment-list");
const commentSaveBtn = document.getElementById("comment-save");
const commentDeleteBtn = document.getElementById("comment-delete");
const uploadLabelTextEl = document.getElementById("upload-label-text");
const paperCountEl = document.getElementById("paper-count");
const emptyStateEl = document.getElementById("empty-state");
const paperFilterEl = document.getElementById("paper-filter");
const viewerPagesEl = document.getElementById("viewer-pages");
const viewerSourceEl = document.getElementById("viewer-source");
const notesRailEl = document.getElementById("notes-rail");
const viewModeEl = document.getElementById("view-mode");
const originalViewEl = document.getElementById("original-view");
const originalFrameEl = document.getElementById("original-frame");
const notesToggleBtn = document.getElementById("notes-toggle");
const readToggleBtn = document.getElementById("read-toggle");
const readToggleTextEl = document.getElementById("read-toggle-text");
const mainEl = document.getElementById("main");
const zoomEl = document.getElementById("zoom");
const zoomLevelEl = document.getElementById("zoom-level");

const state = {
  folders: [], papers: [], currentFolderId: null, currentPaper: null,
  highlights: [], pendingSelection: null, editingHighlight: null, editingComment: null,
  viewerHandle: null, notesVisible: readNotesPreference(),
  paperFilter: readFilterPreference(), viewMode: "reader",
  zoom: readZoomPreference(), pendingRestore: null,
};

/**
 * The original view frames the live page, so its scripts run — that is the
 * point, it is how the interactive diagrams exist at all. Framing a remote
 * origin is ordinary cross-origin embedding: same-origin policy keeps it out
 * of this page. Framing our OWN origin would not be — `allow-scripts` plus
 * `allow-same-origin` on same-origin content lets a page rewrite its way out
 * of the sandbox — so refuse that case.
 */
function canFrame(url) {
  try {
    const target = new URL(url, location.href);
    if (!["http:", "https:"].includes(target.protocol)) return false;
    return target.origin !== location.origin;
  } catch {
    return false;
  }
}

function setViewMode(mode) {
  const paper = state.currentPaper;
  const original = mode === "original" && paper?.source_url && canFrame(paper.source_url);
  state.viewMode = original ? "original" : "reader";

  for (const button of viewModeEl.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.mode === state.viewMode));
  }

  renderZoom();

  if (state.viewMode === "original") {
    closePopover();
    if (originalFrameEl.dataset.src !== paper.source_url) {
      originalFrameEl.src = paper.source_url;
      originalFrameEl.dataset.src = paper.source_url;
    }
    originalViewEl.classList.remove("hidden");
    pdfContainer.classList.add("hidden");
    notesRailEl.classList.add("hidden");
  } else {
    originalViewEl.classList.add("hidden");
    pdfContainer.classList.remove("hidden");
    notesRailEl.classList.toggle("hidden", !state.notesVisible);
    scheduleNotesLayout();
  }
}

function clearOriginalView() {
  originalFrameEl.removeAttribute("src");
  delete originalFrameEl.dataset.src;
  originalViewEl.classList.add("hidden");
  pdfContainer.classList.remove("hidden");
  viewModeEl.classList.add("hidden");
  state.viewMode = "reader";
}

function readFilterPreference() {
  try {
    return localStorage.getItem("gigapaper:filter") === "unread" ? "unread" : "all";
  } catch {
    return "all";
  }
}

/**
 * Zoom is kept as a multiple of the reader's natural size, so the readout says
 * 100% at the size the pages were always drawn at rather than the 140% that
 * PDF.js scale happens to be.
 */
const ZOOM_STEPS = [0.5, 0.65, 0.8, 1, 1.25, 1.5, 1.75, 2];

function readZoomPreference() {
  try {
    const saved = Number(localStorage.getItem("gigapaper:zoom"));
    return ZOOM_STEPS.includes(saved) ? saved : 1;
  } catch {
    return 1;
  }
}

function renderZoom() {
  const pdf = state.currentPaper?.kind !== "markdown";
  zoomEl.classList.toggle("hidden", !pdf || state.viewMode === "original");
  zoomLevelEl.textContent = `${Math.round(state.zoom * 100)}%`;
  const index = ZOOM_STEPS.indexOf(state.zoom);
  zoomEl.querySelector("[data-zoom=out]").disabled = index <= 0;
  zoomEl.querySelector("[data-zoom=in]").disabled = index >= ZOOM_STEPS.length - 1;
}

async function stepZoom(direction) {
  const next = ZOOM_STEPS[ZOOM_STEPS.indexOf(state.zoom) + (direction === "in" ? 1 : -1)];
  if (next === undefined) return;
  state.zoom = next;
  try {
    localStorage.setItem("gigapaper:zoom", String(next));
  } catch {
    // storage unavailable; the zoom just won't be remembered
  }
  renderZoom();

  // Redrawing the pages changes their height, so hold the reader's place across
  // it rather than letting the paper jump.
  const here = capturePosition();
  await state.viewerHandle?.setScale?.(DEFAULT_SCALE * next);
  if (here) restorePosition(here);
  scheduleNotesLayout();
}

/**
 * Where the reader is, as the page at the top of the viewport plus how far into
 * that page it has scrolled. Stored that way rather than as a pixel offset so
 * it survives a zoom, a window resize, and re-rendering the document.
 */
function capturePosition() {
  const top = readingTop();
  let position = null;
  for (const wrap of pdfContainer.querySelectorAll(".pdf-page-wrap")) {
    const box = wrap.getBoundingClientRect();
    if (box.top > top) break; // this page starts below the fold; the previous one holds
    position = {
      page: Number(wrap.dataset.pageNumber),
      offset: Math.min(Math.max((top - box.top) / box.height, 0), 1),
    };
  }
  // Above the first page (the toolbar is in view): the top of page one.
  return position ?? (pdfContainer.firstElementChild ? { page: 1, offset: 0 } : null);
}

function restorePosition({ page, offset }) {
  const wrap = pdfContainer.querySelector(`.pdf-page-wrap[data-page-number="${page}"]`);
  if (!wrap) return false;
  const box = wrap.getBoundingClientRect();
  mainEl.scrollTop += box.top - readingTop() + offset * box.height;
  return true;
}

// The first line of paper you can actually read: the toolbar is sticky, so the
// top of the scroll box is behind it.
function readingTop() {
  const toolbar = document.getElementById("viewer-toolbar").getBoundingClientRect();
  return Math.max(toolbar.bottom, mainEl.getBoundingClientRect().top);
}

let saveTimer = null;
function schedulePositionSave() {
  // Nothing to record until the stored position has been applied — the view
  // switch itself scrolls, and that would overwrite it with the top of page one.
  if (!state.currentPaper || state.pendingRestore || state.viewMode !== "reader") return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(savePosition, 600);
}

function savePosition() {
  clearTimeout(saveTimer);
  const paper = state.currentPaper;
  const here = paper && !state.pendingRestore ? capturePosition() : null;
  if (!here) return;
  paper.last_page = here.page;
  paper.last_offset = here.offset;
  api.savePosition(paper.id, here.page, here.offset).catch(() => {});
}

mainEl.addEventListener("scroll", schedulePositionSave, { passive: true });

// A long document reaches the stored page seconds after it opens. If the reader
// has already started somewhere else by then, they have chosen a place — don't
// haul them off it.
for (const event of ["wheel", "mousedown", "keydown", "touchstart"]) {
  window.addEventListener(event, () => { state.pendingRestore = null; }, { passive: true });
}

const NOTE_GAP = 8;

function readNotesPreference() {
  try {
    return localStorage.getItem("gigapaper:notes") === "on";
  } catch {
    return false;
  }
}

function writeNotesPreference(on) {
  try {
    localStorage.setItem("gigapaper:notes", on ? "on" : "off");
  } catch {
    // storage unavailable; the toggle just won't be remembered
  }
}

/**
 * Margin notes: one card per highlight, parked beside the highlight it belongs
 * to. Cards are absolutely positioned against the page column, so the offsets
 * are recomputed whenever the pages themselves move — which they do as the
 * document renders page by page.
 */
function renderNotes() {
  notesRailEl.classList.toggle("hidden", !state.notesVisible);
  notesToggleBtn.setAttribute("aria-pressed", String(state.notesVisible));
  notesRailEl.innerHTML = "";
  if (!state.notesVisible) return;

  const ordered = [...state.highlights].sort(
    (a, b) => a.page_number - b.page_number || a.id - b.id
  );
  for (const highlight of ordered) {
    notesRailEl.appendChild(makeNote(highlight));
  }
  layoutNotes();
}

function makeNote(highlight) {
  const note = document.createElement("article");
  note.className = "note";
  note.dataset.highlightId = highlight.id;

  const page = document.createElement("span");
  page.className = "label note-page";
  page.textContent = `Page ${highlight.page_number}`;
  note.appendChild(page);

  if (highlight.comments.length === 0) {
    const empty = document.createElement("p");
    empty.className = "note-empty";
    empty.textContent = "No comment yet";
    note.appendChild(empty);
  }
  for (const comment of highlight.comments) {
    const body = document.createElement("p");
    body.className = "note-comment";
    body.textContent = comment.body;
    note.appendChild(body);
  }

  note.addEventListener("click", () => openHighlight(highlight.id, note));
  note.addEventListener("mouseenter", () => linkHighlight(highlight.id, true));
  note.addEventListener("mouseleave", () => linkHighlight(highlight.id, false));
  return note;
}

function linkHighlight(highlightId, on) {
  for (const rect of pdfContainer.querySelectorAll(`[data-highlight-id="${highlightId}"]`)) {
    rect.classList.toggle("linked", on);
  }
}

function layoutNotes() {
  if (!state.notesVisible) return;
  const containerTop = pdfContainer.getBoundingClientRect().top;

  const anchored = [];
  const unplaced = [];
  for (const note of notesRailEl.children) {
    const rect = pdfContainer.querySelector(`[data-highlight-id="${note.dataset.highlightId}"]`);
    if (rect) anchored.push({ note, wanted: rect.getBoundingClientRect().top - containerTop });
    else unplaced.push(note);
  }

  // Order by where the highlight actually sits. Creation order is not document
  // order — on a single-page article every highlight shares a page number, so
  // sorting by id would push a late note made near the top below an early one
  // made near the bottom.
  anchored.sort((a, b) => a.wanted - b.wanted);

  let previousBottom = 0;
  for (const { note, wanted } of anchored) {
    const top = Math.max(wanted, previousBottom + NOTE_GAP);
    note.style.top = `${top}px`;
    previousBottom = top + note.offsetHeight;
  }
  // Pages that haven't rendered yet have nothing to anchor to; park these
  // below and re-place them once their page arrives.
  for (const note of unplaced) {
    const top = previousBottom + NOTE_GAP;
    note.style.top = `${top}px`;
    previousBottom = top + note.offsetHeight;
  }
}

let layoutQueued = false;
function scheduleNotesLayout() {
  if (layoutQueued) return;
  layoutQueued = true;
  requestAnimationFrame(() => {
    layoutQueued = false;
    layoutNotes();
  });
}

// Pages append as they render and the column grows; keep the notes with them.
const notesObserver = new ResizeObserver(scheduleNotesLayout);
window.addEventListener("resize", scheduleNotesLayout);

async function refreshFolders() {
  state.folders = await api.listFolders();
  renderFolders();
}

function renderFolders() {
  folderListEl.innerHTML = "";
  folderListEl.appendChild(makeFolderItem({ id: null, name: "All papers" }));
  for (const folder of state.folders) folderListEl.appendChild(makeFolderItem(folder));
}

function makeFolderItem(folder) {
  const li = document.createElement("li");
  li.className = folder.id === state.currentFolderId ? "active" : "";
  li.innerHTML = `<span class="folder-name"></span><span class="folder-actions">${
    folder.id != null ? '<button data-action="rename" title="Rename folder">✎</button><button data-action="delete" title="Delete folder">✕</button>' : ""
  }</span><span class="label folder-count"></span>`;
  li.querySelector(".folder-name").textContent = folder.name;
  li.querySelector(".folder-count").textContent = String(papersInFolder(folder.id).length).padStart(2, "0");
  li.addEventListener("click", (e) => {
    if (e.target.dataset.action) return handleFolderAction(e.target.dataset.action, folder);
    selectFolder(folder.id);
  });
  return li;
}

async function handleFolderAction(action, folder) {
  if (action === "rename") {
    const name = await showPrompt("Rename folder", folder.name);
    if (name) await api.renameFolder(folder.id, name);
  } else if (action === "delete") {
    const ok = await showConfirm(`Delete folder "${folder.name}"? Papers inside will become unfiled.`);
    if (!ok) return;
    await api.deleteFolder(folder.id);
    if (state.currentFolderId === folder.id) state.currentFolderId = null;
  }
  await refreshFolders();
  await refreshPapers();
}

function selectFolder(folderId) {
  // Picking a folder is a navigation: leave whatever is open and show it.
  if (state.currentPaper) backToList();
  state.currentFolderId = folderId;
  renderFolders();
  refreshPapers();
}

async function refreshPapers() {
  // Fetch the whole library once: the same list feeds the grid and the
  // per-folder counts in the rail.
  state.papers = await api.listPapers();
  renderFolders();

  const folder = state.folders.find((f) => f.id === state.currentFolderId);
  currentFolderTitleEl.textContent = folder ? folder.name : "All papers";
  renderVisiblePapers();
}

// Sidebar counts stay as folder totals; only the grid follows the filter.
function papersInFolder(folderId) {
  if (folderId == null) return state.papers;
  return state.papers.filter((p) => p.folder_id === folderId);
}

function visiblePapers() {
  const papers = papersInFolder(state.currentFolderId);
  if (state.paperFilter === "unread") return papers.filter((p) => p.read_at == null);
  return papers;
}

function renderVisiblePapers() {
  const unreadOnly = state.paperFilter === "unread";
  const papers = visiblePapers();

  for (const button of paperFilterEl.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.filter === state.paperFilter));
  }

  paperCountEl.textContent = unreadOnly
    ? `${papers.length} unread`
    : `${papers.length} ${papers.length === 1 ? "document" : "documents"}`;

  emptyStateEl.textContent = unreadOnly
    ? "Nothing unread here. Every paper in this view is marked read."
    : "No papers here yet. Import a PDF to start reading.";
  emptyStateEl.classList.toggle("hidden", papers.length > 0);

  renderPapers(papers);
}

function renderPapers(papers) {
  paperListEl.innerHTML = "";
  for (const paper of papers) paperListEl.appendChild(makePaperItem(paper));
}

function makePaperItem(paper) {
  const li = document.createElement("li");
  const folderOptions = [`<option value="">Unfiled</option>`]
    .concat(state.folders.map((f) => `<option value="${f.id}" ${f.id === paper.folder_id ? "selected" : ""}>${f.name}</option>`))
    .join("");
  const isArticle = paper.kind === "markdown";
  li.innerHTML = `<div class="paper-thumb${isArticle ? " article" : ""}"><img alt="" /><div class="thumb-text"></div></div>` +
    `<button class="paper-rename" title="Rename paper">✎</button>` +
    `<button class="paper-delete" title="Delete paper">✕</button>` +
    `<div class="paper-meta"><span class="paper-title"></span>` +
    `<span class="label paper-source"></span>` +
    `<span class="label read-flag">✓ Read</span>` +
    `<select title="Move to folder">${folderOptions}</select></div>`;
  li.querySelector(".paper-title").textContent = paper.title;
  li.querySelector(".paper-title").title = paper.title;
  li.querySelector(".paper-source").textContent = isArticle ? hostOf(paper.source_url) : "PDF";
  li.classList.toggle("read", paper.read_at != null);
  li.querySelector(".paper-delete").addEventListener("click", () => deletePaper(paper));
  li.querySelector(".paper-rename").addEventListener("click", () => renamePaper(paper));
  const thumb = li.querySelector(".paper-thumb");
  thumb.addEventListener("click", () => openPaper(paper));
  li.querySelector("span.paper-title").addEventListener("click", () => openPaper(paper));
  li.querySelector("select").addEventListener("change", async (e) => {
    await api.movePaper(paper.id, e.target.value ? Number(e.target.value) : null);
    await refreshPapers();
  });
  thumb.dataset.paperId = paper.id;
  thumb.dataset.kind = paper.kind;
  thumbObserver.observe(thumb);
  return li;
}

// Thumbnails are rendered from the PDF itself, so only pay for the cards the
// user can actually see.
const thumbObserver = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    thumbObserver.unobserve(entry.target);
    loadThumbnail(entry.target);
  }
}, { rootMargin: "200px" });

async function loadThumbnail(thumb) {
  const paperId = Number(thumb.dataset.paperId);

  // Articles have no page to render, so preview their opening text instead.
  if (thumb.dataset.kind === "markdown") {
    const excerpt = await fetchExcerpt(paperId);
    if (!thumb.isConnected) return;
    if (excerpt) {
      thumb.querySelector(".thumb-text").textContent = excerpt;
      thumb.classList.add("loaded");
    } else {
      thumb.classList.add("failed");
    }
    return;
  }

  const dataUrl = await getThumbnail(paperId, api.paperFileUrl(paperId));
  if (!thumb.isConnected) return;
  if (dataUrl) {
    thumb.querySelector("img").src = dataUrl;
    thumb.classList.add("loaded");
  } else {
    thumb.classList.add("failed");
  }
}

async function fetchExcerpt(paperId) {
  try {
    const response = await fetch(api.paperFileUrl(paperId));
    if (!response.ok) return null;
    const md = await response.text();
    return md
      .replace(/```[\s\S]*?```/g, "")   // fenced code reads as noise at 8px
      .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
      .replace(/^#.*$/gm, "")
      .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
      .replace(/[*_`>#]/g, "")
      .split(/\n\s*\n/)
      .map((block) => block.replace(/\s+/g, " ").trim())
      .filter((block) => block.length > 40)
      .join("\n\n")
      .slice(0, 700);
  } catch {
    return null;
  }
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "Article";
  }
}

async function renamePaper(paper) {
  const title = await showPrompt("Rename paper", paper.title);
  if (!title || title === paper.title) return;
  await api.renamePaper(paper.id, title);
  if (state.currentPaper?.id === paper.id) viewerTitleEl.textContent = title;
  await refreshPapers();
}

async function deletePaper(paper) {
  const ok = await showConfirm(`Delete "${paper.title}"? This also removes its highlights.`);
  if (!ok) return;
  await api.deletePaper(paper.id);
  forgetThumbnail(paper.id);
  await refreshPapers();
}

async function openPaper(paper) {
  state.currentPaper = paper;
  paperListView.classList.add("hidden");
  viewerView.classList.remove("hidden");
  viewerTitleEl.textContent = paper.title;
  renderReadToggle();
  viewerPagesEl.textContent = "";
  viewerSourceEl.textContent = "";
  viewerSourceEl.removeAttribute("href");

  // Start the highlights request before rendering: the renderer paints each
  // page as soon as it has both, so they no longer wait for the last page.
  const pendingHighlights = api.listHighlights(paper.id).catch(() => []);
  pendingHighlights.then((highlights) => {
    if (state.currentPaper !== paper) return;
    state.highlights = highlights;
    renderNotes();
  });
  notesObserver.observe(pdfContainer);

  clearOriginalView();
  viewModeEl.classList.toggle("hidden", !(paper.source_url && canFrame(paper.source_url)));
  renderZoom();

  // Pick reading up where it was left. Held until the page it names has
  // rendered, which is also what keeps the scroll from being saved over.
  state.pendingRestore = paper.last_page ? { page: paper.last_page, offset: paper.last_offset ?? 0 } : null;
  mainEl.scrollTop = 0;

  const options = { onSelect: onTextSelected, highlights: pendingHighlights, onPageReady };
  if (paper.kind === "markdown") {
    state.viewerHandle = renderArticle(pdfContainer, api.paperHtmlUrl(paper.id), options);
    if (paper.source_url) {
      viewerSourceEl.textContent = hostOf(paper.source_url);
      viewerSourceEl.href = paper.source_url;
    }
  } else {
    state.viewerHandle = renderPdf(pdfContainer, api.paperFileUrl(paper.id), {
      ...options,
      scale: DEFAULT_SCALE * state.zoom,
    });
  }

  try {
    const numPages = await state.viewerHandle.rendering;
    // The reader may have moved on while the document was still rendering.
    if (state.currentPaper !== paper) return;
    if (paper.kind !== "markdown") viewerPagesEl.textContent = `${numPages} pages`;
  } catch (error) {
    if (state.currentPaper === paper) await showAlert(error.message);
  } finally {
    // A stored page past the end of a document (it was replaced, or the file
    // changed) would otherwise block saving for the rest of the session.
    if (state.currentPaper === paper) state.pendingRestore = null;
  }
}

// Each page arrives on screen: place the notes beside it, and if this is the
// page the reader was last on, scroll there.
function onPageReady(pageNumber) {
  const pending = state.pendingRestore;
  if (pending && pageNumber >= pending.page) {
    state.pendingRestore = null;
    restorePosition(pending);
  }
  scheduleNotesLayout();
}

async function refreshHighlights() {
  const paper = state.currentPaper;
  const highlights = await api.listHighlights(paper.id);
  if (state.currentPaper !== paper) return;
  state.highlights = highlights;
  state.viewerHandle?.renderHighlights(highlights);
  renderNotes();
}

// Delegated, because highlights are painted page by page as rendering
// progresses; there is no single moment when they all exist to be wired.
pdfContainer.addEventListener("click", (e) => {
  const rect = e.target.closest(".highlight-rect");
  if (rect) openHighlight(rect.dataset.highlightId, rect);
});

const POPOVER_GAP = 10;
const POPOVER_MARGIN = 12;

// A fresh selection: write a first comment and save it as a new highlight.
function onTextSelected(pageNumber, rects, text, pageElement) {
  const last = rects[rects.length - 1];
  const page = pageElement.getBoundingClientRect();
  state.pendingSelection = { pageNumber, rects, text };
  state.editingHighlight = null;
  state.editingComment = null;
  state.anchor = {
    left: page.left + (last.x / 100) * page.width,
    top: page.top + (last.y / 100) * page.height,
    height: (last.height / 100) * page.height,
  };
  renderPopover();
}

// An existing highlight: read its comments, add another, or remove it.
function openHighlight(highlightId, element) {
  const highlight = state.highlights.find((h) => String(h.id) === String(highlightId));
  if (!highlight) return;
  const box = element.getBoundingClientRect();
  state.pendingSelection = null;
  state.editingHighlight = highlight;
  state.editingComment = null;
  state.anchor = { left: box.left, top: box.top, height: box.height };
  renderPopover();
}

function renderPopover({ keepDraft = false } = {}) {
  const highlight = state.editingHighlight;
  const comments = highlight?.comments ?? [];

  renderComments(comments);
  commentListEl.classList.toggle("hidden", comments.length === 0);
  commentDeleteBtn.classList.toggle("hidden", !highlight);

  if (state.editingComment) {
    commentSaveBtn.textContent = "Save comment";
    commentInput.placeholder = "Edit this comment";
  } else if (highlight) {
    commentSaveBtn.textContent = "Add comment";
    commentInput.placeholder = comments.length ? "Add another comment" : "Add a comment";
  } else {
    commentSaveBtn.textContent = "Save highlight";
    commentInput.placeholder = "Add a comment (optional)";
  }

  if (!keepDraft) {
    commentInput.value = state.editingComment ? state.editingComment.body : "";
  }

  commentPopover.classList.remove("hidden");
  positionPopover(state.anchor);
  // The selection is cleared before the popover opens, so the caret is free to
  // land here and the user can type straight away.
  commentInput.focus();
  commentInput.setSelectionRange(commentInput.value.length, commentInput.value.length);
}

function renderComments(comments) {
  commentListEl.innerHTML = "";
  for (const comment of comments) {
    const li = document.createElement("li");
    li.innerHTML =
      `<p class="comment-body"></p>` +
      `<div class="comment-actions">` +
      `<span class="label comment-date"></span>` +
      `<button data-action="edit" title="Edit comment">✎</button>` +
      `<button data-action="delete" title="Delete comment">✕</button>` +
      `</div>`;
    li.querySelector(".comment-body").textContent = comment.body;
    li.querySelector(".comment-date").textContent = formatDate(comment.created_at);
    li.classList.toggle("editing", state.editingComment?.id === comment.id);
    li.querySelector("[data-action=edit]").addEventListener("click", () => {
      state.editingComment = comment;
      renderPopover();
    });
    li.querySelector("[data-action=delete]").addEventListener("click", () => removeComment(comment));
    commentListEl.appendChild(li);
  }
}

function formatDate(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

function closePopover() {
  commentPopover.classList.add("hidden");
  state.pendingSelection = null;
  state.editingHighlight = null;
  state.editingComment = null;
}

/**
 * Places the popover just under its anchor, in viewport coordinates — the paper
 * scrolls inside #main rather than with the window, so nothing else is stable.
 */
function positionPopover(anchor) {
  const popover = commentPopover.getBoundingClientRect();

  let left = anchor.left;
  let top = anchor.top + anchor.height + POPOVER_GAP;

  // Flip above the anchor when there is no room below it.
  if (top + popover.height > window.innerHeight - POPOVER_MARGIN) {
    const above = anchor.top - popover.height - POPOVER_GAP;
    top = above >= POPOVER_MARGIN ? above : window.innerHeight - popover.height - POPOVER_MARGIN;
  }
  left = Math.min(Math.max(left, POPOVER_MARGIN), window.innerWidth - popover.width - POPOVER_MARGIN);
  // Both edges, not just the top: an anchor that has scrolled off the bottom
  // would otherwise put "above the anchor" off the bottom of the screen too.
  top = Math.min(Math.max(top, POPOVER_MARGIN), window.innerHeight - popover.height - POPOVER_MARGIN);

  commentPopover.style.left = `${left}px`;
  commentPopover.style.top = `${top}px`;
}

async function saveHighlight() {
  const body = commentInput.value.trim();
  const paperId = state.currentPaper.id;

  if (state.editingComment) {
    if (!body) return; // an empty edit is a no-op; use ✕ to remove a comment
    await api.editComment(paperId, state.editingHighlight.id, state.editingComment.id, body);
    state.editingComment = null;
    await reopenHighlight();
  } else if (state.editingHighlight) {
    if (!body) return;
    await api.addComment(paperId, state.editingHighlight.id, body);
    await reopenHighlight();
  } else if (state.pendingSelection) {
    const { pageNumber, rects, text } = state.pendingSelection;
    await api.createHighlight(paperId, {
      page_number: pageNumber,
      selected_text: text,
      rects,
      comment: body || null,
    });
    closePopover();
    await refreshHighlights();
  }
}

async function removeComment(comment) {
  await api.deleteComment(state.currentPaper.id, state.editingHighlight.id, comment.id);
  if (state.editingComment?.id === comment.id) state.editingComment = null;
  await reopenHighlight();
}

// Reload the highlight so the popover shows the comments the server now holds.
async function reopenHighlight() {
  const highlightId = state.editingHighlight.id;
  await refreshHighlights();
  const fresh = state.highlights.find((h) => h.id === highlightId);
  if (!fresh) return closePopover();
  state.editingHighlight = fresh;
  renderPopover();
}

async function deleteOpenHighlight() {
  const highlight = state.editingHighlight;
  if (!highlight) return;
  closePopover();
  await api.deleteHighlight(state.currentPaper.id, highlight.id);
  await refreshHighlights();
}

function backToList() {
  savePosition(); // before the pages go away and there is nothing to measure
  viewerView.classList.add("hidden");
  paperListView.classList.remove("hidden");
  closePopover(); // also clears the pending selection and any highlight being edited
  clearOriginalView();
  notesObserver.unobserve(pdfContainer);
  notesRailEl.innerHTML = "";
  pdfContainer.innerHTML = "";
  state.highlights = [];
  state.currentPaper = null;
  state.viewerHandle = null;
  state.pendingRestore = null;
}

document.getElementById("new-folder-btn").addEventListener("click", async () => {
  const name = await showPrompt("Folder name");
  if (!name) return;
  await api.createFolder(name);
  await refreshFolders();
});

document.getElementById("upload-input").addEventListener("change", async (e) => {
  const files = Array.from(e.target.files);
  e.target.value = "";
  if (files.length === 0) return;
  await uploadPapers(files);
});

async function uploadPapers(files) {
  const failed = [];
  // Sequential: SQLite takes one writer at a time, and it keeps the progress
  // count honest.
  for (const [index, file] of files.entries()) {
    setUploadStatus(files.length > 1 ? `Importing ${index + 1}/${files.length}…` : "Importing…");
    try {
      const paper = await api.uploadPaper(file, state.currentFolderId);
      await applyDetectedTitle(paper, file);
    } catch {
      failed.push(file.name);
    }
  }
  setUploadStatus(null);
  await refreshPapers();
  if (failed.length > 0) {
    await showAlert(`Could not import ${failed.length} file(s): ${failed.join(", ")}`);
  }
}

/**
 * Names a freshly imported PDF after its own title page. The filename a paper
 * arrives with is usually the download's — `2504.15278v2` — which makes for a
 * library you can't read. Failing to find one is not a failed import: the paper
 * keeps its filename and can be renamed by hand.
 */
async function applyDetectedTitle(paper, file) {
  try {
    const title = await guessTitle(await file.arrayBuffer());
    if (title && title !== paper.title) await api.renamePaper(paper.id, title);
  } catch {
    // keep the filename
  }
}

function setUploadStatus(text) {
  uploadLabelTextEl.textContent = text ?? "+ Import PDFs";
  document.getElementById("upload-label").classList.toggle("busy", text != null);
}

document.getElementById("import-url-btn").addEventListener("click", async () => {
  const url = await showPrompt("Paste a URL to import as an article");
  if (!url) return;
  setUploadStatus("Fetching…");
  try {
    await api.importPaperFromUrl(url, state.currentFolderId);
  } catch (error) {
    await showAlert(error.message);
  } finally {
    setUploadStatus(null);
    await refreshPapers();
  }
});

function renderReadToggle() {
  const read = state.currentPaper?.read_at != null;
  readToggleBtn.setAttribute("aria-pressed", String(read));
  readToggleTextEl.textContent = read ? "Read" : "Mark as read";
}

readToggleBtn.addEventListener("click", async () => {
  const paper = state.currentPaper;
  if (!paper) return;
  const updated = await api.setPaperRead(paper.id, paper.read_at == null);

  // Record it whatever happened meanwhile: the reply can land after the reader
  // has already left the paper, and the card must still show the new state.
  const stale = state.papers.findIndex((p) => p.id === updated.id);
  if (stale !== -1) state.papers[stale] = updated;
  renderVisiblePapers();

  // Only the toolbar depends on this still being the open paper.
  if (state.currentPaper?.id === updated.id) {
    state.currentPaper = updated;
    renderReadToggle();
  }
});

zoomEl.addEventListener("click", (e) => {
  const direction = e.target.dataset.zoom;
  if (direction) stepZoom(direction);
});

viewModeEl.addEventListener("click", (e) => {
  const mode = e.target.dataset.mode;
  if (mode && mode !== state.viewMode) setViewMode(mode);
});

paperFilterEl.addEventListener("click", (e) => {
  const filter = e.target.dataset.filter;
  if (!filter || filter === state.paperFilter) return;
  state.paperFilter = filter;
  try {
    localStorage.setItem("gigapaper:filter", filter);
  } catch {
    // storage unavailable; the choice just won't be remembered
  }
  renderVisiblePapers();
});

notesToggleBtn.addEventListener("click", () => {
  state.notesVisible = !state.notesVisible;
  writeNotesPreference(state.notesVisible);
  renderNotes();
});

document.getElementById("back-btn").addEventListener("click", backToList);
document.getElementById("comment-save").addEventListener("click", saveHighlight);
document.getElementById("comment-cancel").addEventListener("click", closePopover);
commentDeleteBtn.addEventListener("click", deleteOpenHighlight);

/**
 * Escape backs out one layer at a time: the comment popover if it is open,
 * otherwise the paper itself. Owned here rather than on the popover so a single
 * press can't close the popover and leave the paper on its way up.
 */
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || isModalOpen()) return;
  if (!commentPopover.classList.contains("hidden")) {
    e.preventDefault();
    closePopover();
  } else if (!viewerView.classList.contains("hidden")) {
    e.preventDefault();
    backToList();
  }
});

// Keyboard shortcuts, bound to the whole popover so they work wherever focus is.
commentPopover.addEventListener("keydown", (e) => {
  // Enter saves; Shift+Enter still starts a new line in the comment.
  if (e.key === "Enter" && !e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) {
    e.preventDefault();
    saveHighlight();
    return;
  }

  // Delete removes the highlight, but only with an empty box — while there is
  // text to edit it has to stay an ordinary text-editing key. Backspace counts:
  // on a Mac that is the key labelled "delete", and it is a no-op when empty.
  const deleteKey = e.key === "Delete" || e.key === "Backspace";
  if (deleteKey && state.editingHighlight && commentInput.value === "") {
    e.preventDefault();
    deleteOpenHighlight();
  }
});

renderNotes(); // reflect the remembered toggle state before anything is open
await refreshFolders();
await refreshPapers();
