/* Gestiona persistencia y cambio de tema por usuario. */

(function () {
  const STORAGE_PREFIX = "sentinldrive_theme";
  const DEFAULT_THEME = "glass-dark";
  const LIGHT_THEME = "glass-light";
  const DARK_THEME = "glass-dark";

  function currentUserKey() {
    const username = document.body?.dataset?.currentUser || "guest";
    return `${STORAGE_PREFIX}::${username}`;
  }

  function isLightTheme(themeName) {
    return String(themeName || "").toLowerCase() === LIGHT_THEME;
  }

  function updateThemeColor(themeName) {
    const themeColorMeta = document.querySelector('meta[name="theme-color"]');
    if (!themeColorMeta) return;
    themeColorMeta.setAttribute("content", isLightTheme(themeName) ? "#f4f7fb" : "#161a1e");
  }

  function applyTheme(themeName) {
    const theme = themeName || DEFAULT_THEME;
    document.documentElement.setAttribute("data-theme", theme);
    updateThemeColor(theme);
    try {
      localStorage.setItem(currentUserKey(), theme);
      localStorage.setItem(STORAGE_PREFIX, theme);
    } catch {
      // ignore storage errors
    }
    document.dispatchEvent(new CustomEvent("sentinldrive:themechange", { detail: { theme } }));
  }

  function readTheme() {
    try {
      return localStorage.getItem(currentUserKey()) || localStorage.getItem(STORAGE_PREFIX) || DEFAULT_THEME;
    } catch {
      return DEFAULT_THEME;
    }
  }

  function updateToggleUi(themeName) {
    const button = document.getElementById("themeModeToggle");
    if (!button) return;
    const icon = button.querySelector("[data-theme-toggle-icon]");
    const label = button.querySelector("[data-theme-toggle-label]");
    const isLight = isLightTheme(themeName);
    button.setAttribute("aria-pressed", isLight ? "true" : "false");
    if (icon) {
      icon.className = `bi ${isLight ? "bi-brightness-high-fill" : "bi-moon-stars-fill"}`;
    }
    if (label) {
      label.textContent = isLight ? "Modo claro" : "Modo oscuro";
    }
  }

  function initThemeSelector() {
    const selector = document.querySelector("[data-theme-switcher]");
    if (!selector) return;
    selector.value = document.documentElement.getAttribute("data-theme") || DEFAULT_THEME;
    selector.addEventListener("change", () => {
      applyTheme(selector.value);
      updateToggleUi(selector.value);
    });
  }

  function initThemeToggle() {
    const button = document.getElementById("themeModeToggle");
    if (!button) return;
    button.addEventListener("click", () => {
      const activeTheme = document.documentElement.getAttribute("data-theme") || DEFAULT_THEME;
      const nextTheme = isLightTheme(activeTheme) ? DARK_THEME : LIGHT_THEME;
      applyTheme(nextTheme);
      updateToggleUi(nextTheme);
    });
  }

  window.SentinelDriveTheme = {
    applyTheme,
    readTheme,
    defaultTheme: DEFAULT_THEME,
    lightTheme: LIGHT_THEME,
    darkTheme: DARK_THEME,
  };

  const initialTheme = readTheme();
  applyTheme(initialTheme);
  updateToggleUi(initialTheme);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      initThemeSelector();
      initThemeToggle();
      updateToggleUi(document.documentElement.getAttribute("data-theme") || DEFAULT_THEME);
    });
  } else {
    initThemeSelector();
    initThemeToggle();
    updateToggleUi(document.documentElement.getAttribute("data-theme") || DEFAULT_THEME);
  }
})();
