"""Progress of a synth run — including one started before this command existed.

Chunk cache keys are deterministic, so progress is not guessed from a log: the exact set of
chunks the book will produce is recomputed here and checked against the cache. That works for
a run started in another terminal, or one already hours in.
"""
import argparse
import json
import shutil
import sys
import time

import soundfile as sf

from . import paths
from .synth import chunk_key, load_dict, plan_pieces

RTF = 3.14          # measured generation speed: audio seconds per compute second


def bar(fraction, width=None):
    width = width or max(20, min(50, shutil.get_terminal_size((80, 20)).columns - 34))
    filled = int(fraction * width)
    return "█" * filled + "░" * (width - filled)


def survey(doc, pron, voice, speed, cache, no_normalize=False):
    """Every chunk the book will produce, and whether it is already rendered."""
    done = total = 0
    per_chapter, rendered = [], []
    for ch in doc["chapters"]:
        pieces = plan_pieces(ch, pron, not no_normalize)
        hits = 0
        for p in pieces:
            path = cache / f"{chunk_key(p['text'], voice, speed)}.wav"
            if path.exists():
                hits += 1
                if len(rendered) < 40:
                    rendered.append(path)
        per_chapter.append((ch["id"], ch["title"], hits, len(pieces)))
        done += hits
        total += len(pieces)
    return done, total, per_chapter, rendered


def seconds_per_chunk(rendered):
    """Compute cost of one chunk, from the audio already made rather than a guess."""
    if not rendered:
        return None
    durations = []
    for path in rendered:
        try:
            info = sf.info(path)
            durations.append(info.duration)
        except Exception:
            continue
    if not durations:
        return None
    return (sum(durations) / len(durations)) / RTF


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", help="book slug (default: most recent)")
    ap.add_argument("--voice", default="af_bella")
    ap.add_argument("--speed", type=float, default=0.85)
    ap.add_argument("--dict", default="pronounce.json")
    ap.add_argument("--no-normalize", action="store_true")
    ap.add_argument("--watch", action="store_true", help="refresh until complete")
    ap.add_argument("--interval", type=int, default=20)
    args = ap.parse_args()

    cpath = paths.chapters_path(args.book)
    doc = json.loads(cpath.read_text())
    pron = load_dict(paths.ROOT / args.dict)
    cache = paths.CACHE

    first = None
    while True:
        done, total, per_chapter, rendered = survey(doc, pron, args.voice, args.speed,
                                                    cache, args.no_normalize)
        now = time.time()
        if first is None:
            first = (now, done)

        frac = done / total if total else 1.0
        elapsed = now - first[0]
        made = done - first[1]
        rate = made / elapsed if elapsed > 5 and made else 0        # chunks per second
        eta = (total - done) / rate / 60 if rate else None
        if eta is None:                      # not watching long enough — estimate from audio
            per = seconds_per_chunk(rendered)
            eta = (total - done) * per / 60 if per else None

        line = f'\r  {bar(frac)} {frac*100:5.1f}%  {done:,}/{total:,} chunks'
        if eta is not None:
            line += f'  ~{eta:.0f} min left'
        elif args.watch:
            line += "  measuring rate..."

        if not args.watch:
            print(line.lstrip("\r"))
            for cid, title, hits, n in per_chapter:
                mark = "done" if hits == n else f"{hits}/{n}"
                print(f'    {cid}  {title[:40]:<40} {mark}')
            if done < total:
                per = seconds_per_chunk(rendered)
                if per:
                    print(f'\n  {total-done:,} chunks left  '
                          f'(~{(total-done)*per/3600:.1f}h at {per:.1f}s per chunk)')
                else:
                    print(f'\n  {total-done:,} chunks left')
            return

        # A carriage-return bar is invisible once redirected, so a pipe or a log file gets
        # one timestamped line per sample instead.
        if sys.stdout.isatty():
            sys.stdout.write(line + "   ")
        else:
            sys.stdout.write(f'{time.strftime("%H:%M:%S")}  {frac*100:5.1f}%  '
                             f'{done:,}/{total:,}'
                             + (f'  ~{eta:.0f} min left' if eta else "") + "\n")
        sys.stdout.flush()
        if done >= total:
            print("\n  complete — run: sawt qa && sawt build --format both")
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
