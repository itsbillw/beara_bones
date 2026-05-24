(function () {
  const layout = document.getElementById("learning-layout");
  const sidebar = document.getElementById("learning-sidebar");
  const toggle = document.getElementById("learning-sidebar-toggle");
  const backdrop = document.getElementById("learning-sidebar-backdrop");
  const sidebarStorageKey = "learning-sidebar-collapsed";
  const treeExpandedKey = "learning-tree-expanded";
  const mobileQuery = window.matchMedia("(max-width: 767px)");

  const isMobile = () => mobileQuery.matches;

  if (layout && sidebar && toggle) {
    const setBackdropVisible = (visible) => {
      if (!backdrop) return;
      backdrop.hidden = !visible;
      backdrop.setAttribute("aria-hidden", String(!visible));
    };

    const applyCollapsed = (collapsed) => {
      layout.classList.toggle("sidebar-collapsed", collapsed);
      layout.classList.toggle("sidebar-open", !collapsed);
      setBackdropVisible(isMobile() && !collapsed);
      toggle.setAttribute("aria-expanded", String(!collapsed));
      toggle.setAttribute(
        "aria-label",
        collapsed ? "Show sidebar" : "Hide sidebar",
      );
      const icon = toggle.querySelector("i");
      if (icon) {
        icon.className = collapsed ? "bi bi-layout-sidebar" : "bi bi-list";
      }
    };

    const closeSidebar = () => {
      applyCollapsed(true);
      if (!isMobile()) {
        localStorage.setItem(sidebarStorageKey, "true");
      }
    };

    const openSidebar = () => {
      applyCollapsed(false);
      if (!isMobile()) {
        localStorage.setItem(sidebarStorageKey, "false");
      }
    };

    const initSidebar = () => {
      if (isMobile()) {
        applyCollapsed(true);
        return;
      }
      const savedSidebar = localStorage.getItem(sidebarStorageKey);
      applyCollapsed(savedSidebar === "true");
    };

    initSidebar();

    toggle.addEventListener("click", () => {
      const collapsed = !layout.classList.contains("sidebar-collapsed");
      if (collapsed) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });

    if (backdrop) {
      backdrop.addEventListener("click", closeSidebar);
    }

    document.addEventListener("keydown", (e) => {
      if (
        e.key === "Escape" &&
        isMobile() &&
        !layout.classList.contains("sidebar-collapsed")
      ) {
        closeSidebar();
      }
    });

    mobileQuery.addEventListener("change", () => {
      if (isMobile()) {
        applyCollapsed(true);
      } else {
        setBackdropVisible(false);
        const savedSidebar = localStorage.getItem(sidebarStorageKey);
        applyCollapsed(savedSidebar === "true");
      }
    });
  }

  const filterSelect = document.getElementById("learning-filter-select");
  if (filterSelect) {
    filterSelect.addEventListener("change", () => {
      window.location.href = filterSelect.value;
    });
  }

  // Nested tree expand/collapse
  const expandedSet = new Set(
    JSON.parse(localStorage.getItem(treeExpandedKey) || "[]"),
  );
  document.querySelectorAll(".learning-tree-toggle").forEach((btn) => {
    const dirId = btn.dataset.dirId;
    const children = document.getElementById(`tree-children-${dirId}`);
    if (!children) return;
    if (expandedSet.has(dirId)) {
      children.classList.remove("d-none");
      btn
        .querySelector("i")
        ?.classList.replace("bi-chevron-right", "bi-chevron-down");
    }
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const isHidden = children.classList.toggle("d-none");
      const icon = btn.querySelector("i");
      if (icon) {
        icon.className = isHidden
          ? "bi bi-chevron-right"
          : "bi bi-chevron-down";
      }
      if (isHidden) expandedSet.delete(dirId);
      else expandedSet.add(dirId);
      localStorage.setItem(treeExpandedKey, JSON.stringify([...expandedSet]));
    });
  });

  const filesContainer = document.getElementById("learning-files");
  const viewButtons = document.querySelectorAll(".learning-view-btn");
  const viewStorageKey = "learning-view-mode";

  if (filesContainer && viewButtons.length) {
    const applyView = (view) => {
      filesContainer.dataset.view = view;
      document
        .querySelectorAll(".learning-section-files")
        .forEach((section) => {
          section.dataset.view = view;
        });
      viewButtons.forEach((btn) => {
        const isActive = btn.dataset.view === view;
        btn.classList.toggle("active", isActive);
        btn.setAttribute("aria-pressed", String(isActive));
      });
    };

    const savedView = localStorage.getItem(viewStorageKey);
    if (savedView === "grid" || savedView === "list") {
      applyView(savedView);
    }

    viewButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        applyView(btn.dataset.view);
        localStorage.setItem(viewStorageKey, btn.dataset.view);
      });
    });
  }

  const uploadInput = document.getElementById("upload-input");
  const uploadForm = document.getElementById("upload-form");
  const triggerUpload = document.getElementById("trigger-upload");
  const dropZone = document.getElementById("learning-content");
  const dropOverlay = document.getElementById("learning-drop-overlay");
  const uploadTray = document.getElementById("learning-upload-tray");
  const uploadQueueEl = document.getElementById("learning-upload-queue");
  const uploadTrayTitle = document.getElementById("learning-upload-tray-title");
  const uploadTrayToggle = document.getElementById(
    "learning-upload-tray-toggle",
  );
  const uploadTrayClose = document.getElementById("learning-upload-tray-close");
  const importZipForm = document.getElementById("import-zip-form");
  const importZipModal = document.getElementById("importZipModal");

  function getCsrfToken() {
    return document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
  }

  function isZipFile(file) {
    return file.name.toLowerCase().endsWith(".zip");
  }

  function ensureFilesContainer() {
    let container = document.getElementById("learning-files");
    if (container) return container;
    const content = document.getElementById("learning-content");
    if (!content || !uploadForm) return null;
    const empty = content.querySelector(".learning-empty");
    if (empty) empty.remove();
    container = document.createElement("div");
    container.id = "learning-files";
    container.className = "learning-files";
    container.dataset.view =
      localStorage.getItem("learning-view-mode") || "grid";
    container.dataset.sort = "name";
    content.appendChild(container);
    return container;
  }

  function appendUploadedHtml(html) {
    const container = ensureFilesContainer();
    if (!container || !html.trim()) return;
    const parsed = new DOMParser().parseFromString(html, "text/html");
    parsed.querySelectorAll(".learning-file-row").forEach((row) => {
      container.appendChild(document.importNode(row, true));
    });
    const empty = document.querySelector(".learning-empty");
    if (empty) empty.remove();
  }

  class UploadQueue {
    constructor() {
      this.items = [];
      this.active = false;
      this.autoCollapseTimer = null;
    }

    showTray() {
      if (uploadTray) uploadTray.hidden = false;
    }

    hideTrayIfIdle() {
      if (!uploadTray) return;
      const pending = this.items.some(
        (item) =>
          item.state === "queued" ||
          item.state === "uploading" ||
          item.state === "processing",
      );
      if (!pending) {
        this.autoCollapseTimer = setTimeout(() => {
          if (
            !this.items.some(
              (item) =>
                item.state === "queued" ||
                item.state === "uploading" ||
                item.state === "processing",
            )
          ) {
            uploadTray.hidden = true;
          }
        }, 5000);
      }
    }

    updateTitle() {
      if (!uploadTrayTitle) return;
      const total = this.items.length;
      const done = this.items.filter(
        (item) =>
          item.state === "complete" ||
          item.state === "duplicate" ||
          item.state === "error",
      ).length;
      const active = this.items.some(
        (item) => item.state === "uploading" || item.state === "processing",
      );
      uploadTrayTitle.textContent = active
        ? `Uploads (${done} of ${total})`
        : total === done
          ? `${total} upload${total === 1 ? "" : "s"} complete`
          : `Uploads (${done} of ${total})`;
    }

    createRow(item) {
      const li = document.createElement("li");
      li.className = "learning-upload-item";
      li.dataset.uploadId = item.id;
      li.innerHTML =
        '<div class="learning-upload-item-progress">' +
        '<div class="learning-upload-item-bar"></div></div>' +
        '<span class="learning-upload-item-icon" aria-hidden="true"></span>' +
        '<span class="learning-upload-item-name"></span>' +
        '<span class="learning-upload-item-status"></span>' +
        '<button type="button" class="learning-upload-item-retry btn btn-sm btn-outline-light" hidden>Retry</button>';
      uploadQueueEl?.appendChild(li);
      item.row = li;
      this.renderItem(item);
      return li;
    }

    renderItem(item) {
      if (!item.row) return;
      const bar = item.row.querySelector(".learning-upload-item-bar");
      const icon = item.row.querySelector(".learning-upload-item-icon");
      const name = item.row.querySelector(".learning-upload-item-name");
      const status = item.row.querySelector(".learning-upload-item-status");
      const retry = item.row.querySelector(".learning-upload-item-retry");
      name.textContent = item.label;
      item.row.className =
        "learning-upload-item learning-upload-item-" + item.state;
      if (bar) bar.style.width = String(item.progress || 0) + "%";
      retry.hidden = item.state !== "error";
      retry.onclick = () => {
        item.state = "queued";
        item.progress = 0;
        item.errorMessage = "";
        this.renderItem(item);
        this.pump();
      };
      if (item.state === "queued") {
        icon.innerHTML = '<i class="bi bi-circle"></i>';
        status.textContent = "Queued";
      } else if (item.state === "uploading") {
        icon.innerHTML = '<i class="bi bi-cloud-upload"></i>';
        status.textContent = item.progress ? item.progress + "%" : "Uploading…";
      } else if (item.state === "processing") {
        icon.innerHTML = '<span class="learning-upload-spinner"></span>';
        status.textContent = "Processing…";
      } else if (item.state === "complete") {
        icon.innerHTML = '<i class="bi bi-check-circle-fill"></i>';
        status.textContent = "Done";
      } else if (item.state === "duplicate") {
        icon.innerHTML = '<i class="bi bi-exclamation-triangle-fill"></i>';
        status.textContent = "Duplicate";
      } else if (item.state === "error") {
        icon.innerHTML = '<i class="bi bi-x-circle-fill"></i>';
        status.textContent = item.errorMessage || "Failed";
      }
      this.updateTitle();
    }

    addFiles(files) {
      if (!uploadForm || !files.length) return;
      this.showTray();
      if (this.autoCollapseTimer) clearTimeout(this.autoCollapseTimer);
      for (const file of files) {
        if (isZipFile(file)) {
          this.importZip(file);
          continue;
        }
        const item = {
          id: crypto.randomUUID
            ? crypto.randomUUID()
            : String(Date.now() + Math.random()),
          kind: "file",
          file,
          label: file.name,
          state: "queued",
          progress: 0,
        };
        this.items.push(item);
        this.createRow(item);
      }
      this.pump();
    }

    importZip(file) {
      if (!importZipForm) {
        if (window.Feedback) {
          Feedback.toast("Open a folder to import zip archives.", {
            variant: "warning",
          });
        }
        return;
      }
      const item = {
        id: crypto.randomUUID
          ? crypto.randomUUID()
          : String(Date.now() + Math.random()),
        kind: "zip",
        file,
        label: file.name,
        state: "queued",
        progress: 0,
      };
      this.items.push(item);
      this.createRow(item);
      this.pump();
    }

    pump() {
      if (this.active) return;
      const next = this.items.find((item) => item.state === "queued");
      if (!next) {
        this.hideTrayIfIdle();
        return;
      }
      this.active = true;
      if (next.kind === "zip") {
        this.uploadZip(next).finally(() => {
          this.active = false;
          this.pump();
        });
      } else {
        this.uploadOne(next).finally(() => {
          this.active = false;
          this.pump();
        });
      }
    }

    uploadOne(item) {
      item.state = "uploading";
      this.renderItem(item);
      const formData = new FormData(uploadForm);
      formData.delete("file");
      formData.append("file", item.file);
      return new Promise((resolve) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", uploadForm.action);
        xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
        xhr.setRequestHeader("HX-Request", "true");
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            item.progress = Math.min(90, Math.round((e.loaded / e.total) * 90));
            this.renderItem(item);
          }
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            item.state = "processing";
            item.progress = 92;
            this.renderItem(item);
            appendUploadedHtml(xhr.responseText);
            let resultStatus = "complete";
            try {
              const doc = new DOMParser().parseFromString(
                xhr.responseText,
                "text/html",
              );
              const meta = doc.querySelector(".upload-results-meta");
              if (meta) {
                const results = JSON.parse(meta.textContent);
                const match = results.find((r) => r.name === item.label);
                if (match?.status === "duplicate") {
                  resultStatus = "duplicate";
                  if (window.Feedback && match.message) {
                    Feedback.toast(match.message, { variant: "warning" });
                  }
                }
              }
            } catch (_err) {
              /* ignore parse errors */
            }
            item.state = resultStatus;
            item.progress = 100;
            this.renderItem(item);
            resolve();
            return;
          }
          let message = "Upload failed";
          try {
            const data = JSON.parse(xhr.responseText);
            message = data.error || message;
          } catch (_err) {
            /* ignore */
          }
          item.state = "error";
          item.errorMessage = message;
          item.progress = 0;
          this.renderItem(item);
          if (window.Feedback) Feedback.toast(message, { variant: "error" });
          resolve();
        };
        xhr.onerror = () => {
          item.state = "error";
          item.errorMessage = "Network error";
          this.renderItem(item);
          if (window.Feedback) {
            Feedback.toast("Upload failed: network error.", {
              variant: "error",
            });
          }
          resolve();
        };
        xhr.send(formData);
      });
    }

    uploadZip(item) {
      if (!importZipForm) {
        item.state = "error";
        item.errorMessage = "No folder open";
        this.renderItem(item);
        return Promise.resolve();
      }
      item.state = "uploading";
      item.progress = 10;
      this.renderItem(item);
      const formData = new FormData(importZipForm);
      formData.set("file", item.file);
      return fetch(importZipForm.action, {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": getCsrfToken(),
        },
        body: formData,
      })
        .then(async (response) => {
          const data = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(data.message || "Import failed");
          }
          item.state = "complete";
          item.progress = 100;
          this.renderItem(item);
          if (window.Feedback) {
            Feedback.toast(data.message || "Zip imported.", {
              variant: "success",
            });
          }
          window.setTimeout(() => window.location.reload(), 800);
        })
        .catch((err) => {
          item.state = "error";
          item.errorMessage = err.message || "Import failed";
          this.renderItem(item);
          if (window.Feedback) {
            Feedback.toast(item.errorMessage, { variant: "error" });
          }
        });
    }
  }

  const uploadQueue = new UploadQueue();

  if (uploadTrayToggle && uploadQueueEl) {
    uploadTrayToggle.addEventListener("click", () => {
      const expanded =
        uploadTrayToggle.getAttribute("aria-expanded") === "true";
      uploadTrayToggle.setAttribute("aria-expanded", String(!expanded));
      uploadQueueEl.hidden = expanded;
      uploadTrayToggle.classList.toggle("is-collapsed", expanded);
    });
  }

  if (uploadTrayClose && uploadTray) {
    uploadTrayClose.addEventListener("click", () => {
      const busy = uploadQueue.items.some(
        (item) =>
          item.state === "queued" ||
          item.state === "uploading" ||
          item.state === "processing",
      );
      if (busy) return;
      uploadTray.hidden = true;
      uploadQueue.items = [];
      uploadQueueEl.innerHTML = "";
    });
  }

  if (importZipForm) {
    importZipForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = document.getElementById("import-zip-input");
      const errorEl = document.getElementById("import-zip-error");
      if (!input?.files?.length) return;
      if (errorEl) errorEl.hidden = true;
      uploadQueue.importZip(input.files[0]);
      uploadQueue.pump();
      if (importZipModal) {
        bootstrap.Modal.getOrCreateInstance(importZipModal).hide();
      }
      input.value = "";
    });
  }

  function handleIncomingFiles(files) {
    if (!uploadForm) {
      if (window.Feedback) {
        Feedback.toast("Open a folder before uploading files.", {
          variant: "warning",
        });
      }
      return;
    }
    const regular = [];
    for (const file of files) {
      if (isZipFile(file)) {
        uploadQueue.importZip(file);
      } else {
        regular.push(file);
      }
    }
    if (regular.length) uploadQueue.addFiles(regular);
    else uploadQueue.pump();
  }

  if (triggerUpload && uploadInput) {
    triggerUpload.addEventListener("click", () => uploadInput.click());
    uploadInput.addEventListener("change", () => {
      if (uploadInput.files?.length) {
        handleIncomingFiles([...uploadInput.files]);
        uploadInput.value = "";
      }
    });
  }

  if (dropZone && uploadForm) {
    ["dragenter", "dragover"].forEach((ev) => {
      dropZone.addEventListener(ev, (e) => {
        e.preventDefault();
        if (dropOverlay) dropOverlay.hidden = false;
        dropZone.classList.add("learning-drop-active");
      });
    });
    ["dragleave", "drop"].forEach((ev) => {
      dropZone.addEventListener(ev, (e) => {
        e.preventDefault();
        if (dropOverlay) dropOverlay.hidden = true;
        dropZone.classList.remove("learning-drop-active");
      });
    });
    dropZone.addEventListener("drop", (e) => {
      const files = [...(e.dataTransfer?.files || [])];
      if (files.length) handleIncomingFiles(files);
    });
  }

  document.querySelectorAll(".learning-star-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const url = btn.dataset.starUrl;
      const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value;
      fetch(url, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrf,
          "X-Requested-With": "XMLHttpRequest",
        },
      })
        .then((r) => r.json())
        .then((data) => {
          btn.classList.toggle("starred", data.starred);
          const icon = btn.querySelector("i");
          if (icon) {
            icon.className = data.starred ? "bi bi-star-fill" : "bi bi-star";
          }
          btn.setAttribute(
            "aria-label",
            data.starred
              ? btn.dataset.unstarLabel || "Unstar"
              : btn.dataset.starLabel || "Star",
          );
        });
    });
  });

  document
    .querySelectorAll(".wikilink[data-bs-toggle='popover']")
    .forEach((el) => {
      new bootstrap.Popover(el, { container: "body", html: false });
    });

  const searchInput = document.getElementById("learning-search-input");
  let gPending = false;
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select")) {
      if (e.key === "Escape") e.target.blur();
      return;
    }
    if (e.key === "/" && searchInput) {
      e.preventDefault();
      searchInput.focus();
    }
    if (e.key === "?") {
      document.getElementById("shortcutsModal") &&
        bootstrap.Modal.getOrCreateInstance(
          document.getElementById("shortcutsModal"),
        ).show();
    }
    if (e.key === "g") {
      gPending = true;
      setTimeout(() => {
        gPending = false;
      }, 800);
      return;
    }
    if (gPending) {
      gPending = false;
      if (e.key === "l") {
        viewButtons.forEach((b) => b.dataset.view === "list" && b.click());
      }
      if (e.key === "g") {
        viewButtons.forEach((b) => b.dataset.view === "grid" && b.click());
      }
    }
  });
})();
