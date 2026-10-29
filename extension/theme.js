// Applies the reader's appearance choice to an extension page. "auto" (the default) leaves the
// stylesheet's prefers-color-scheme rules in charge; "light" or "dark" overrides them.
// chrome.storage is the record; localStorage (shared by the extension's own pages) is read
// synchronously first, so a popup set to light does not flash dark while storage answers.
(() => {
  const apply = (theme) => {
    if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try { localStorage.setItem("theme", theme || "auto"); } catch {}
  };
  try { apply(localStorage.getItem("theme")); } catch {}
  chrome.storage.local.get("theme").then(({ theme }) => apply(theme));
  chrome.storage.local.onChanged.addListener((c) => { if (c.theme) apply(c.theme.newValue); });
})();
