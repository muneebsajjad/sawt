// Injected on demand, after vendor/Readability.js. The last expression is the result
// chrome.scripting.executeScript hands back to the background worker.
(() => {
  const BLOCKS = "p, h1, h2, h3, h4, h5, h6, li, blockquote, pre, figcaption, dt, dd";

  // Readability's textContent loses paragraph breaks, and the server pauses longer at those,
  // so rebuild the text from block elements of its cleaned HTML.
  function toText(html) {
    // DOMParser never runs scripts, unlike assigning innerHTML on a live element
    const doc = new DOMParser().parseFromString(html, "text/html");
    const parts = [];
    for (const el of doc.body.querySelectorAll(BLOCKS)) {
      if (el.querySelector(BLOCKS)) continue;          // leaf blocks only, or text repeats
      const t = el.textContent.replace(/\s+/g, " ").trim();
      if (t) parts.push(t);
    }
    return parts.length ? parts.join("\n\n") : doc.body.textContent.trim();
  }

  const selection = String(window.getSelection() || "").trim();
  if (selection.length > 40) {
    return { title: "", text: selection, source: "selection" };
  }

  const article = new Readability(document.cloneNode(true)).parse();
  if (article && article.content) {
    return { title: (article.title || document.title).trim(), text: toText(article.content),
             source: "article" };
  }
  return { title: document.title, text: document.body.innerText, source: "page" };
})();
