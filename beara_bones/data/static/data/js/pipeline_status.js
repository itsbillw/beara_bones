(function () {
  "use strict";

  var POLL_INTERVAL_MS = 2500;
  var pollTimer = null;
  var wasRunning = false;

  function getCsrfToken() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function formatRelativeTime(isoString) {
    if (!isoString) return "";
    var date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return isoString;
    var seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return "just now";
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + "m ago";
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + "h ago";
    var days = Math.floor(hours / 24);
    return days + "d ago";
  }

  function updateLastRefreshed(isoString) {
    var el = document.getElementById("pipeline-last-refreshed");
    if (!el || !isoString) return;
    var relative = formatRelativeTime(isoString);
    el.innerHTML =
      'Last refreshed: <time datetime="' +
      isoString +
      '">' +
      relative +
      "</time>";
  }

  function renderChip(status) {
    var chip = document.getElementById("pipeline-status-chip");
    if (!chip) return;

    var html = "";
    if (status.running) {
      var progress =
        status.total_pairs > 0
          ? "Running " +
            (status.completed + status.failed) +
            "/" +
            status.total_pairs
          : "Running…";
      var detail = "";
      if (status.current && status.current.league_name) {
        detail =
          '<span class="pipeline-chip-detail">' + status.current.league_name;
        if (status.current.season_year) {
          detail += " " + status.current.season_year;
        }
        detail += "</span>";
      }
      html =
        '<span class="pipeline-chip pipeline-chip-running">' +
        '<span class="pipeline-chip-spinner" aria-hidden="true"></span>' +
        progress +
        detail +
        "</span>";
    } else if (status.batch_outcome === "success") {
      html =
        '<span class="pipeline-chip pipeline-chip-success">Updated just now</span>';
    } else if (status.batch_outcome === "partial") {
      html =
        '<span class="pipeline-chip pipeline-chip-warning">Completed with errors</span>';
    } else if (status.batch_outcome === "failed") {
      html =
        '<span class="pipeline-chip pipeline-chip-error">Refresh failed</span>';
    } else if (status.stale_lock) {
      html =
        '<span class="pipeline-chip pipeline-chip-warning">Run may be stuck</span>';
    }
    chip.innerHTML = html;
  }

  function refreshActivityPanel(url) {
    var panel = document.getElementById("pipeline-activity-panel");
    if (!panel || !url) return;
    fetch(url, { headers: { Accept: "text/html" } })
      .then(function (r) {
        if (!r.ok) return null;
        return r.text();
      })
      .then(function (html) {
        if (!html) return;
        panel.outerHTML = html;
        bindActivityToggle();
      })
      .catch(function () {});
  }

  function refreshDashboardPanel(panelUrl) {
    var form = document.getElementById("football-dashboard-controls");
    if (!form || !panelUrl || !window.htmx) return;
    var params = new URLSearchParams(new FormData(form));
    htmx.ajax("GET", panelUrl + "?" + params.toString(), {
      target: "#football-dashboard-panel",
      swap: "innerHTML",
    });
  }

  function handleStatusTransition(status, btn) {
    if (wasRunning && !status.running) {
      if (status.batch_outcome === "success") {
        if (window.Feedback) {
          Feedback.toast("Pipeline refresh complete. Dashboard updated.", {
            variant: "success",
          });
        }
        refreshDashboardPanel(btn.dataset.panelUrl);
      } else if (
        status.batch_outcome === "failed" ||
        status.batch_outcome === "partial"
      ) {
        if (window.Feedback) {
          Feedback.toast("Pipeline finished with errors.", {
            variant: "warning",
          });
        }
      }
      if (btn) btn.disabled = false;
    }
    wasRunning = status.running;
    if (status.last_success_at) {
      updateLastRefreshed(status.last_success_at);
    }
  }

  function pollStatus(btn) {
    var statusUrl = btn.dataset.statusUrl;
    if (!statusUrl) return;
    fetch(statusUrl, { headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json();
      })
      .then(function (status) {
        renderChip(status);
        refreshActivityPanel(btn.dataset.activityUrl);
        handleStatusTransition(status, btn);
        if (status.running) {
          pollTimer = setTimeout(function () {
            pollStatus(btn);
          }, POLL_INTERVAL_MS);
        } else {
          pollTimer = null;
        }
      })
      .catch(function () {
        pollTimer = setTimeout(function () {
          pollStatus(btn);
        }, POLL_INTERVAL_MS * 2);
      });
  }

  function startPolling(btn) {
    if (pollTimer) clearTimeout(pollTimer);
    wasRunning = true;
    pollStatus(btn);
  }

  function resetChipFromServer(btn) {
    fetch(btn.dataset.statusUrl, { headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json();
      })
      .then(renderChip)
      .catch(function () {
        renderChip({ running: false });
      });
  }

  function bindActivityToggle() {
    var toggle = document.getElementById("pipeline-activity-toggle");
    var body = document.getElementById("pipeline-activity-body");
    if (!toggle || !body || toggle.dataset.bound === "1") return;
    toggle.dataset.bound = "1";
    toggle.addEventListener("click", function () {
      var expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      body.hidden = expanded;
      toggle.classList.toggle("is-open", !expanded);
    });
  }

  function initPipelineStatus() {
    var btn = document.getElementById("refresh-btn");
    if (!btn) return;

    bindActivityToggle();

    var lastRefreshed = document.querySelector("#pipeline-last-refreshed time");
    if (lastRefreshed && lastRefreshed.getAttribute("datetime")) {
      updateLastRefreshed(lastRefreshed.getAttribute("datetime"));
    }

    fetch(btn.dataset.statusUrl, { headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json();
      })
      .then(function (status) {
        wasRunning = status.running;
        if (status.running) {
          btn.disabled = true;
          startPolling(btn);
        }
      })
      .catch(function () {});

    btn.addEventListener("click", function () {
      btn.disabled = true;

      fetch(btn.dataset.url, {
        method: "POST",
        headers: {
          "X-CSRFToken": getCsrfToken(),
          "Content-Type": "application/json",
        },
      })
        .then(function (r) {
          if (r.status === 202) {
            if (window.Feedback) {
              Feedback.toast("Pipeline refresh started.", { variant: "info" });
            }
            startPolling(btn);
            return;
          }
          if (r.status === 409) {
            if (window.Feedback) {
              Feedback.toast("Pipeline is already running.", {
                variant: "warning",
              });
            }
            startPolling(btn);
            return;
          }
          btn.disabled = false;
          resetChipFromServer(btn);
          if (window.Feedback) {
            Feedback.toast("Could not start refresh (HTTP " + r.status + ").", {
              variant: "error",
            });
          }
        })
        .catch(function () {
          btn.disabled = false;
          resetChipFromServer(btn);
          if (window.Feedback) {
            Feedback.toast("Request failed.", { variant: "error" });
          }
        });
    });
  }

  document.addEventListener("DOMContentLoaded", initPipelineStatus);
})();
