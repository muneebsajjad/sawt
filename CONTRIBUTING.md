# Contributing

Thanks for helping. This project has one rule that shapes everything else: **nothing a user
reads may leave their machine.** No cloud APIs, no telemetry, no remote fonts or scripts in the
extension. A change that needs the network for anything but the one-time model download will
not be merged, however useful it is.

## Set up

You need [uv](https://docs.astral.sh/uv/) and Chrome (or another Chromium browser).

```bash
git clone https://github.com/muneebsajjad/sawt
cd sawt
uv sync                    # creates .venv with the engine and pytest
uv run pytest              # the text tests; no voice model needed
./sawt serve               # the engine; the first start downloads the model (~350MB)
```

Then load the extension: `chrome://extensions` → Developer mode → **Load unpacked** → pick
`extension/`. After editing anything in `extension/`, press reload on its card.

The unpacked copy gets the same extension ID as the Chrome Web Store version, because
`manifest.json` carries the store's public `key`. The engine only answers that ID, so keep the
key in place; to try a copy with a different ID, run `./sawt serve --allow-extension <its id>`.
Turn the store version off while the unpacked one is loaded: both use `Alt+R`.

A source checkout keeps books and output next to the code (`work/`, `out/`, both git-ignored).
Set `SAWT_HOME` to put them elsewhere.

## Where things are

See [docs/architecture.md](docs/architecture.md) for a map of the modules and how a sentence
travels from a web page to your speakers.

## Making a change

1. Open an issue first for anything bigger than a bug fix, so we agree on the approach before
   you spend the time.
2. Keep pull requests to one change. A fix plus an unrelated refactor is two PRs.
3. Add a test when the change is testable without the voice model — text normalization,
   sentence splitting, chunking and extraction all are. Put it in `tests/`.
4. **Listen to it.** For anything that changes what is spoken, run it and hear the result. Text
   that looks right can still sound wrong.
5. Match the surrounding code: comments say *why*, not what; short functions; no new
   dependencies without a reason in the PR.

## Good first issues

- **`Ch. XIV` is read as letters.** `textnorm.py` expands the `ch.` abbreviation only in lower
  case, and converts Roman numerals before abbreviations, so `Ch. XIV` never becomes "chapter
  fourteen". `tests/test_text.py::test_normalize_abbreviated_chapter` is the failing test; make
  it pass and remove its `xfail` marker.
- **Try the background engine on Linux or Windows.** `sawt agent install` registers a systemd
  user service or a Task Scheduler logon task (`src/sawt/agent.py`), but only macOS has been
  used for real. Install it, log out and back in, kill the engine, and report what happened.
- **Firefox.** The extension uses Manifest V3 and the offscreen API; Firefox needs a different
  way to keep audio playing after the popup closes.

## Reporting bugs

Use the issue templates. For a mispronunciation, paste the exact sentence; for a page that
reads the wrong text, include the URL. Security problems go through a private advisory instead
(see [SECURITY.md](SECURITY.md)).

## Licence

By contributing you agree that your work is released under the [MIT licence](LICENSE).
