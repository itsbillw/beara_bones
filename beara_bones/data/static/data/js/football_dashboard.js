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
})();
