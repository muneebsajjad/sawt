# Architecture

Two programs that only meet over `127.0.0.1:7865`:

```
 Browser                                       Your computer
┌──────────────────────────────┐             ┌─────────────────────────────────────┐
│ content.js  Readability →     │             │ sawt serve   (serve.py)        │
│             article text      │  POST /read │   split sentences                   │
│ background.js  owns state ────┼────────────▶│   normalize → pronounce.json        │
│                               │             │   chunk → key = sha256(text,voice,  │
│ offscreen.js  plays wavs  ◀───┼─────────────┤          speed)                     │
│                               │ GET /chunk  │   Kokoro (ONNX, CPU) → cache/*.wav  │
│ highlight.js  CSS Highlight   │   /<key>.wav│   worker stays 6 chunks ahead       │
│   meaning cards, word zoom    │ /<key>.words│   word timings beside each wav      │
│                               │       .json │   glossary.sqlite → hard words      │
└──────────────────────────────┘             └─────────────────────────────────────┘
```

The book pipeline uses the same text path and the same cache, from the command line instead of
the browser.

## Engine (`src/sawt/`)

| Module | Job |
|---|---|
| `cli.py` | `sawt <command>` - picks the module, hands it the rest of the arguments; `agent` (launchd) lives here |
| `models.py` | Finds the Kokoro model files, downloads and SHA-256-checks them on first use |
| `paths.py` | Where files live (`SAWT_HOME`, a source checkout, or `~/Sawt`), per-book directories, the active book |
| `serve.py` | The local HTTP server for the extension: sessions, lookahead worker, origin checks |
| `glossary.py` | Hard words in an article and their meanings: the downloaded Wiktionary glossary, acronyms the article defines itself, rarity from `wordfreq` |
| `wordtime.py` | When each word is spoken: groups the model's phoneme timings into words and matches them back to the words on the page |
| `textnorm.py` | Numbers, abbreviations, roman numerals, currency → spoken form |
| `synth.py` | Chunk → normalize → dictionary → synthesize → cache → one wav per chapter |
| `extract.py` | EPUB/PDF/TXT → `chapters.json`. De-hyphenates, strips footnote markers and page numbers, cuts Project Gutenberg boilerplate |
| `inspect_book.py` | Chapter table + head/tail of each chapter + outlier flags |
| `trim.py` | Drop or retitle chapters; keeps a `.bak` |
| `clean.py` | Repair scanned-book text: drop citation debris, fix OCR letter confusions |
| `names.py` | Proper nouns ranked by frequency, to fix in `pronounce.json` before generating |
| `voices.py` | List and audition the English voices on the book's own opening |
| `progress.py` | How much of a book is synthesized |
| `qa.py` | wpm outliers, silence runs, and an audition file |
| `assemble.py` | m4b with chapter marks + metadata, and/or per-chapter mp3s, mastered to −20 LUFS |
| `batch.py` | Several books unattended; re-invokes `python -m sawt` per stage |
| `books.py` | List books, switch the active one |

`pronounce.json` at the files root holds whole-word replacements applied before synthesis.

## Extension (`extension/`)

| File | Job |
|---|---|
| `background.js` | The service worker. Owns reading state, talks to the engine, saves positions |
| `content.js` | Runs Mozilla's Readability on the page and rebuilds paragraph breaks |
| `offscreen.js` | Plays the sentence wavs in order; the only part that touches audio |
| `highlight.js` | Highlights the sentence being spoken with the CSS Highlight API, without touching the page's markup; draws the meaning cards and the word zoom in a closed shadow root |
| `popup.*` | The toolbar popup: controls, voice and speed, meanings, word zoom, appearance, the setup prompt |
| `theme.js` | Applies the Auto / Light / Dark choice to the extension's own pages |
| `welcome.*` | First-run setup page with a live check for the engine |
| `vendor/Readability.js` | Mozilla Readability, Apache-2.0, unmodified |

## Design rules

- **Local only.** The engine's only outbound requests are the one-time downloads of the voice
  model and the glossary, each checked against a pinned SHA-256.
- **Everything resumable.** Chunks are content-addressed, so an interrupted book resumes and an
  edited paragraph is the only thing regenerated.
- **Split before normalizing.** The extension highlights by sentence, so each chunk must point
  back at text that is really on the page ("$5m", not "five million dollars").
