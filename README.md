<p align="center">
  <img src="https://raw.githubusercontent.com/muneebsajjad/sawt/main/docs/assets/sawt-pixel.svg" width="256" alt="Pixel-art open book with sound bars bouncing above it">
</p>

# Sawt

_صوت (sawt): Arabic for "voice" or "sound"._

**Listen to any web page, or turn a whole book into an audiobook, with a natural voice that
runs on your own computer.**

Free, private, offline. No account, no subscription, no usage limits, and nothing you read is
ever sent to a server: the voice model ([Kokoro](https://huggingface.co/hexgrad/Kokoro-82M),
82M parameters) runs locally on your CPU.

- **Read any article aloud** from the browser: one click or `Alt+R`. Menus, ads and sidebars
  are skipped, the sentence being spoken is highlighted, and every page resumes where you left off.
- **Convert books** (EPUB, PDF, TXT) into `.m4b` audiobooks with chapter markers, mastered to
  audiobook loudness standards.
- **28 English voices**, American and British, with adjustable speed.

> **Status: v0.1, early.** It works well for the author daily; expect rough edges.
> Bug reports and contributions are very welcome. See [CONTRIBUTING.md](https://github.com/muneebsajjad/sawt/blob/main/CONTRIBUTING.md).

## How it works

```
 Browser extension                        Your computer
┌───────────────────────┐   article text   ┌──────────────────────────────┐
│ finds the article     │ ───────────────▶ │ sawt serve              │
│ plays + highlights    │ ◀─────────────── │ Kokoro voice model (CPU)     │
└───────────────────────┘   sentence audio  └──────────────────────────────┘
                     only over 127.0.0.1 - never the internet
```

The extension can't run a voice model by itself, so it talks to a small engine you run
locally. The engine keeps the model loaded, synthesizes a few sentences ahead of playback, and
caches the audio, so re-opening an article plays instantly.

## Install

**1. Install the engine.** You need [uv](https://docs.astral.sh/uv/), the Python installer
(skip this if `uv --version` already works):

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then:

```bash
uv tool install sawt
sawt serve        # first start downloads the voice model once (~350MB)
```

On macOS, `sawt agent install` starts the engine at login instead, so you never think
about it again.

**2. Add the browser extension** from the Chrome Web Store _(link coming with the first store
release)_. Its setup page checks that the engine is running.

**3. Open any article and press `Alt+R`.**

## Usage

### Reading web pages

| Do this | To |
|---|---|
| Toolbar icon → **Read this page**, or `Alt+R` | Read the article |
| `Alt+R` again | Pause / resume |
| Right-click selected text → **Read selection aloud** | Hear just that, when the page's article detection picks the wrong block |
| Popup → voice / speed | Change it mid-article; reading continues from the current sentence |

More: [docs/extension.md](https://github.com/muneebsajjad/sawt/blob/main/docs/extension.md) (highlighting, resume, limits).

### Converting books

Needs [FFmpeg](https://ffmpeg.org) on your `PATH`.

```bash
sawt extract ~/Downloads/mybook.epub     # -> chapters
sawt inspect                             # check what extraction produced
sawt synth                               # synthesize (hours for a novel; resumable)
sawt build                               # -> ~/Sawt/out/<book>.m4b
```

Or several at once, unattended: `sawt batch books/*.epub --voice af_bella --speed 0.85`.
The full guide (voices, pronunciation fixes, trimming front matter, quality checks):
[docs/books.md](https://github.com/muneebsajjad/sawt/blob/main/docs/books.md).

Run `sawt` with no arguments for every command.

## Configuration

| Setting | Default | What it does |
|---|---|---|
| `SAWT_HOME` | `~/Sawt` | Where books, output, the audio cache and `pronounce.json` live |
| `SAWT_MODELS` | `~/.cache/sawt/models` | Where the voice model is stored |
| `SAWT_EXTENSION_IDS` | the published extension | Extra extension IDs the engine accepts (comma-separated), e.g. a local unpacked copy |
| `sawt serve --port` | `7865` | Port the engine listens on (the extension expects 7865) |
| `pronounce.json` | — | Whole-word pronunciation fixes, e.g. `{"Gregor": "Gregg or"}` |

## Platform support

| | Engine | Start at login | Extension |
|---|---|---|---|
| macOS | ✅ | ✅ `sawt agent install` | ✅ Chrome; other Chromium browsers should work |
| Linux | ✅ | run `sawt serve` yourself | ✅ Chrome / Chromium |
| Windows | ⚠️ expected to work, untested | run `sawt serve` yourself | ✅ Chrome |

English only for now. Firefox and Safari are not supported yet.

## Privacy and security

- The extension reads a page only when you ask, and sends its text only to `127.0.0.1`.
- The engine makes one network request ever: the first-run model download, verified against
  pinned SHA-256 hashes.
- The engine refuses requests from web pages and from other extensions. Details in
  [SECURITY.md](https://github.com/muneebsajjad/sawt/blob/main/SECURITY.md); the full policy is in [PRIVACY.md](https://github.com/muneebsajjad/sawt/blob/main/PRIVACY.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| Popup says the engine isn't running | Start it: `sawt serve`. Check it answers: `curl -H "X-Sawt: 1" http://127.0.0.1:7865/health` |
| `sawt: command not found` after install | Open a new terminal, or run `uv tool update-shell` |
| Nothing is read on a page | Scroll first if the page loads text lazily, or select the text and right-click → **Read selection aloud** |
| A name is mispronounced | Add it to `pronounce.json` in `SAWT_HOME` with a phonetic spelling |
| `build` fails | Install FFmpeg (`brew install ffmpeg`, `apt install ffmpeg`, or `winget install ffmpeg`) |

## Roadmap

- Chrome Web Store release, with the engine's extension ID pinned
- Start at login on Linux and Windows
- A desktop app that bundles the engine, so no terminal is needed
- Firefox support
- More languages (Kokoro has voices for Spanish, French, Hindi, Italian, Japanese, Portuguese
  and Chinese)

Ideas and votes welcome in [issues](https://github.com/muneebsajjad/sawt/issues).

## Contributing

Pull requests are welcome, from typo fixes to new features. Start with
[CONTRIBUTING.md](https://github.com/muneebsajjad/sawt/blob/main/CONTRIBUTING.md) (setup takes a couple of minutes) and
[docs/architecture.md](https://github.com/muneebsajjad/sawt/blob/main/docs/architecture.md) for a map of the code. Issues marked
_good first issue_ are a gentle way in.

## Credits

- [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad, the voice model (Apache-2.0)
- [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx), which runs it on the CPU (MIT)
- [Readability](https://github.com/mozilla/readability) by Mozilla, which finds the article on
  a page (Apache-2.0)
- Pronunciation falls back to [espeak-ng](https://github.com/espeak-ng/espeak-ng) (GPL-3.0),
  installed as a dependency of kokoro-onnx

Convert books you own, public-domain texts and your own writing. Distributing a synthesized
copy of an in-copyright book is not allowed.

## Licence

[MIT](https://github.com/muneebsajjad/sawt/blob/main/LICENSE)
