// Injected into the page being read. Finds each original sentence in the live DOM and marks
// the one being spoken with the CSS Custom Highlight API, which paints ranges without touching
// the page's markup — nothing to clean up, nothing for the site's own scripts to trip over.
(() => {
  if (window.__readAloudHighlighter) return;
  window.__readAloudHighlighter = true;

  const NAME = "sawt-reading";
  const WINDOW = 4000;          // chars ahead of the last match a sentence may be found in
  const USER_SCROLL_GRACE = 4000;

  let sentences = [];
  let ranges = [];
  let lastUserScroll = 0;

  for (const ev of ["wheel", "touchmove"]) {
    addEventListener(ev, () => { lastUserScroll = Date.now(); }, { passive: true });
  }
  addEventListener("keydown", (e) => {
    if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(e.key)) {
      lastUserScroll = Date.now();
    }
  });

  // The page's visible text with whitespace collapsed exactly as content.js and the server
  // collapse it, plus, per character, the text node and offset it came from.
  function indexText() {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => n.parentElement?.closest("script, style, noscript, template, textarea")
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    const chars = [];
    const nodes = [];
    const offsets = [];
    let space = true;
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const s = n.data;
      for (let i = 0; i < s.length; i++) {
        const ws = /\s/.test(s[i]);
        if (ws && space) continue;
        chars.push(ws ? " " : s[i]);
        nodes.push(n);
        offsets.push(i);
        space = ws;
      }
    }
    return { text: chars.join(""), nodes, offsets };
  }

  // Sentences are searched in order, each after the previous match, so a sentence repeated in
  // a sidebar or a later paragraph cannot steal the highlight. Until something has matched,
  // the whole page is searched; after that, only a window ahead of the last match.
  function prepare(list) {
    sentences = list;
    const { text, nodes, offsets } = indexText();
    ranges = [];
    let from = 0;
    let anchored = false;
    for (const s of sentences) {
      const needle = s.replace(/\s+/g, " ").trim();
      let at = needle ? text.indexOf(needle, from) : -1;
      if (anchored && at > from + WINDOW) at = -1;
      if (at < 0) {
        ranges.push(null);
        continue;
      }
      const end = at + needle.length - 1;
      const r = document.createRange();
      r.setStart(nodes[at], offsets[at]);
      r.setEnd(nodes[end], offsets[end] + 1);
      ranges.push(r);
      from = end + 1;
      anchored = true;
    }
    return ranges.filter(Boolean).length;
  }

  function show(i) {
    let r = ranges[i];
    // a page that re-rendered since prepare() leaves ranges pointing at detached nodes
    if (r && !r.startContainer.isConnected) {
      prepare(sentences);
      r = ranges[i];
    }
    if (!r) {
      CSS.highlights.delete(NAME);
      return;
    }
    CSS.highlights.set(NAME, new Highlight(r));

    // follow along, unless the reader has scrolled away on purpose in the last few seconds
    if (Date.now() - lastUserScroll < USER_SCROLL_GRACE) return;
    const rect = r.getBoundingClientRect();
    if (rect.top < 80 || rect.bottom > innerHeight - 80) {
      const el = r.startContainer.parentElement;
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    if (msg.to !== "page") return;
    if (msg.cmd === "prepare") reply({ found: prepare(msg.sentences), total: msg.sentences.length });
    if (msg.cmd === "show") show(msg.sentence);
    if (msg.cmd === "clear") CSS.highlights.delete(NAME);
  });
})();
