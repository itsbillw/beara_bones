(function () {
  const layout = document.getElementById("learning-layout");
  const sidebar = document.getElementById("learning-sidebar");
  const toggle = document.getElementById("learning-sidebar-toggle");
  const sidebarStorageKey = "learning-sidebar-collapsed";
  const treeExpandedKey = "learning-tree-expanded";

  if (layout && sidebar && toggle) {
    const applyCollapsed = (collapsed) => {
      layout.classList.toggle("sidebar-collapsed", collapsed);
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

    const savedSidebar = localStorage.getItem(sidebarStorageKey);
    if (savedSidebar === "true") {
      applyCollapsed(true);
    } else {
      layout.classList.add("sidebar-open");
    }

    toggle.addEventListener("click", () => {
      const collapsed = !layout.classList.contains("sidebar-collapsed");
      applyCollapsed(collapsed);
      localStorage.setItem(sidebarStorageKey, String(collapsed));
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
  const uploadProgress = document.getElementById("learning-upload-progress");
  const uploadBar = document.getElementById("learning-upload-bar");
  const uploadLabel = document.getElementById("learning-upload-label");

  function uploadFiles(files) {
    if (!uploadForm || !files.length) return;
    const formData = new FormData(uploadForm);
    formData.delete("file");
    for (const file of files) formData.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", uploadForm.action);
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    if (uploadProgress) uploadProgress.hidden = false;
    xhr.upload.onprogress = (e) => {
      if (uploadProgress && e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        if (uploadBar) uploadBar.style.width = `${pct}%`;
        if (uploadLabel) uploadLabel.textContent = `Uploading… ${pct}%`;
      }
    };
    xhr.onload = () => {
      if (uploadProgress) uploadProgress.hidden = true;
      window.location.reload();
    };
    xhr.send(formData);
  }

  if (triggerUpload && uploadInput) {
    triggerUpload.addEventListener("click", () => uploadInput.click());
    uploadInput.addEventListener("change", () => {
      if (uploadInput.files?.length) uploadFiles([...uploadInput.files]);
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
      if (files.length) uploadFiles(files);
    });
  }

  document.querySelectorAll(".learning-star-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
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
          if (icon)
            icon.className = data.starred ? "bi bi-star-fill" : "bi bi-star";
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
