(function () {
  function cssVar(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
  }

  function palette() {
    return {
      text: cssVar("--chart-text", cssVar("--chart-text-color", "#f8fafc")),
      grid: cssVar("--chart-grid", cssVar("--chart-grid-color", "rgba(148, 163, 184, 0.18)")),
      accent: cssVar("--accent-green", cssVar("--accent", cssVar("--accent-color", "#22d67a"))),
      success: cssVar("--success", cssVar("--success-color", "#22d67a")),
      warning: cssVar("--warning", cssVar("--warning-color", "#ffb020")),
      danger: cssVar("--danger", cssVar("--danger-color", "#ff5f6d")),
      info: cssVar("--accent-cyan", cssVar("--info", "#42d7ff")),
      tooltipBg: "rgba(18, 22, 30, 0.92)",
      tooltipBorder: "rgba(255, 255, 255, 0.14)",
    };
  }

  function tooltipOptions() {
    const colors = palette();
    return {
      backgroundColor: colors.tooltipBg,
      titleColor: colors.text,
      bodyColor: colors.text,
      borderColor: colors.tooltipBorder,
      borderWidth: 1,
      padding: 10,
      cornerRadius: 12,
      displayColors: true,
    };
  }

  function applyChartDefaults() {
    if (!window.Chart) return;
    const colors = palette();
    Chart.defaults.color = colors.text;
    Chart.defaults.borderColor = colors.grid;
    Chart.defaults.font.family = "'Poppins', system-ui, -apple-system, 'Segoe UI', sans-serif";
    Chart.defaults.plugins.tooltip = {
      ...(Chart.defaults.plugins.tooltip || {}),
      ...tooltipOptions(),
    };
    if (Chart.defaults.plugins.legend && Chart.defaults.plugins.legend.labels) {
      Chart.defaults.plugins.legend.labels.color = colors.text;
    }
    Chart.defaults.elements.bar.borderRadius = 8;
    Chart.defaults.elements.bar.borderSkipped = false;
  }

  window.SDChartTheme = {
    palette,
    tooltipOptions,
    applyChartDefaults,
  };

  applyChartDefaults();
  document.addEventListener("DOMContentLoaded", applyChartDefaults);
  document.addEventListener("sentinldrive:themechange", applyChartDefaults);
})();
