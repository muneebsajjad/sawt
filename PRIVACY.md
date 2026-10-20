# Privacy policy

_Last updated: 20 October 2026_

Sawt reads web pages aloud using a voice engine that runs on your own computer.
It is built so that what you read never leaves your machine.

## What the extension handles

- **The text of the page you ask it to read.** When you click "Read this page", press the
  shortcut, or choose "Read selection aloud", the extension extracts the article text from that
  tab and sends it to the voice engine at `http://127.0.0.1:7865` — an address that only exists
  on your own computer. It is never sent to the developer or to any other server.
- **Your reading position.** The last sentence you heard on each page is saved in your browser's
  extension storage, so reading the page again resumes where you stopped. The 300 most recent
  pages are kept; finishing an article deletes its entry. This never leaves your browser.
- **Your voice and speed settings**, stored the same way.

## What it does not do

- No accounts, analytics, tracking, advertising or telemetry.
- No data is sold, shared or transferred to anyone.
- The extension reads a page only when you ask it to. It has no access to pages in the background.

## The voice engine

The engine (`sawt serve`) is open-source software you install and run yourself. It turns text
into speech on your computer and keeps a cache of generated audio on your disk, which you can
delete at any time. The only network access it ever makes is a one-time download of the voice
model files from the kokoro-onnx GitHub releases page the first time it starts.

## Contact

Questions: open an issue at https://github.com/muneebsajjad/sawt
