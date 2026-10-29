// Injected into the page being read. Finds each original sentence in the live DOM and marks
// the one being spoken with the CSS Custom Highlight API, which paints ranges without touching
// the page's markup — nothing to clean up, nothing for the site's own scripts to trip over.
(() => {
  if (window.__readAloudHighlighter) return;
  window.__readAloudHighlighter = true;

  const NAME = "sawt-reading";
  const WORD = "sawt-word";
  const LINGER = 5000;          // ms a card stays after its sentence, to finish reading it
  const MAX_CARDS = 2;          // more than two at once is a wall of text beside the article
  const WINDOW = 4000;          // chars ahead of the last match a sentence may be found in
  const USER_SCROLL_GRACE = 4000;

  let sentences = [];
  let ranges = [];
  let page = null;              // indexText() of the last prepare, to find words inside sentences
  let spans = [];               // [start, end] of each found sentence in page.text
  let current = -1;             // sentence on screen, so a long sentence's 2nd chunk is a no-op
  let hideTimer = 0;
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
    page = indexText();
    const { text, nodes, offsets } = page;
    ranges = [];
    spans = [];
    current = -1;
    let from = 0;
    let anchored = false;
    for (const s of sentences) {
      const needle = s.replace(/\s+/g, " ").trim();
      let at = needle ? text.indexOf(needle, from) : -1;
      if (anchored && at > from + WINDOW) at = -1;
      if (at < 0) {
        ranges.push(null);
        spans.push(null);
        continue;
      }
      const end = at + needle.length - 1;
      spans.push([at, end]);
      const r = document.createRange();
      r.setStart(nodes[at], offsets[at]);
      r.setEnd(nodes[end], offsets[end] + 1);
      ranges.push(r);
      from = end + 1;
      anchored = true;
    }
    return ranges.filter(Boolean).length;
  }

  function show(i, words = []) {
    let r = ranges[i];
    // a page that re-rendered since prepare() leaves ranges pointing at detached nodes
    if (r && !r.startContainer.isConnected) {
      prepare(sentences);
      r = ranges[i];
    }
    const changed = i !== current;
    current = i;
    if (changed) lens?.remove();          // the next word event places it again
    if (!r) {
      CSS.highlights.delete(NAME);
      return;
    }
    CSS.highlights.set(NAME, new Highlight(r));
    if (changed) explain(i, r, words);

    // follow along, unless the reader has scrolled away on purpose in the last few seconds
    if (Date.now() - lastUserScroll < USER_SCROLL_GRACE) return;
    const rect = r.getBoundingClientRect();
    if (rect.top < 80 || rect.bottom > innerHeight - 80) {
      const el = r.startContainer.parentElement;
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }

  // ---- zooming the word being spoken ------------------------------------------------------

  // The page's text is never touched: a magnified copy of the word is drawn over it, in the
  // page's own font, and moved from word to word.
  const ZOOM = 1.1;             // the space between words is ~0.3em: more and the lens covers the neighbours
  let lens = null;

  function zoom(i, start, end) {
    const span = spans[i];
    if (i !== current || !span) {
      lens?.remove();
      return;
    }
    const at = span[0] + start;
    const last = span[0] + end - 1;
    if (last > span[1] || !page.nodes[at]?.isConnected) return;
    const r = document.createRange();
    r.setStart(page.nodes[at], page.offsets[at]);
    r.setEnd(page.nodes[last], page.offsets[last] + 1);
    const box = r.getClientRects()[0];
    if (!box) return;

    const root = cardRoot();
    if (!lens?.isConnected) {
      lens = el("div", "lens");
      lens.setAttribute("aria-hidden", "true");     // a visual echo; the page text is the text
      root.append(lens);
    }
    const font = getComputedStyle(page.nodes[at].parentElement);
    Object.assign(lens.style, {
      left: `${box.left + scrollX}px`, top: `${box.top + scrollY}px`,
      height: `${box.height}px`, lineHeight: `${box.height}px`,
      fontFamily: font.fontFamily, fontSize: font.fontSize, fontWeight: font.fontWeight,
      fontStyle: font.fontStyle, letterSpacing: font.letterSpacing,
    });
    lens.textContent = r.toString();
    // A gentle zoom-in per word. The Web Animations API restarts it without forcing a layout,
    // and a transform/opacity animation runs on the compositor, off the page's main thread.
    if (!reducedMotion.matches) {
      lens.animate([{ transform: "scale(1)", opacity: 0.6 }, { transform: `scale(${ZOOM})`, opacity: 1 }],
                   { duration: 180, easing: "cubic-bezier(.2, .8, .2, 1)" });
    }
  }
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");

  // ---- meanings of hard words -------------------------------------------------------------

  // The first whole-word match of `word` inside sentence i, as a Range.
  function wordRange(i, word) {
    const span = spans[i];
    if (!span) return null;
    const slice = page.text.slice(span[0], span[1] + 1);
    const esc = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const m = new RegExp(`(^|[^\\p{L}\\p{N}])(${esc})(?![\\p{L}\\p{N}])`, "u").exec(slice);
    if (!m) return null;
    const at = span[0] + m.index + m[1].length;
    const end = at + word.length - 1;
    const r = document.createRange();
    r.setStart(page.nodes[at], page.offsets[at]);
    r.setEnd(page.nodes[end], page.offsets[end] + 1);
    return r;
  }

  function explain(i, sentenceRange, words) {
    if (!words.length) {
      // the last card stays a moment, so a word near the end of a sentence can still be read
      clearTimeout(hideTimer);
      hideTimer = setTimeout(clearCards, LINGER);
      return;
    }
    clearTimeout(hideTimer);
    const marks = words.map((w) => wordRange(i, w.word)).filter(Boolean);
    if (marks.length) CSS.highlights.set(WORD, new Highlight(...marks));
    else CSS.highlights.delete(WORD);
    renderCards(words, sentenceRange);
  }

  let host = null;
  let shadow = null;
  let theme = "auto";           // the reader's appearance choice, from the popup

  chrome.storage?.local.get("theme").then((v) => setTheme(v.theme));
  chrome.storage?.local.onChanged.addListener((c) => { if (c.theme) setTheme(c.theme.newValue); });

  function setTheme(t) {
    theme = t || "auto";
    if (!host) return;
    if (theme === "light" || theme === "dark") host.dataset.theme = theme;
    else delete host.dataset.theme;
  }

  // Cards live in a closed shadow root: the page's CSS cannot restyle them, ours cannot leak.
  function cardRoot() {
    if (host?.isConnected) return shadow;
    host = document.createElement("sawt-meanings");
    host.style.cssText = "position:absolute;top:0;left:0;width:0;height:0;z-index:2147483647;";
    if (theme === "light" || theme === "dark") host.dataset.theme = theme;
    shadow = host.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = CARD_CSS;
    shadow.append(style);
    document.documentElement.append(host);
    return shadow;
  }

  function clearCards() {
    CSS.highlights.delete(WORD);
    shadow?.querySelectorAll(".stack").forEach((el) => el.remove());
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // "Don't explain again" acts at once and offers an undo, rather than asking first
  // (elementary HIG: always provide an undo).
  const UNDO_MS = 6000;
  let toastTimer = 0;
  let undo = null;

  function card(w) {
    const c = el("div", "card");
    const head = el("div", "head");
    head.append(el("span", "word", w.word));
    const hide = el("button", "hide", "Don't explain again");
    hide.onclick = () => dismiss(w.word, c);
    head.append(hide);
    c.append(head);
    // no part of speech: "adj." is dictionary jargon. A usage note like "figuratively" changes
    // the meaning, so it stays.
    for (const [, meaning, label] of w.senses.slice(0, 2)) {
      const row = el("p", "sense");
      if (label) row.append(el("span", "label", `${label[0].toUpperCase()}${label.slice(1)}:`), " ");
      row.append(meaning);
      c.append(row);
    }
    const src = el("div", "src");
    if (w.source === "page") {
      src.textContent = "As defined in this article";
    } else {
      const a = el("a", null, "From Wiktionary");
      a.href = `https://en.wiktionary.org/wiki/${encodeURIComponent(w.word)}`;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.title = "Wiktionary text, CC BY-SA 4.0";
      src.append(a);
    }
    c.append(src);
    return c;
  }

  function dismiss(word, c) {
    chrome.runtime.sendMessage({ to: "bg", cmd: "known", word });
    const stack = c.parentElement;
    const next = c.nextSibling;
    const sentence = current;
    c.remove();
    if (stack && !stack.querySelector(".card")) stack.remove();
    undo = () => {
      chrome.runtime.sendMessage({ to: "bg", cmd: "unknown", word });
      if (!stack || sentence !== current) return;      // reading has moved on: just forget it
      if (!stack.isConnected) cardRoot().append(stack);
      stack.insertBefore(c, next?.parentElement === stack ? next : null);
    };
    showToast(`Won't explain “${word}” again`);
  }

  function showToast(text) {
    const root = cardRoot();
    root.querySelector(".toast")?.remove();
    const t = el("div", "toast");
    t.setAttribute("role", "status");
    const b = el("button", null, "Undo");
    b.onclick = runUndo;
    t.append(el("span", null, text), b);
    root.append(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(closeToast, UNDO_MS);
  }

  function closeToast() {
    clearTimeout(toastTimer);
    shadow?.querySelector(".toast")?.remove();
    undo = null;
  }

  function runUndo() {
    undo?.();
    closeToast();
  }

  // Esc closes the cards; Ctrl/Cmd+Z undoes while the toast is up. Only these, and only then,
  // are taken from the page.
  addEventListener("keydown", (e) => {
    if (e.key === "Escape" && shadow?.querySelector(".stack")) {
      clearCards();
    } else if (undo && e.key.toLowerCase() === "z" && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
      e.preventDefault();
      runUndo();
    }
  }, true);

  // Beside the article column when there is room. Otherwise above the sentence, over text
  // already read; below it only when the sentence is too near the top of the window.
  function renderCards(words, sentenceRange) {
    const root = cardRoot();
    root.querySelectorAll(".stack").forEach((s) => s.remove());   // not the word marks
    const stack = el("div", "stack");
    for (const w of words.slice(0, MAX_CARDS)) stack.append(card(w));
    root.append(stack);

    const rect = sentenceRange.getBoundingClientRect();
    const column = sentenceRange.startContainer.parentElement?.closest("p, li, blockquote, div")
      ?.getBoundingClientRect() || rect;
    const width = Math.min(300, innerWidth - 32);
    let left = column.right + 24;
    let top = rect.top;
    stack.style.width = `${width}px`;
    if (left + width > innerWidth - 16) {
      left = Math.max(16, Math.min(rect.left, innerWidth - width - 16));
      const height = stack.offsetHeight;
      top = rect.top - height - 10 >= 8 ? rect.top - height - 10 : rect.bottom + 10;
    }
    stack.style.left = `${left + scrollX}px`;
    stack.style.top = `${top + scrollY}px`;
  }

  const DARK = `--bg: #1d1f26; --fg: #ececf1; --muted: #9a9ca8; --line: #2a2c35;
    --accent: #2dd4bf;
    --shadow: 0 3px 4px rgba(0,0,0,.25), 0 3px 3px -3px rgba(0,0,0,.45);
    --highlight: rgba(255,255,255,.07);   /* light catching the top edge: shadows barely show */`;

  const CARD_CSS = `
    :host { all: initial; }
    .stack, .toast { --bg: #ffffff; --fg: #16181d; --muted: #6b7280; --line: #e5e7eb;
                     --accent: #0d9488;
                     /* elementary's shadow level 2, the one its popovers use: a tight contact
                        shadow under a soft lift, rather than one big blur */
                     --shadow: 0 3px 4px rgba(0,0,0,.15), 0 3px 3px -3px rgba(0,0,0,.35);
                     --highlight: rgba(255,255,255,0);
                     font: 13px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    /* dark when chosen in the popup, or when the system is dark and light was not chosen */
    :host([data-theme="dark"]) :is(.stack, .toast) { ${DARK} }
    @media (prefers-color-scheme: dark) {
      :host(:not([data-theme="light"])) :is(.stack, .toast) { ${DARK} }
    }
    .stack { position: absolute; display: flex; flex-direction: column; gap: 6px;
             animation: fade .2s ease-out; }
    @keyframes fade { from { opacity: 0; } }
    .card { background: var(--bg); color: var(--fg); border: 1px solid var(--line);
            border-left: 3px solid var(--accent); border-radius: 10px; padding: 12px;
            box-shadow: inset 0 1px 0 var(--highlight), var(--shadow); }
    .head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
            margin-bottom: 4px; }
    .word { font-weight: 600; font-size: 14px; }
    button { font: inherit; font-size: 11px; color: var(--muted); background: none; border: 0;
             padding: 2px 6px; border-radius: 6px; cursor: pointer; }
    button:hover { color: var(--fg); background: var(--line); }
    button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
    .sense { margin: 2px 0 0; }
    .sense + .sense { margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--line); }
    .label { color: var(--accent); font-weight: 500; }   /* no italics: GNOME HIG */
    .src { margin-top: 6px; font-size: 11px; color: var(--muted); }
    .src a { color: inherit; }
    .lens { position: absolute; box-sizing: content-box; padding: 0 2px; margin-left: -2px;
            white-space: pre; pointer-events: none; color: #1a1a1a; background: #ffe58a;
            border-radius: 6px; transform: scale(${ZOOM}); transform-origin: 50% 60%;
            box-shadow: 0 1px 3px rgba(0,0,0,.12), 0 1px 2px rgba(0,0,0,.24); }
    .lens { will-change: transform; }
    .toast { position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%);
             display: flex; align-items: center; gap: 12px; padding: 8px 8px 8px 14px;
             background: var(--fg); color: var(--bg); border-radius: 10px;
             box-shadow: var(--shadow); animation: fade .2s ease-out; }
    .toast button { font-size: 12.5px; font-weight: 600; color: var(--bg); }
    .toast button:hover { background: rgba(127,127,127,.25); color: var(--bg); }
  `;

  chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
    if (msg.to !== "page") return;
    if (msg.cmd === "prepare") reply({ found: prepare(msg.sentences), total: msg.sentences.length });
    if (msg.cmd === "show") show(msg.sentence, msg.words);
    if (msg.cmd === "word") zoom(msg.sentence, msg.start, msg.end);
    if (msg.cmd === "clear") {
      CSS.highlights.delete(NAME);
      clearCards();
      lens?.remove();
      current = -1;
    }
  });
})();
