/**
 * PDF.js viewer with toolbar, lazy rendering, and progress saving.
 */

export function initPdfViewer(options) {
  const { url, containerId, initialPage = 1, progressUrl, csrfToken } = options;

  const container = document.getElementById(containerId);
  const pageInput = document.getElementById("pdf-page-input");
  const pageCountEl = document.getElementById("pdf-page-count");
  if (!container) return;

  let pdfDoc = null;
  let currentPage = initialPage;
  let scale = 1.25;
  let fitMode = null;
  let saveTimer = null;

  const pdfjsLib = window["pdfjs-dist/build/pdf"];
  if (pdfjsLib) {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.worker.min.mjs";
  }

  async function loadPdf() {
    const mod = await import(
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.min.mjs"
    );
    mod.GlobalWorkerOptions.workerSrc =
      "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.8.69/pdf.worker.min.mjs";
    pdfDoc = await mod.getDocument(url).promise;
    if (pageCountEl) pageCountEl.textContent = `/ ${pdfDoc.numPages}`;
    if (pageInput) {
      pageInput.max = pdfDoc.numPages;
      pageInput.value = Math.min(currentPage, pdfDoc.numPages);
    }
    await renderPage(currentPage);
  }

  async function renderPage(num) {
    if (!pdfDoc) return;
    currentPage = Math.max(1, Math.min(num, pdfDoc.numPages));
    if (pageInput) pageInput.value = currentPage;

    const page = await pdfDoc.getPage(currentPage);
    let viewport;
    if (fitMode === "width") {
      const base = page.getViewport({ scale: 1 });
      scale = container.clientWidth / base.width;
      viewport = page.getViewport({ scale });
    } else if (fitMode === "page") {
      const base = page.getViewport({ scale: 1 });
      scale = Math.min(
        container.clientWidth / base.width,
        container.clientHeight / base.height,
      );
      viewport = page.getViewport({ scale });
    } else {
      viewport = page.getViewport({ scale });
    }

    container.innerHTML = "";
    const canvas = document.createElement("canvas");
    canvas.className = "learning-pdf-page";
    canvas.height = viewport.height;
    canvas.width = viewport.width;
    container.appendChild(canvas);
    await page.render({ canvasContext: canvas.getContext("2d"), viewport })
      .promise;
    scheduleSave();
  }

  function scheduleSave() {
    if (!progressUrl) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      const body = new FormData();
      body.append("page", String(currentPage));
      fetch(progressUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        body,
      });
    }, 500);
  }

  document
    .getElementById("pdf-prev")
    ?.addEventListener("click", () => renderPage(currentPage - 1));
  document
    .getElementById("pdf-next")
    ?.addEventListener("click", () => renderPage(currentPage + 1));
  pageInput?.addEventListener("change", () =>
    renderPage(parseInt(pageInput.value, 10) || 1),
  );
  document.getElementById("pdf-zoom-in")?.addEventListener("click", () => {
    fitMode = null;
    scale *= 1.2;
    renderPage(currentPage);
  });
  document.getElementById("pdf-zoom-out")?.addEventListener("click", () => {
    fitMode = null;
    scale /= 1.2;
    renderPage(currentPage);
  });
  document.getElementById("pdf-fit-width")?.addEventListener("click", () => {
    fitMode = "width";
    renderPage(currentPage);
  });
  document.getElementById("pdf-fit-page")?.addEventListener("click", () => {
    fitMode = "page";
    renderPage(currentPage);
  });
  document.getElementById("pdf-fullscreen")?.addEventListener("click", () => {
    container.requestFullscreen?.();
  });

  container.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "j") renderPage(currentPage + 1);
    if (e.key === "ArrowLeft" || e.key === "k") renderPage(currentPage - 1);
  });

  loadPdf();
}
