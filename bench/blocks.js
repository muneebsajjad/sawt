// Runs inside a page: splits it into text blocks with the facts a reader of the page could see.
// The labels (read / skip) and every extractor's score are kept per block, by its order here.
(() => {
  const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "HEAD", "IFRAME", "OBJECT"]);
  const BLOCKISH = new Set(["P", "H1", "H2", "H3", "H4", "H5", "H6", "LI", "BLOCKQUOTE", "PRE",
    "FIGCAPTION", "DT", "DD", "TD", "TH", "CAPTION", "DIV", "SECTION", "ARTICLE", "ASIDE", "HEADER",
    "FOOTER", "NAV", "MAIN", "SPAN", "A", "BUTTON", "LABEL", "FIGURE", "TIME", "SUMMARY", "ADDRESS"]);
  const blocks = [];
  // a block: the nearest block-level element owning a run of text
  const owners = new Map();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    if (!t.textContent.trim()) continue;
    let el = t.parentElement, bad = false;
    for (let a = el; a; a = a.parentElement) if (SKIP_TAGS.has(a.tagName)) { bad = true; break; }
    if (bad) continue;
    // climb out of inline wrappers (a, em, code, span inside a paragraph)
    while (el.parentElement && el !== document.body) {
      const d = getComputedStyle(el).display;
      if (d !== "inline" && d !== "contents") break;
      el = el.parentElement;
    }
    if (!owners.has(el)) owners.set(el, []);
  }
  for (const el of owners.keys()) {
    const text = el.innerText?.replace(/\s+/g, " ").trim() || el.textContent.replace(/\s+/g, " ").trim();
    // only text that belongs to this element, not to a nested block already counted
    let own = "";
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let t = w.nextNode(); t; t = w.nextNode()) {
      let o = t.parentElement;
      while (o !== el && o && !owners.has(o)) o = o.parentElement;
      if (o === el) own += t.textContent;
    }
    own = own.replace(/\s+/g, " ").trim();
    if (!own) continue;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const anc = [];
    for (let a = el; a && a !== document.body && anc.length < 8; a = a.parentElement) {
      anc.push([a.tagName.toLowerCase(), (a.id || ""), (typeof a.className === "string" ? a.className : ""),
                a.getAttribute("role") || "", a.getAttribute("aria-label") || ""].join("|").slice(0, 160));
    }
    let linkChars = 0;
    for (const a of el.querySelectorAll("a")) linkChars += a.textContent.trim().length;
    blocks.push({
      i: blocks.length, tag: el.tagName.toLowerCase(), text: own.slice(0, 2000), full: text.length,
      links: linkChars, x: Math.round(r.left), y: Math.round(r.top + scrollY), w: Math.round(r.width),
      h: Math.round(r.height), font: parseFloat(cs.fontSize) || 0, weight: cs.fontWeight,
      visible: r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none",
      interactive: !!el.closest("button, a[href], [role=button], label, select, input, [onclick]"),
      anc,
    });
  }
  return blocks;
})();
