# Changelog

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
