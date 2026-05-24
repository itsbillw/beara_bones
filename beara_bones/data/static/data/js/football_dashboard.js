(function () {
  "use strict";

  var CHART_WRAPPER_ID = "football-chart";
  var PLOT_ID = "football-chart-plot";
  var TABLE_ID = "football-standings-table";
  var PANEL_ID = "football-dashboard-panel";

  function parseFigure(wrapper) {
    var dataEl = wrapper.querySelector(".football-chart-data");
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

  function renderFootballChart() {
    var wrapper = document.getElementById(CHART_WRAPPER_ID);
    var plotEl = document.getElementById(PLOT_ID);
    if (!wrapper || !plotEl || typeof Plotly === "undefined") {
      return;
    }
    var figure = parseFigure(wrapper);
    if (!figure) {
      return;
    }
    if (plotEl.classList.contains("js-plotly-plot")) {
      Plotly.purge(plotEl);
    }
    Plotly.newPlot(plotEl, figure.data || [], figure.layout || {}, {
      responsive: true,
      displayModeBar: false,
    }).then(function () {
      requestAnimationFrame(function () {
        Plotly.Plots.resize(plotEl);
      });
    });
  }

  window.renderFootballChart = renderFootballChart;

  function initDashboardPanel() {
    renderFootballChart();
    if (window.initFootballStandingsSort) {
      window.initFootballStandingsSort(TABLE_ID);
    }
  }

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail.target.id === PANEL_ID) {
      initDashboardPanel();
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    initDashboardPanel();
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
