# Converting books

`sawt` turns an EPUB, PDF or plain-text book into a narrated `.m4b` with chapter markers
(or per-chapter mp3s). Building needs [FFmpeg](https://ffmpeg.org) on your `PATH`.

Files live in `~/Sawt` for an installed copy (`SAWT_HOME` overrides): put books in
`books/`, and the results land in `out/`.

## Measured on the author's Mac (CPU only)

| | |
|---|---|
| Throughput | **2.7× realtime** (a 90k-word book ≈ 6.5h audio, ~2.5h to generate) |
| Pace | Kokoro's default is 207–230 wpm, too fast for a book. **`--speed 0.75` → ~152 wpm**, the audiobook band |
| Re-runs | Fully cached: a re-run of an unchanged book is seconds, not hours |

## Pipeline

```bash
sawt extract books/mybook.epub        # -> work/<slug>/chapters.json
sawt inspect                          # READ THIS. extraction is what goes wrong
sawt trim --drop ch001 --renumber     # cut front matter / licence pages
sawt names --write                    # proper nouns by frequency -> pronounce.json
sawt voices --audition                # hear all 28 English voices on your own text
sawt synth --only ch001 --max-words 300   # one page, listen before committing hours
sawt synth                            # the whole book (resumable, cached)
sawt qa                               # outliers + audition.mp3
sawt build --format both              # -> out/<slug>.m4b and per-chapter mp3s
```


## Workflow that actually works

1. `extract`, then **`inspect`** — look at every HEAD and TAIL. Front matter welded onto chapter
   one, a table of contents read as prose, and a running header repeated every page all show here.
2. `trim` what should not be narrated.
3. `synth --limit 1` and listen to `work/<slug>/chapters/ch001.wav`. Fix pronunciation now, not after
   six hours of CPU.
4. `synth` the rest, `qa`, listen to `qa/audition.mp3`, then `build`.

## Many books at once

```bash
sawt batch books/*.epub --voice af_bella --speed 0.85 --jobs 2
```

Each book runs extract -> clean -> synth -> qa -> build. Finished stages are skipped, so a
batch killed overnight resumes instead of restarting. Logs land in `work/<slug>/batch.log`.

**`--jobs 2` is the sweet spot here.** One synth saturates about 5 of this machine's 12 cores,
so a second book is nearly free; a third mostly makes the first two slower.

`batch` skips the manual quality steps — `inspect`, `trim`, hand-tuned `pronounce.json`. For a
scanned or badly structured book, do those by hand first and let the batch pick up from there.
Add `--max-words 300` to trial every book cheaply before committing hours.

## Several books

Each book lives in `work/<slug>/`, so a second book cannot overwrite the first. The most
recently extracted one is active; every command takes `--book <slug>` to override.

```bash
sawt books                 # list, * marks active
sawt books --use metamorphosis
sawt qa --book metamorphosis
```

The chunk cache at `work/cache/` is deliberately shared: chunks are keyed by content hash, so
two books sharing a sentence share the audio.

## Input formats

| Format | Chapters | Metadata | Notes |
|---|---|---|---|
| **`.epub`** | from the spine — reliable | title + author | **best choice** |
| `.txt` / `.md` | heuristic headings | from a `Title:` / `Author:` header if present | matched the EPUB exactly on Kafka: 3 chapters, 22k words |
| `.pdf` | heuristic headings | from PDF metadata, often empty | needs a text layer; try `--headings titlecase` for non-fiction |

Anything else — `.mobi`, `.azw3`, `.docx`, `.html` — convert first:

```bash
ebook-convert input.azw3 output.epub     # Calibre
pandoc input.docx -o output.txt
```

Unsupported extensions fail with that hint rather than a stack trace.

### Heading detection

Plain text and PDF lose the markup that made a heading a heading, so each shape is matched
explicitly: `Chapter 4` / `Part Two`, a bare roman numeral (`II`), a bare number, and a short
ALL-CAPS line. `--headings titlecase` adds Title Case lines, which is what non-fiction PDFs
use — opt-in, because an aggressive match splits ordinary prose.

Sections that come out too short are **merged into the previous one**, never dropped; losing
text is worse than a lumpy chapter. Only boilerplate is discarded.

## Voices

28 English voices: 11 American female, 9 American male, 4 British female, 4 British male.
(The model holds 54, but the rest are other languages and need a matching `lang` code.)

```bash
sawt voices                          # the list
sawt voices --audition               # all of them read YOUR book's opening line
sawt voices --audition --filter bm   # just British male
```

Pacing varies by voice — `bm_george` is noticeably slower than `am_adam`, so pair a slow voice
with a higher `--speed`. A voice is a whole-book decision: changing it invalidates the cache.

## Pronunciation

A proper noun in a novel recurs constantly — "Gregor" appears 298 times in Metamorphosis,
"Utterson" 131 times in Jekyll — so one wrong pronunciation is not one defect, it is hundreds.
Find them before generating:

```bash
sawt names            # ranked by frequency, flags what is missing from the dictionary
sawt names --write    # append placeholders to pronounce.json
```

Then edit the *values* to phonetic spellings and re-run `synth`; only affected chunks regenerate.

```json
{ "Gregor": "Gregg or", "Samsa": "Sam sa" }
```

## Text normalization

Numbers, abbreviations, roman numerals and currency are expanded to spoken form before
synthesis, so `"By 1847 he had spent $5m, roughly 12.5%"` is read as *"By eighteen forty-seven
he had spent five million dollars, roughly twelve point five percent."* Also `Chapter XIV` →
Chapter fourteen, `21st` → twenty-first, `1920s` → nineteen twenties, `pp. 3-7` → pages three to seven.

The pronunciation dictionary is applied *after* normalization, so a hand-written override always
wins. Disable with `synth --no-normalize`.

## How the cache works

Every chunk is keyed `sha256(text + voice + speed)`. So:

- Interrupt a 2.5-hour run at any point; re-running resumes where it stopped.
- Fix one paragraph and only that paragraph is re-synthesized.
- Change voice or speed and everything regenerates, correctly — the key covers both.

Cache lives in `work/cache/`. Delete it to reclaim space; it only costs time.

## Chunking

Prose is split on sentence boundaries under 420 chars, never mid-sentence, with paragraph
breaks preserved as chunk boundaries. Gaps: 0.18s between sentences, 0.55s between paragraphs,
1.0s after a spoken chapter title. Sentence-chunking costs nothing — measured identical pacing
to one long call — and buys per-paragraph re-generation.

## Mastering

Raw Kokoro output peaks around **−0.3 dBFS**, which clips on cheap hardware and which retailers
reject. `build` masters to **−20 LUFS integrated, −3 dB peak** (ACX wants −23…−18 LUFS and
≤ −3 dB).

It takes two passes, because one does not work. `loudnorm`'s true-peak control is approximate
and the AAC encoder overshoots it further — measured results against a −3 dB target:

| chain | measured peak |
|---|---|
| no mastering | −0.3 dB |
| `loudnorm` alone | −1.9 dB |
| `loudnorm` + `alimiter` | −1.1 dB (the limiter's auto-level re-normalises) |
| **measure, then correct** | **−3.1 dB** |

So `build` encodes once, measures the real peak, computes the residual gain and re-encodes.
Every build prints the measured peak and mean with a verdict. Override with `--lufs` / `--peak`,
skip with `--no-master`.

## Known limits

- **Scanned PDFs do not work** — there is no text layer. OCR first.
- PDF chapter detection is heuristic; EPUB is reliable because the spine is explicit. Prefer
  EPUB wherever you have the choice.
- One voice throughout; no separate dialogue voice.
- Kokoro is English-only here (`lang="en-us"`).
- Gutenberg EPUBs often give generic section titles — `trim --retitle ch001="Part One"` fixes it.

## Legal

Fine for books you own, public-domain texts, and your own writing. Distributing a synthesized
copy of an in-copyright book is not.
