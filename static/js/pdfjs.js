// One place to load PDF.js and point it at its worker, so the reader, the
// thumbnails and the title reader can't drift apart on the worker path.
import * as pdfjsLib from "./vendor/pdf.min.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/js/vendor/pdf.worker.min.mjs";

export { pdfjsLib };
