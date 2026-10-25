# The browser extension

How reading a web page works, in detail. For setup, see the [README](../README.md).

## Overview

`extension/` is a Chrome extension that reads the current page aloud through a local
server, using the same normalization, `pronounce.json` and chunk cache as the books.

```bash
sawt agent install    # once: runs in the background from login; or `sawt serve` in a terminal
```

Install it from the [Chrome Web Store](https://chromewebstore.google.com/detail/sawt-read-aloud-locally/onfpjncnceogmahnimecmbofiplglnge), or for a local copy: `chrome://extensions` →
Developer mode → **Load unpacked** → pick `extension/` (remove the store version first; both
have the same ID).
Click the toolbar icon → **Read this page**, or press `Alt+R` (read / pause / resume). Right-click
a selection → **Read selection aloud** for pages where article detection picks the wrong block.

| | |
|---|---|
| First sound | ~0.8s after the click (model stays loaded; one sentence per chunk) |
| After that | gapless: synthesis runs ~2.8× realtime, 6 sentences ahead of playback |
| Cost of abandoning | only what was synthesized ahead — the worker stops at the lookahead |

**Highlighting.** The sentence being spoken is highlighted on the page and scrolled into view
(paused for a few seconds after you scroll yourself). The server splits sentences *before*
normalizing, so each chunk points back at text that is really on the page ("$5m", not "five
million dollars"); `highlight.js` finds them in order with the CSS Highlight API, so the page's
markup is never modified. Measured 99–100% of sentences matched on Paul Graham, Wikipedia,
Fowler's bliki and Simon Willison; a miss just means no highlight for that sentence.

**Resume.** The last sentence heard is saved per page (URL minus fragment and `utm_*`). Reading
that page again picks up there, at the start of the sentence, with a **Start over** button in the
popup. The position is matched by sentence text, so an article edited since still resumes in the
right place. Finishing an article forgets it; the 300 most recent pages are kept. Selections
are never saved.

How it fits together: `content.js` runs Mozilla's Readability on the page and rebuilds paragraph
breaks; `background.js` posts the text to `127.0.0.1:7865/read`; `offscreen.js` plays the
returned sentence wavs in order. Changing voice or speed in the popup re-requests the rest of
the article from the current sentence.

The server answers only requests that carry `X-Sawt: 1`, come from a
`chrome-extension://` origin (or none), and address `127.0.0.1`/`localhost` — so a web page
cannot drive it, even via DNS rebinding.

Limits: English only; text drawn as images (some titles) is not highlighted; pages that load text lazily need scrolling before you click; scanned or
canvas-rendered text cannot be read. After editing `extension/`, hit reload on its card in
`chrome://extensions`.

