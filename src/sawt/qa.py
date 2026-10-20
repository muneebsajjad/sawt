"""Nobody can listen to six hours. Sample where the failures actually are.

Two signals catch most synthesis damage: a chapter whose words-per-minute is an outlier
(runaway or truncated synthesis), and silence runs (a chunk that produced nothing).
Plus a sampler that cuts the first N seconds of every chapter into one audition file.
"""
import argparse
import json
import pathlib
import statistics
import subprocess

from . import paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--manifest", help="override manifest path")
    ap.add_argument("--book", help="book slug (default: most recent)")
    ap.add_argument("--sample-seconds", type=int, default=20)
    ap.add_argument("--out", help="override qa output dir")
    args = ap.parse_args()

    mpath = paths.manifest_path(args.book, args.manifest)
    manifest = json.loads(mpath.read_text())
    out = pathlib.Path(args.out) if args.out else mpath.parent / "qa"
    out.mkdir(parents=True, exist_ok=True)

    wpms = [m["wpm"] for m in manifest.values()]
    med = statistics.median(wpms)
    print(f"median {med:.0f} wpm across {len(wpms)} chapters "
          f"(audiobook band is 150-160)\n")

    bad = False
    wavs = {cid: paths.wav_path(mpath, m) for cid, m in manifest.items()}
    missing = [cid for cid, w in wavs.items() if not w.exists()]
    if missing:
        raise SystemExit("missing audio for: " + ", ".join(missing)
                         + "\n  re-run: sawt synth")

    for cid, m in manifest.items():
        flags = []
        if abs(m["wpm"] - med) > med * 0.15:
            flags.append(f'wpm {m["wpm"]:.0f} vs median {med:.0f}')
        if m["seconds"] < 20:
            flags.append(f'only {m["seconds"]:.0f}s long')
        sil = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(wavs[cid]),
             "-af", "silencedetect=n=-50dB:d=3", "-f", "null", "-"],
            capture_output=True, text=True).stderr
        runs = sil.count("silence_start")
        if runs:
            flags.append(f"{runs} silence run(s) over 3s")
        if flags:
            bad = True
            print(f'{cid}  {m["title"][:45]}')
            for f in flags:
                print(f"    ! {f}")

    if not bad:
        print("no outliers — every chapter is within 15% of median pace, no long silences")

    # one audition file: the opening of every chapter, back to back
    parts = out / "sample_parts"; parts.mkdir(exist_ok=True)
    listing = out / "sample.txt"
    lines = []
    for i, (cid, m) in enumerate(manifest.items(), 1):
        dest = parts / f"{cid}.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-t", str(args.sample_seconds),
                        "-i", str(wavs[cid]), str(dest)], check=True)
        lines.append(f"file '{dest.resolve()}'")
    listing.write_text("\n".join(lines) + "\n")
    audition = out / "audition.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(listing), "-c:a", "libmp3lame", "-b:a", "64k",
                    str(audition)], check=True)
    print(f'\n-> {audition}  (first {args.sample_seconds}s of each chapter — listen to this)')


if __name__ == "__main__":
    main()
