(function () {
  const STORAGE_KEY = "itsbillw-theme";
  const COOKIE_NAME = "itsbillw-theme";
  const THEME_COLORS = {
    dark: "#1a2628",
    light: "#ffffff",
  };

  function systemTheme() {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function storedTheme() {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  }

  function resolveTheme() {
    return storedTheme() ?? systemTheme();
  }

  function setThemeCookie(theme) {
    document.cookie = `${COOKIE_NAME}=${theme};path=/;max-age=31536000;SameSite=Lax`;
  }

  function updateThemeColorMeta(theme) {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", THEME_COLORS[theme] || THEME_COLORS.dark);
    }
  }

  function updateThemeControls(theme) {
    document.querySelectorAll("[data-theme-choice]").forEach((btn) => {
      const choice = btn.getAttribute("data-theme-choice");
      btn.setAttribute("aria-pressed", String(choice === theme));
    });
  }

  function applyTheme(theme, persist) {
    document.documentElement.dataset.theme = theme;
    setThemeCookie(theme);
    updateThemeColorMeta(theme);
    updateThemeControls(theme);
    if (persist) {
      localStorage.setItem(STORAGE_KEY, theme);
    }
    document.dispatchEvent(
      new CustomEvent("themechange", { detail: { theme } }),
    );
  }

  function toggleTheme() {
    const next =
      document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next, true);
  }

  window.itsbillwTheme = {
    resolveTheme,
    applyTheme,
    toggleTheme,
    STORAGE_KEY,
  };

  const initial = resolveTheme();
  applyTheme(initial, false);

  document.querySelectorAll("[data-theme-choice]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const theme = btn.getAttribute("data-theme-choice");
      if (theme === "light" || theme === "dark") {
        applyTheme(theme, true);
      }
    });
  });

  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", (e) => {
      if (storedTheme()) return;
      applyTheme(e.matches ? "dark" : "light", false);
    });
})();
