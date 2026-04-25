(function () {
  const STORAGE_KEY = "sentinldrive_theme";
  const DEFAULT_THEME = "glass-dark";

  function applyTheme(themeName) {
    const theme = themeName || DEFAULT_THEME;
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // ignore storage errors
    }
    document.dispatchEvent(new CustomEvent("sentinldrive:themechange", { detail: { theme } }));
  }

  function readTheme() {
    try {
      return localStorage.getItem(STORAGE_KEY) || DEFAULT_THEME;
    } catch {
      return DEFAULT_THEME;
    }
  }

  function initThemeSelector() {
    const selector = document.querySelector("[data-theme-switcher]");
    if (!selector) return;
    selector.value = document.documentElement.getAttribute("data-theme") || DEFAULT_THEME;
    selector.addEventListener("change", () => applyTheme(selector.value));
  }

  window.SentinelDriveTheme = {
    applyTheme,
    readTheme,
    defaultTheme: DEFAULT_THEME,
  };

  applyTheme(readTheme());

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initThemeSelector);
  } else {
    initThemeSelector();
  }
})();
