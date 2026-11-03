// Shows the reading copy of a PDF (made by the engine, kept in chrome.storage.session under
// "doc:<id>") and asks the background worker to read it. highlight.js runs on this page too:
// the worker reaches it with runtime messages carrying this tab's id.
(async () => {
  const $ = (id) => document.getElementById(id);
  const id = location.hash.slice(1);
  const tab = await chrome.tabs.getCurrent();
  window.__sawtTab = tab.id;

  const doc = (await chrome.storage.session.get("doc:" + id))["doc:" + id];
  if (!doc) {
    $("title").textContent = "Sawt reader";
    $("missing").hidden = false;
    return;
  }
  document.title = doc.title;
  $("title").textContent = doc.title;
  let where = doc.url;
  try {
    const u = new URL(doc.url);
    where = u.protocol === "file:" ? decodeURIComponent(u.pathname.split("/").pop()) : u.hostname;
  } catch {}
  $("meta").textContent = `${doc.pages} ${doc.pages === 1 ? "page" : "pages"} · ${where}`;
  $("original").href = doc.url;
  $("truncated").hidden = !doc.truncated;

  // A heading is a short line that does not end like a sentence; the engine keeps those as
  // paragraphs of their own.
  const isHeading = (p) => p.split(/\s+/).length <= 12 && !/[.?!:,;]["”’)\]]?$/.test(p);
  $("text").replaceChildren(...doc.text.split("\n\n").map((p) => {
    const el = document.createElement(isHeading(p) ? "h2" : "p");
    el.textContent = p;
    return el;
  }));

  chrome.runtime.sendMessage({ to: "bg", cmd: "readDoc", id, tabId: tab.id });
})();
