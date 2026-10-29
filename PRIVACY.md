# Privacy policy

_Last updated: 30 October 2026_

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
- **Your settings** (voice, speed, how many hard words to explain, word zoom, appearance) and the
  words you marked "Don't explain again", stored the same way. They never leave your browser.

## What it does not do

- No accounts, analytics, tracking, advertising or telemetry.
- No data is sold, shared or transferred to anyone.
- The extension reads a page only when you ask it to. It has no access to pages in the background.

## The voice engine

The engine (`sawt serve`) is open-source software you install and run yourself. It turns text
into speech on your computer and keeps a cache of generated audio on your disk, which you can
delete at any time. The only network access it ever makes is a one-time download, the first time it starts, of
the voice model (from the kokoro-onnx GitHub releases page) and of the word glossary (from
Sawt's own GitHub releases page). Word meanings are looked up in that file on your computer;
the words you read are never sent anywhere to be defined.

A meaning card has a "From Wiktionary" link. Wiktionary is contacted only if you click it.

## Contact

Questions: open an issue at https://github.com/muneebsajjad/sawt
