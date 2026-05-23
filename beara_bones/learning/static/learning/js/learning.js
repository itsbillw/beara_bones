(function () {
  const layout = document.getElementById("learning-layout");
  const sidebar = document.getElementById("learning-sidebar");
  const toggle = document.getElementById("learning-sidebar-toggle");
  const sidebarStorageKey = "learning-sidebar-collapsed";

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
    }

    toggle.addEventListener("click", () => {
      const collapsed = !layout.classList.contains("sidebar-collapsed");
      applyCollapsed(collapsed);
      localStorage.setItem(sidebarStorageKey, String(collapsed));
    });
  }

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

  if (triggerUpload && uploadInput && uploadForm) {
    triggerUpload.addEventListener("click", () => {
      uploadInput.click();
    });

    uploadInput.addEventListener("change", () => {
      if (uploadInput.files && uploadInput.files.length > 0) {
        uploadForm.submit();
      }
    });
  }
})();
