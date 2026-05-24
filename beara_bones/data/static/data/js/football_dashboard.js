(function () {
  "use strict";

  function parseFigure(container) {
    var dataEl = container.querySelector(".football-chart-data");
    if (!dataEl) {
      return null;
    }
    try {
      return JSON.parse(dataEl.textContent);
    } catch (err) {
      console.error("Invalid chart JSON", err);
      return null;
    }
  }

  function renderFootballChart(containerId) {
    var container = document.getElementById(containerId);
    if (!container || typeof Plotly === "undefined") {
      return;
    }
    var figure = parseFigure(container);
    if (!figure) {
      return;
    }
    Plotly.newPlot(containerId, figure.data || [], figure.layout || {}, {
      responsive: true,
      displayModeBar: false,
    });
  }

  window.renderFootballChart = renderFootballChart;

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail.target.id === "football-dashboard-panel") {
      renderFootballChart("football-chart");
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    renderFootballChart("football-chart");
  });

  document.addEventListener("themechange", function () {
    var form = document.getElementById("football-dashboard-controls");
    if (form && window.htmx) {
      htmx.trigger(form, "change");
    }
  });

  function cellValue(row, index, sortType) {
    var cell = row.cells[index];
    if (!cell) return "";
    if (sortType === "number") {
      return parseFloat(cell.textContent.trim()) || 0;
    }
    return cell.textContent.trim().toLowerCase();
  }

  function initFootballStandingsSort(tableId) {
    var table = document.getElementById(tableId);
    if (!table) return;
    var headers = table.querySelectorAll("thead th[data-sort]");
    headers.forEach(function (th, index) {
      if (th.getAttribute("data-sort") === "none") return;
      th.style.cursor = "pointer";
      th.addEventListener("click", function () {
        var tbody = table.querySelector("tbody");
        var rows = Array.from(tbody.querySelectorAll("tr"));
        var sortType = th.getAttribute("data-sort") || "string";
        var ascending = th.getAttribute("data-order") !== "asc";
        rows.sort(function (a, b) {
          var av = cellValue(a, index, sortType);
          var bv = cellValue(b, index, sortType);
          if (av < bv) return ascending ? -1 : 1;
          if (av > bv) return ascending ? 1 : -1;
          return 0;
        });
        headers.forEach(function (h) {
          h.removeAttribute("data-order");
        });
        th.setAttribute("data-order", ascending ? "asc" : "desc");
        rows.forEach(function (row) {
          tbody.appendChild(row);
        });
      });
    });
  }

  window.initFootballStandingsSort = initFootballStandingsSort;
})();
