/* Cinesmith theme toggle — dark default, light optional, localStorage persistence.
   Safe to load in <head>: applies data-theme before first paint when possible. */
(function (global) {
  "use strict";

  var STORAGE_KEY = "cinesmith-theme";
  var DEFAULT_THEME = "dark";
  var THEMES = { dark: true, light: true };

  function normalize(theme) {
    if (theme === "light" || theme === "dark") return theme;
    return DEFAULT_THEME;
  }

  function readStored() {
    try {
      return normalize(global.localStorage && global.localStorage.getItem(STORAGE_KEY));
    } catch (_e) {
      return DEFAULT_THEME;
    }
  }

  function writeStored(theme) {
    try {
      if (global.localStorage) global.localStorage.setItem(STORAGE_KEY, theme);
    } catch (_e) {
      /* private mode / blocked storage — ignore */
    }
  }

  function applyTheme(theme) {
    theme = normalize(theme);
    var root = document.documentElement;
    root.setAttribute("data-theme", theme);
    root.style.colorScheme = theme;
    if (document.body) {
      document.body.setAttribute("data-theme", theme);
    }
    syncToggleUi(theme);
    try {
      global.dispatchEvent(new CustomEvent("cinesmith:themechange", { detail: { theme: theme } }));
    } catch (_e) {
      /* older engines without CustomEvent constructor quirks — ignore */
    }
    return theme;
  }

  function getTheme() {
    var attr = document.documentElement.getAttribute("data-theme");
    return normalize(attr || readStored());
  }

  function setTheme(theme) {
    theme = normalize(theme);
    writeStored(theme);
    return applyTheme(theme);
  }

  function toggleTheme() {
    var next = getTheme() === "light" ? "dark" : "light";
    return setTheme(next);
  }

  function syncToggleUi(theme) {
    var btn = document.getElementById("cinesmith-theme-toggle");
    if (!btn) return;
    var isLight = theme === "light";
    btn.setAttribute("aria-pressed", isLight ? "true" : "false");
    btn.setAttribute(
      "aria-label",
      isLight ? "Switch to dark theme" : "Switch to light theme"
    );
    btn.title = isLight ? "Dark theme" : "Light theme";
    var icon = btn.querySelector(".theme-icon");
    var label = btn.querySelector(".theme-label");
    if (icon) icon.textContent = isLight ? "☾" : "☀";
    if (label) label.textContent = isLight ? "Dark" : "Light";
  }

  function onToggleClick(ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    }
    toggleTheme();
  }

  function wireToggle() {
    var btn = document.getElementById("cinesmith-theme-toggle");
    if (!btn || btn.dataset.cinesmithThemeWired === "1") return;
    btn.dataset.cinesmithThemeWired = "1";
    btn.addEventListener("click", onToggleClick);
    syncToggleUi(getTheme());
  }

  // Apply immediately (head-safe)
  applyTheme(readStored());

  function boot() {
    applyTheme(readStored());
    wireToggle();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  global.CinesmithTheme = {
    get: getTheme,
    set: setTheme,
    toggle: toggleTheme,
    apply: applyTheme,
    STORAGE_KEY: STORAGE_KEY,
    DEFAULT: DEFAULT_THEME,
    THEMES: THEMES,
  };
})(typeof window !== "undefined" ? window : globalThis);
