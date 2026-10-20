"""chapters.json -> one wav per chapter, via a per-chunk cache.

Generation of a full book runs for hours, so nothing here may depend on finishing in one go.
Every chunk is keyed by a hash of (text, voice, speed): change one paragraph and only that
paragraph is re-synthesised; interrupt at any point and re-running resumes.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys
import time

import numpy as np
import soundfile as sf
from tqdm import tqdm

from . import models, paths
from .textnorm import normalize

SR = 24000

# Kokoro degrades on very long inputs, so prose is split into sentence groups under this size.
MAX_CHARS = 420


def load_dict(path):
    """Pronunciation overrides, applied as whole-word replacements before synthesis."""
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def apply_dict(text, d):
    for word, say in d.items():
        text = re.sub(rf'\b{re.escape(word)}\b', say, text)
    return text


def chunk(text, max_chars=MAX_CHARS):
    """Split into speakable chunks on sentence boundaries, never mid-sentence.

    Paragraph breaks are kept as chunk boundaries so a pause can be inserted there.
    """
    out = []
    for para in re.split(r'\n\s*\n', text):
        para = " ".join(para.split())
        if not para:
            continue
        sents = re.split(r'(?<=[.!?:;]) +', para)
        cur = ""
        for s in sents:
            while len(s) > max_chars:                    # a sentence longer than the limit
                cut = s.rfind(", ", 0, max_chars)
                cut = cut if cut > 80 else max_chars
                out.append({"text": s[:cut].strip(), "para_end": False})
                s = s[cut:].strip()
            if len(cur) + len(s) + 1 <= max_chars:
                cur = f"{cur} {s}".strip()
            else:
                if cur:
                    out.append({"text": cur, "para_end": False})
                cur = s
        if cur:
            out.append({"text": cur, "para_end": False})
        if out:
            out[-1]["para_end"] = True
    return out


def silence(seconds):
    return np.zeros(int(SR * seconds), dtype=np.float32)


def chunk_key(text, voice, speed):
    """Cache identity of one spoken chunk. Voice and speed are part of it on purpose."""
    return hashlib.sha256(f"{text}|{voice}|{speed}".encode()).hexdigest()[:24]


def plan_pieces(chapter, pron, do_normalize=True, max_words=None):
    """The exact sequence of chunks a chapter will be spoken as.

    Shared with progress.py so a progress bar cannot drift from what synth actually does.
    """
    body = chapter["text"]
    if max_words:
        # cut at the last sentence end inside the budget, so a trial never ends mid-clause
        body = " ".join(body.split()[:max_words])
        cut = max(body.rfind(". "), body.rfind("! "), body.rfind("? "))
        if cut > 200:
            body = body[:cut + 1]

    prep = (lambda t: apply_dict(normalize(t), pron)) if do_normalize else \
        (lambda t: apply_dict(t, pron))

    pieces = [{"text": prep(chapter["title"]), "para_end": True, "is_title": True}]
    pieces += [dict(c, is_title=False) for c in chunk(prep(body))]
    return pieces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--chapters", help="override chapters.json path")
    ap.add_argument("--book", help="book slug (default: most recent)")
    ap.add_argument("--voice", default="am_adam")
    ap.add_argument("--speed", type=float, default=0.75, help="0.75 ~= 152 wpm, audiobook pace")
    ap.add_argument("--dict", default="pronounce.json")
    ap.add_argument("--no-normalize", action="store_true",
                    help="skip number/abbreviation expansion")
    ap.add_argument("--cache", help="override chunk cache dir (default: shared work/cache)")
    ap.add_argument("--outdir", help="override chapter wav dir")
    ap.add_argument("--only", help="one chapter id, e.g. ch003")
    ap.add_argument("--limit", type=int, help="stop after N chapters (for a trial run)")
    ap.add_argument("--max-words", type=int,
                    help="narrate only the first N words of each chapter — a trial page")
    ap.add_argument("--gap-sentence", type=float, default=0.18)
    ap.add_argument("--gap-para", type=float, default=0.55)
    ap.add_argument("--gap-title", type=float, default=1.0)
    args = ap.parse_args()

    cpath = paths.chapters_path(args.book, args.chapters)
    bdir = cpath.parent
    doc = json.loads(cpath.read_text())
    chapters = doc["chapters"]
    if args.only:
        chapters = [c for c in chapters if c["id"] == args.only]
    if args.limit:
        chapters = chapters[:args.limit]

    dpath = pathlib.Path(args.dict)
    pron = load_dict(dpath if dpath.is_absolute() else paths.ROOT / dpath)
    # the cache is shared across books on purpose: chunks are keyed by content hash
    cache = pathlib.Path(args.cache) if args.cache else paths.CACHE
    cache.mkdir(parents=True, exist_ok=True)
    outdir = pathlib.Path(args.outdir) if args.outdir else bdir / "chapters"
    outdir.mkdir(parents=True, exist_ok=True)

    kokoro = models.load()

    manifest = {}
    t_start = time.time()
    for ci, ch in enumerate(chapters, 1):
        out_wav = outdir / f'{ch["id"]}.wav'
        pieces = [silence(0.4)]

        # The chapter title is spoken, then held, so a listener can hear the seam.
        spoken = plan_pieces(ch, pron, not args.no_normalize, args.max_words)

        hit = miss = 0
        bar = tqdm(spoken, desc=f'{ch["id"]} {ch["title"][:28]}', unit="chunk",
                   disable=not sys.stderr.isatty(), leave=True,
                   bar_format="  {l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
        for i, piece in enumerate(bar):
            key = chunk_key(piece["text"], args.voice, args.speed)
            cached = cache / f"{key}.wav"
            if cached.exists():
                audio, _ = sf.read(cached, dtype="float32")
                hit += 1
            else:
                audio, sr = kokoro.create(piece["text"], voice=args.voice,
                                          speed=args.speed, lang="en-us")
                audio = np.asarray(audio, dtype="float32")
                # Write via a temp file and rename: a kill mid-write would otherwise leave a
                # truncated wav in the cache, which later runs would trust and reuse.
                tmp = cached.with_suffix(".part")
                sf.write(tmp, audio, sr, format="WAV")   # .part gives no format to infer
                tmp.replace(cached)
                miss += 1
            pieces.append(audio)
            gap = (args.gap_title if piece["is_title"]
                   else args.gap_para if piece["para_end"]
                   else args.gap_sentence)
            pieces.append(silence(gap))
            bar.set_postfix_str(f"{miss} new / {hit} cached", refresh=False)
            if not sys.stderr.isatty() and miss and miss % 25 == 0 and i:
                done = time.time() - t_start
                pct = (i + 1) / len(spoken) * 100
                eta = (done / max(i, 1)) * (len(spoken) - i) / 60
                print(f'    {ch["id"]} {i}/{len(spoken)} chunks ({pct:.0f}%)  '
                      f'{done/60:.1f} min elapsed, ~{eta:.0f} min left', file=sys.stderr)

        audio = np.concatenate(pieces)
        sf.write(out_wav, audio, SR)
        dur = len(audio) / SR
        spoken_words = sum(len(p["text"].split()) for p in spoken)
        manifest[ch["id"]] = {"title": ch["title"],
                              "wav": str(out_wav.relative_to(bdir)),
                              "seconds": round(dur, 2), "words": spoken_words,
                              "wpm": round(spoken_words / (dur / 60), 1),
                              "chunks": len(spoken), "cached": hit, "generated": miss}
        print(f'{ch["id"]} [{ci}/{len(chapters)}] {dur/60:6.1f} min  '
              f'{manifest[ch["id"]]["wpm"]:5.1f} wpm  '
              f'{miss} new / {hit} cached  {ch["title"][:40]}')

    mpath = bdir / "manifest.json"
    prev = json.loads(mpath.read_text()) if mpath.exists() else {}
    prev.update(manifest)
    mpath.write_text(json.dumps(prev, indent=2))

    total = sum(v["seconds"] for v in prev.values())
    print(f'\n{len(prev)} chapters rendered, {total/3600:.2f}h total audio')
    print(f'elapsed {(time.time()-t_start)/60:.1f} min  ->  {mpath}')


if __name__ == "__main__":
    main()
