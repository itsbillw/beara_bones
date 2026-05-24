(function () {
  "use strict";

  var TOAST_CONTAINER_ID = "feedback-toast-container";

  function ensureToastContainer() {
    var container = document.getElementById(TOAST_CONTAINER_ID);
    if (container) return container;
    container = document.createElement("div");
    container.id = TOAST_CONTAINER_ID;
    container.className = "feedback-toast-container";
    container.setAttribute("aria-live", "polite");
    container.setAttribute("aria-atomic", "true");
    document.body.appendChild(container);
    return container;
  }

  function toastClass(variant) {
    if (variant === "success") return "text-bg-success";
    if (variant === "error" || variant === "danger") return "text-bg-danger";
    if (variant === "warning") return "text-bg-warning";
    return "text-bg-primary";
  }

  function showToast(message, options) {
    options = options || {};
    var variant = options.variant || "info";
    var duration = options.duration !== undefined ? options.duration : 5000;
    var container = ensureToastContainer();
    var el = document.createElement("div");
    el.className = "toast align-items-center border-0 " + toastClass(variant);
    el.setAttribute("role", "alert");
    el.innerHTML =
      '<div class="d-flex">' +
      '<div class="toast-body">' +
      escapeHtml(message) +
      "</div>" +
      '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>' +
      "</div>";
    container.appendChild(el);
    if (typeof bootstrap !== "undefined" && bootstrap.Toast) {
      var toast = bootstrap.Toast.getOrCreateInstance(el, {
        autohide: duration > 0,
        delay: duration,
      });
      el.addEventListener("hidden.bs.toast", function () {
        el.remove();
      });
      toast.show();
    } else {
      setTimeout(function () {
        el.remove();
      }, duration || 5000);
    }
    return el;
  }

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function showAlert(container, message, variant) {
    if (!container) return null;
    variant = variant || "info";
    var alert = document.createElement("div");
    alert.className = "alert alert-" + variant + " alert-dismissible fade show";
    alert.setAttribute("role", "alert");
    alert.innerHTML =
      escapeHtml(message) +
      '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
    container.appendChild(alert);
    return alert;
  }

  window.Feedback = {
    toast: showToast,
    alert: showAlert,
  };
})();
