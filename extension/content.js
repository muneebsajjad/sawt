// Injected on demand, after vendor/Readability.js. The last expression is the result
// chrome.scripting.executeScript hands back to the background worker.
(() => {
  const BLOCKS = "p, h1, h2, h3, h4, h5, h6, li, blockquote, pre, figcaption, dt, dd";
  // Controls are never prose: their labels ("Play", "100%", "Download") are not the article.
  const CONTROLS = "button, input, select, textarea, audio, video, canvas, svg, [role=button],"
    + " [role=slider], [role=progressbar], [role=toolbar], [role=menu], [role=menubar],"
    + " [role=tablist], [role=dialog], [role=switch], [aria-hidden=true], [hidden]";
  // What marks a media player or similar widget, whose whole box should go, not just its buttons.
  const WIDGET = "audio, video, input[type=range], [role=slider], [role=progressbar]";
  const MEDIA_TEXT = /^(\d{1,2}:\d{2}(:\d{2})?(\s*\/\s*\d{1,2}:\d{2}(:\d{2})?)?|\d{1,3}\s?%|[0-9.]+\s?[x×]|-?\d{1,2}:\d{2}\s+-?\d{1,2}:\d{2})$/i;

  const words = (el) => el.textContent.replace(/\s+/g, " ").trim().split(" ").filter(Boolean).length;

  // A player box is the widest ancestor of a slider/audio element that still holds no real
  // prose: no paragraph of a dozen words, and little text overall. Readability would turn its
  // divs into paragraphs of "0:00", "Michael", "USA"...
  // Formulas: MathML carries its TeX source in <annotation>, which would be read out as
  // "backslash mathbf". A single symbol ("where w is the weight") is kept as text; a formula is
  // left out, as in PDFs. Reference lists go too (footnotes stay: they are the author's words).
  function dropMathAndReferences(doc) {
    for (const m of doc.querySelectorAll("math")) {
      for (const a of m.querySelectorAll("annotation, annotation-xml")) a.remove();
      const t = m.textContent.replace(/\s+/g, "");
      m.replaceWith(doc.createTextNode(t.length <= 3 && m.getAttribute("display") !== "block" ? t : ""));
    }
    for (const el of doc.querySelectorAll("[class*=bibliograph], [id*=bibliograph], .references,"
                                          + " #references, .reflist, section.ltx_bibliography")) {
      el.remove();
    }
  }

  function dropWidgets(doc) {
    for (const el of doc.querySelectorAll(WIDGET)) {
      if (!el.isConnected) continue;
      let box = el;
      for (let up = el.parentElement, n = 0; up && up !== doc.body && n < 8;
           up = up.parentElement, n++) {
        const prose = [...up.querySelectorAll("p, li, blockquote")].some((p) => words(p) >= 12);
        if (prose || words(up) > 80) break;
        box = up;
      }
      box.remove();
    }
    for (const el of doc.querySelectorAll(CONTROLS)) el.remove();
  }

  // Readability's textContent loses paragraph breaks, and the server pauses longer at those,
  // so rebuild the text from block elements of its cleaned HTML.
  function toText(html) {
    // DOMParser never runs scripts, unlike assigning innerHTML on a live element
    const doc = new DOMParser().parseFromString(html, "text/html");
    const parts = [];
    for (const el of doc.body.querySelectorAll(BLOCKS)) {
      if (el.querySelector(BLOCKS)) continue;          // leaf blocks only, or text repeats
      const t = el.textContent.replace(/\s+/g, " ").trim();
      if (t) parts.push({ t, heading: /^H\d$/.test(el.tagName), item: el.tagName === "LI" });
    }
    return parts.length ? clean(parts).join("\n\n") : doc.body.textContent.trim();
  }

  // Whatever widget text got past dropWidgets: timestamps and percentages on their own, and runs
  // of four or more scraps (two or three words, no sentence) such as "Michael", "USA",
  // "Lauren", "England". List items are left alone: "2 eggs", "1 cup flour" are content.
  function clean(parts) {
    const scrap = (p) => !p.heading && !p.item && p.t.split(" ").length <= 3
      && !/[.!?:;"”]$/.test(p.t);
    const out = [];
    for (let i = 0; i < parts.length;) {
      if (MEDIA_TEXT.test(parts[i].t)) { i++; continue; }
      let j = i;
      while (j < parts.length && (scrap(parts[j]) || MEDIA_TEXT.test(parts[j].t))) j++;
      if (j - i >= 4) { i = j; continue; }
      out.push(parts[i].t);
      i++;
    }
    return out;
  }

  const selection = String(window.getSelection() || "").trim();
  if (selection.length > 40 && !window.__sawtWhole) {     // queueing takes the whole page
    return { title: "", text: selection, source: "selection" };
  }

  const copy = document.cloneNode(true);
  dropMathAndReferences(copy);
  dropWidgets(copy);
  const article = new Readability(copy).parse();
  if (article && article.content) {
    return { title: (article.title || document.title).trim(), text: toText(article.content),
             source: "article" };
  }
  return { title: document.title, text: document.body.innerText, source: "page" };
})();
