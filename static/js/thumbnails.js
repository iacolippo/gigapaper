import * as pdfjsLib from "./vendor/pdf.min.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/js/vendor/pdf.worker.min.mjs";

const CACHE_PREFIX = "gigapaper:thumb:";
const WIDTH = 384; // 2x the ~192px card content width, for retina
const JPEG_QUALITY = 0.8;

// PDF.js pulls a lot of bytes per document; render one at a time so opening a
// folder of papers doesn't saturate the connection pool.
let queue = Promise.resolve();

/**
 * Renders page 1 of `url` to a JPEG data URL, memoised in localStorage under
 * `paperId`. Returns null if the PDF can't be read.
 */
export function getThumbnail(paperId, url) {
  const cached = readCache(paperId);
  if (cached) return Promise.resolve(cached);

  queue = queue.then(() => renderFirstPage(url)).catch(() => null);
  return queue.then((dataUrl) => {
    if (dataUrl) writeCache(paperId, dataUrl);
    return dataUrl;
  });
}

export function forgetThumbnail(paperId) {
  try {
    localStorage.removeItem(CACHE_PREFIX + paperId);
  } catch {
    // storage unavailable; nothing cached to forget
  }
}

async function renderFirstPage(url) {
  const pdf = await pdfjsLib.getDocument(url).promise;
  try {
    const page = await pdf.getPage(1);
    const base = page.getViewport({ scale: 1 });
    const viewport = page.getViewport({ scale: WIDTH / base.width });

    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff"; // JPEG has no alpha; avoid a black page behind the text
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    await page.render({ canvasContext: ctx, viewport }).promise;

    return canvas.toDataURL("image/jpeg", JPEG_QUALITY);
  } finally {
    pdf.destroy();
  }
}

function readCache(paperId) {
  try {
    return localStorage.getItem(CACHE_PREFIX + paperId);
  } catch {
    return null;
  }
}

function writeCache(paperId, dataUrl) {
  try {
    localStorage.setItem(CACHE_PREFIX + paperId, dataUrl);
  } catch {
    // quota exceeded or storage disabled: the thumbnail just re-renders next time
  }
}
