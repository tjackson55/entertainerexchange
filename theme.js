(function () {
  const DISPLAY_SETTINGS_KEY = "entertainers-exchange-display-settings";
  const fallbackSettings = {
    theme: "ocean",
    brightness: "normal",
    fontSize: "medium"
  };
  const displayOptions = {
    theme: ["ocean", "emerald", "sunset", "daylight", "midnight", "forest", "slate", "paper"],
    brightness: ["dim", "normal", "bright"],
    fontSize: ["small", "medium", "large", "xlarge"]
  };
  const fontScaleBySize = {
    small: 0.92,
    medium: 1,
    large: 1.08,
    xlarge: 1.16
  };

  function safeParseJson(rawValue) {
    if (typeof rawValue !== "string" || !rawValue) {
      return null;
    }

    try {
      return JSON.parse(rawValue);
    } catch (error) {
      return null;
    }
  }

  function sanitizeDisplaySettings(settings) {
    const safe = settings && typeof settings === "object" ? settings : {};
    return {
      theme: displayOptions.theme.includes(safe.theme) ? safe.theme : fallbackSettings.theme,
      brightness: displayOptions.brightness.includes(safe.brightness) ? safe.brightness : fallbackSettings.brightness,
      fontSize: displayOptions.fontSize.includes(safe.fontSize) ? safe.fontSize : fallbackSettings.fontSize
    };
  }

  function loadDisplaySettings() {
    const parsed = safeParseJson(window.localStorage.getItem(DISPLAY_SETTINGS_KEY));
    return sanitizeDisplaySettings(parsed);
  }

  function applyDisplaySettings() {
    const settings = loadDisplaySettings();
    if (!document.body) {
      return;
    }

    document.body.dataset.theme = settings.theme;
    document.body.dataset.brightness = settings.brightness;
    document.body.style.fontSize = `${fontScaleBySize[settings.fontSize] || 1}rem`;
  }

  function injectLegacyFooter() {
    if (!document.body || document.querySelector(".site-footer")) {
      return;
    }

    if (!window.location.pathname.includes("/entertainers/")) {
      return;
    }

    const footer = document.createElement("footer");
    footer.className = "site-footer";
    footer.setAttribute("role", "contentinfo");
    footer.innerHTML = `
      <p class="site-footer-copy">Fantasy entertainment index for trend tracking and editorial-style analysis. No real ownership, cash-out, or entertainer endorsement is implied.</p>
      <nav class="site-footer-links" aria-label="Legal and site links">
        <a href="../disclaimer.html">Disclaimer</a>
        <a href="../terms.html">Terms</a>
        <a href="../privacy.html">Privacy</a>
      </nav>
    `;
    document.body.appendChild(footer);
  }

  window.applySharedTheme = applyDisplaySettings;

  function applySharedPageChrome() {
    applyDisplaySettings();
    injectLegacyFooter();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applySharedPageChrome, { once: true });
  } else {
    applySharedPageChrome();
  }
}());
