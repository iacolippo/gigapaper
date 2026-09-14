import { pdfjsLib } from "./pdfjs.js";

/**
 * Guesses a paper's title from its first page.
 *
 * Uploaded PDFs are named whatever the download left behind — `2504.15278v2`,
 * `paper (3)` — so the filename makes a poor library entry. On a paper the
 * title is reliably the largest run of text in the upper part of page one,
 * which beats the /Title metadata field: that is usually absent, and when it
 * is present it is as often the authoring tool's leftovers.
 *
 * Returns null when nothing convincing is found; the caller keeps the name it
 * already had.
 */
export async function guessTitle(data) {
  try {
    const pdf = await pdfjsLib.getDocument({ data }).promise;
    try {
      return fromFirstPage(await pdf.getPage(1)) ?? (await fromMetadata(pdf));
    } finally {
      pdf.destroy();
    }
  } catch {
    return null;
  }
}

const MIN_LENGTH = 6;
const MAX_LENGTH = 300;
// Lines within this much of the largest type count as part of the title, so a
// two-line title still reads as one even if the renderer rounds sizes.
const SIZE_TOLERANCE = 0.02;

async function fromFirstPage(page) {
  const { height: pageHeight } = page.getViewport({ scale: 1 });
  const content = await page.getTextContent();

  const items = [];
  for (const item of content.items) {
    const text = item.str.trim();
    if (!text) continue;
    const [a, b, c, d, , y] = item.transform;
    // Skip anything rotated — the arXiv stamp runs up the left margin in type
    // as large as the title, and it is not the title.
    if (Math.abs(b) > 0.01 || Math.abs(c) > 0.01) continue;
    // Titles sit in the top half; a large section heading further down is not
    // one, and neither is a figure caption.
    if (y < pageHeight * 0.5) continue;
    items.push({ text, size: Math.abs(d) || Math.abs(a), y, x: item.transform[4] });
  }
  if (items.length === 0) return null;

  const largest = Math.max(...items.map((i) => i.size));
  const title = items
    .filter((i) => i.size >= largest * (1 - SIZE_TOLERANCE))
    .sort((p, q) => q.y - p.y || p.x - q.x) // down the page, then across
    .map((i) => i.text)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();

  return acceptable(title) ? title : null;
}

async function fromMetadata(pdf) {
  const { info } = await pdf.getMetadata();
  const title = (info?.Title ?? "").replace(/\s+/g, " ").trim();
  // Word and LaTeX leave the source file's name behind; that is not a title.
  if (/\.(docx?|tex|dvi|pdf|indd)$/i.test(title)) return null;
  return acceptable(title) ? title : null;
}

function acceptable(title) {
  if (title.length < MIN_LENGTH || title.length > MAX_LENGTH) return false;
  return /\p{Letter}{3}/u.test(title); // reject page furniture like "1" or "©2025"
}
