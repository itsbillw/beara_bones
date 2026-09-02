(function () {
  "use strict";

  var CHARTS = [
    { wrapperId: "health-chart-cpu", plotId: "health-chart-cpu-plot" },
    { wrapperId: "health-chart-memory", plotId: "health-chart-memory-plot" },
    {
      wrapperId: "health-chart-temperature",
      plotId: "health-chart-temperature-plot",
    },
    { wrapperId: "health-chart-storage", plotId: "health-chart-storage-plot" },
  ];
  var CHART_HEIGHT = 280;
  var resizeTimer;

  function parseFigure(wrapper) {
    var dataEl = wrapper.querySelector(".health-chart-data");
    if (!dataEl) {
      return null;
    }
    try {
      return JSON.parse(dataEl.textContent);
    } catch (err) {
      console.error("Invalid health chart JSON", err);
      return null;
    }
  }

  function chartContainerWidth(wrapper, plotEl) {
    return plotEl.clientWidth || wrapper.clientWidth || plotEl.offsetWidth;
  }

  function buildLayout(figureLayout, width) {
    var layout = Object.assign({}, figureLayout || {});
    layout.autosize = false;
    layout.height = layout.height || CHART_HEIGHT;
    if (width > 0) {
      layout.width = width;
    }
    return layout;
  }

  function renderHealthCharts() {
    if (typeof Plotly === "undefined") {
      return;
    }
    CHARTS.forEach(function (chart) {
      var wrapper = document.getElementById(chart.wrapperId);
      var plotEl = document.getElementById(chart.plotId);
      if (!wrapper || !plotEl) {
        return;
      }
      var figure = parseFigure(wrapper);
      if (!figure) {
        return;
      }
      if (plotEl.classList.contains("js-plotly-plot")) {
        Plotly.purge(plotEl);
      }
      var width = chartContainerWidth(wrapper, plotEl);
      Plotly.newPlot(
        plotEl,
        figure.data || [],
        buildLayout(figure.layout, width),
        {
          responsive: false,
          displayModeBar: false,
        },
      );
    });
  }

  function resizeHealthCharts() {
    if (typeof Plotly === "undefined") {
      return;
    }
    CHARTS.forEach(function (chart) {
      var wrapper = document.getElementById(chart.wrapperId);
      var plotEl = document.getElementById(chart.plotId);
      if (!wrapper || !plotEl || !plotEl.classList.contains("js-plotly-plot")) {
        return;
      }
      var width = chartContainerWidth(wrapper, plotEl);
      if (width > 0) {
        Plotly.relayout(plotEl, { width: width });
      }
    });
  }

  window.renderHealthCharts = renderHealthCharts;

  document.addEventListener("DOMContentLoaded", function () {
    renderHealthCharts();
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (
      event.detail.target.id === "health-charts-panel" ||
      event.detail.target.id === "health-cards-panel"
    ) {
      if (event.detail.target.id === "health-charts-panel") {
        renderHealthCharts();
      }
    }
  });

  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resizeHealthCharts, 150);
  });
})();
