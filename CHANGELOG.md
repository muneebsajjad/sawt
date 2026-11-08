# Changelog

## 0.3.0 (engine and extension)

### New
- **Read PDFs.** Press `Alt+R` (or **Read this page** in the popup) on a PDF open in Chrome.
  The engine turns it into readable text and Sawt opens a reading copy in the next tab: the
  PDF's headings and paragraphs, without page numbers, running headers, footnote symbols,
  numeric citations like "[13]", tables, code or the reference list. Highlighting, meanings,
  word zoom and resume work there as on any article. Research papers skip the authors,
  universities and emails and start at the abstract (or the first section when there is none),
  and leave out figure and table captions, venue and copyright notices, and the contents page.
- PDFs saved on your computer work once **Allow access to file URLs** is on for Sawt in
  `chrome://extensions`; Sawt says so when it is needed.
- Very long PDFs are read up to the article limit (about 200,000 characters); the reading copy
  says so. Whole books still belong in `sawt extract`.

- **A reading queue.** Press `Alt+Q`, choose **Add this page** in the popup, or right-click
  a page, to save an article or PDF for later; then **Play the queue** reads them one after
  another. The text is saved when you add it, so you can close the tab: an article whose tab is
  still open is read there with its highlight, and one whose tab is gone opens as a reading
  copy in the background. A finished article leaves the queue, and the toolbar icon shows how
  many are waiting (it holds three). Everything stays in the browser on your computer. `Alt+Q` is new, so if
  Chrome gave it to another extension, set it in `chrome://extensions/shortcuts`.

- **Send to my phone.** In the popup, **Send to my phone** makes one MP3 of your queue (or of
  this page when the queue is empty) and shows a QR code. Scan it with your phone's camera, tap
  **Save to phone**, and listen offline on the way home. The phone fetches it straight from
  your computer over your Wi-Fi: no cloud, no account, no app. The link has a long random
  secret, serves only that MP3, and closes after 15 minutes or when you stop sharing. The phone
  needs to be on the same Wi-Fi; some office and guest networks keep devices from seeing each
  other. On macOS with the firewall on, allow the incoming connection the first time.

### Fixed
- **`sawt agent install` could fail on macOS when restarting the engine** (`launchctl bootstrap`
  status 5): launchd had not finished stopping the old engine yet. It now waits and retries.

### Upgrading
- `uv tool upgrade sawt`, then `sawt agent install`. The extension updates itself; with an
  older engine it reads web pages as before and asks for the update when given a PDF.

## 0.2.1 (engine and extension)

### Fixed
- **Reading could go silent for good.** A chunk the voice model cannot say (a lone "[" from a
  footnote marker, say) raised inside the engine's synthesis thread and stopped all audio, while
  the engine still answered as healthy; only a restart helped. Such chunks now play as a short
  silence and reading carries on, and the engine can no longer lose its synthesis thread to one bad
  chunk.
- **`/health` tells the truth**: it reports whether audio is being made, and says how to restart
  the engine if not.
- **Meaning cards covered the text** on pages that do not use `<p>` (paulgraham.com, older sites):
  they were placed beside the sentence instead of beside the column.

### Upgrading
- `uv tool upgrade sawt`, then `sawt agent install` to restart it. The extension updates itself.

## 0.2.0 (engine and extension)

### New
- **Meanings of hard words as you listen.** A card beside the article explains rare words in the
  sentence being read, using an offline Wiktionary glossary, or the article's own definition
  for acronyms like "MAOP". Choose how many in the popup (**Explain hard words for**), hide a
  word with **Don't explain again** (with Undo), and review the page's words in the popup.
- **Word zoom** (optional, off by default): the word being spoken is gently magnified, so you
  can follow along word by word.
- **Appearance: Auto, Light or Dark** for the popup, the meaning cards and the setup page.
- New default voice for the extension: Fable (UK) at 1.1×. Existing settings are kept; the
  book commands still default to Bella at 0.85×.

### Upgrading
- Run `uv tool upgrade sawt`, then `sawt agent install` (or restart `sawt serve`).
- **One-time downloads on first start:** a newer voice model (326MB, the first that reports
  when each word is spoken; the old 310MB file is deleted afterwards) and the glossary (~15MB).
  Reading works while the glossary downloads; meanings appear once it is ready.
- Articles you have listened to before are synthesized once more the next time, to record word
  timings.
- Each half works with the other's older version: a 0.1 engine simply shows no meanings or zoom.

## 0.1.2
- The engine runs in the background on macOS, Linux and Windows (`sawt agent install`).

## 0.1.1
- Pins the Chrome Web Store extension ID.

## 0.1.0
- First release: local read-aloud for the browser, and audiobooks from EPUB, PDF and TXT.
