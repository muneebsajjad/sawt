"""List voices, and audition them on the actual book.

A voice is a whole-book decision — changing it invalidates the cache — so it is worth two
minutes to hear them read your own prose rather than picking a name off a list.
"""
import argparse
import json
import pathlib
import re
import subprocess

import numpy as np
import soundfile as sf

from . import models, paths

SR = 24000

# Kokoro's prefix encodes language + gender. Only the English sets work with lang="en-us".
LANGS = {
    "a": ("American English", "en-us"), "b": ("British English", "en-gb"),
    "e": ("Spanish", None), "f": ("French", None), "h": ("Hindi", None),
    "i": ("Italian", None), "j": ("Japanese", None), "p": ("Portuguese", None),
    "z": ("Mandarin", None),
}
GENDER = {"f": "female", "m": "male"}

DEFAULT_LINE = ("One morning, when Gregor Samsa woke from troubled dreams, he found himself "
                "transformed in his bed into a horrible vermin.")


def describe(name):
    lang, _ = LANGS.get(name[0], ("unknown", None))
    return lang, GENDER.get(name[1], "?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="include non-English voices")
    ap.add_argument("--audition", action="store_true",
                    help="synthesize every listed voice reading the same line")
    ap.add_argument("--text", help="line to audition (default: the book's own opening)")
    ap.add_argument("-c", "--chapters", help="override chapters.json path")
    ap.add_argument("--book", help="book slug (default: most recent)")
    ap.add_argument("--speed", type=float, default=0.75)
    ap.add_argument("--out", help="override audition output dir")
    ap.add_argument("--filter", default="", help="substring, e.g. 'bm' for British male")
    args = ap.parse_args()

    kokoro = models.load()

    names = sorted(kokoro.get_voices())
    if not args.all:
        names = [n for n in names if n[0] in "ab"]
    if args.filter:
        names = [n for n in names if args.filter in n]

    print(f"{len(names)} voices" + ("" if args.all else " (English; --all for the rest)") + "\n")
    for n in names:
        lang, gender = describe(n)
        print(f"  {n:<16} {lang:<18} {gender}")

    if not args.audition:
        print("\naudition them on your book's own opening line:")
        print("  sawt voices --audition            # all English voices")
        print("  sawt voices --audition --filter bm  # just British male")
        return

    try:
        bdir = paths.book_dir(args.book)
        cpath = paths.chapters_path(args.book, args.chapters)
    except SystemExit:                      # no book extracted yet — audition still works
        bdir, cpath = paths.WORK, pathlib.Path("/nonexistent")
    outdir = pathlib.Path(args.out) if args.out else bdir / "qa" / "voices"

    line = args.text
    if not line:
        if cpath.exists():
            doc = json.loads(cpath.read_text())
            text = doc["chapters"][0]["text"]
            sents = re.split(r'(?<=[.!?]) +', text)
            line = " ".join(sents[:2])[:280]
        else:
            line = DEFAULT_LINE

    out = outdir; out.mkdir(parents=True, exist_ok=True)
    print(f'\nauditioning {len(names)} voices on:\n  "{line[:90]}..."\n')

    parts = []
    for i, name in enumerate(names, 1):
        spoken_name = name.split("_")[1]
        intro, _ = kokoro.create(f"{spoken_name}.", voice=name, speed=0.9, lang="en-us")
        body, _ = kokoro.create(line, voice=name, speed=args.speed, lang="en-us")
        clip = np.concatenate([np.asarray(intro, dtype="float32"),
                               np.zeros(int(SR * 0.35), dtype="float32"),
                               np.asarray(body, dtype="float32"),
                               np.zeros(int(SR * 0.7), dtype="float32")])
        dest = out / f"{name}.wav"
        sf.write(dest, clip, SR)
        parts.append(dest)
        lang, gender = describe(name)
        print(f'  [{i}/{len(names)}] {name:<16} {len(clip)/SR:5.1f}s  {lang}, {gender}')

    listing = out / "concat.txt"
    listing.write_text("\n".join(f"file '{p.resolve()}'" for p in parts) + "\n")
    reel = out.parent / "voice-audition.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c:a", "libmp3lame", "-b:a", "64k", str(reel)],
                   check=True)
    print(f"\n-> {reel}   (each voice says its own name, then reads the line)")
    print(f"   individual clips in {out}/")
    print(f"\nthen:  sawt synth --voice <name> --only ch001 --max-words 300")


if __name__ == "__main__":
    main()
