"""Chapter wavs -> a single .m4b with chapter markers, or per-chapter mp3s.

A six-hour single file with no chapter marks is unusable in a player, so m4b is the default:
AAC in an MP4 container plus an ffmetadata chapter table, which every audiobook app reads.

Loudness is handled in two passes. `loudnorm` sets the integrated level, but its true-peak
control is approximate and the AAC encoder overshoots it further — measured at -1.1 dB against
a -3 dB target even with a limiter in the chain. So the first pass is measured, the residual
gain is computed, and the final encode applies it. Verified, not assumed.
"""
import argparse
import json
import pathlib
import subprocess
import tempfile

from . import paths


def peak_db(path):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path),
                          "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "max_volume:" in line:
            return float(line.split("max_volume:")[1].strip().split()[0])
    return 0.0


def mean_db(path):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path),
                          "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].strip().split()[0])
    return 0.0


def encode(input_args, filters, codec_args, dest):
    cmd = ["ffmpeg", "-v", "error", "-y", *input_args]
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd += [*codec_args, str(dest)]
    subprocess.run(cmd, check=True)


def encode_to_ceiling(input_args, base_filters, codec_args, dest, peak_target, suffix):
    """Encode, measure the real peak, then re-encode with the correction applied."""
    if not base_filters:
        encode(input_args, [], codec_args, dest)
        return
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        probe_path = pathlib.Path(tmp.name)
    try:
        encode(input_args, base_filters, codec_args, probe_path)
        measured = peak_db(probe_path)
        correction = peak_target - measured
        filters = base_filters if abs(correction) < 0.05 else \
            base_filters + [f"volume={correction:.2f}dB"]
        encode(input_args, filters, codec_args, dest)
    finally:
        probe_path.unlink(missing_ok=True)


def ffmetadata(manifest, title, author):
    lines = [";FFMETADATA1", f"title={title}", f"artist={author}",
             f"album={title}", "genre=Audiobook"]
    start = 0
    for cid, m in manifest.items():
        end = start + int(m["seconds"] * 1000)
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}",
                  f'title={m["title"]}']
        start = end
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--chapters", help="override chapters.json path")
    ap.add_argument("-m", "--manifest", help="override manifest path")
    ap.add_argument("--book", help="book slug (default: most recent)")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--format", choices=["m4b", "mp3", "both"], default="m4b")
    ap.add_argument("--bitrate", default="64k", help="64k mono is transparent for speech")
    ap.add_argument("--cover", help="cover image to embed (m4b only)")
    ap.add_argument("--lufs", type=float, default=-20.0,
                    help="integrated loudness target; retailers want -23..-18")
    ap.add_argument("--peak", type=float, default=-3.0,
                    help="peak ceiling in dB; retailers want -3 or lower")
    ap.add_argument("--no-master", action="store_true", help="skip loudness normalisation")
    args = ap.parse_args()

    cpath = paths.chapters_path(args.book, args.chapters)
    mpath = paths.manifest_path(args.book, args.manifest)
    doc = json.loads(cpath.read_text())
    manifest = json.loads(mpath.read_text())

    # keep chapter order from chapters.json, not dict insertion order
    order = [c["id"] for c in doc["chapters"] if c["id"] in manifest]
    manifest = {cid: manifest[cid] for cid in order}
    if not manifest:
        raise SystemExit("manifest is empty — run synth.py first")

    wavs = {cid: paths.wav_path(mpath, m) for cid, m in manifest.items()}
    absent = [cid for cid, w in wavs.items() if not w.exists()]
    if absent:
        raise SystemExit("missing audio for: " + ", ".join(absent)
                         + "\n  re-run: sawt synth")

    out = pathlib.Path(args.out)
    if not out.is_absolute():
        out = paths.ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    work = mpath.parent
    slug = paths.slugify(doc["title"], "audiobook")

    base_filters = [] if args.no_master else [
        f"loudnorm=I={args.lufs}:TP={args.peak}:LRA=11"]

    if args.format in ("mp3", "both"):
        mp3dir = out / f"{slug}-chapters"
        mp3dir.mkdir(exist_ok=True)
        for i, (cid, m) in enumerate(manifest.items(), 1):
            dest = mp3dir / f"{i:03d}-{cid}.mp3"
            codec = ["-c:a", "libmp3lame", "-b:a", args.bitrate, "-ac", "1",
                     "-metadata", f'title={m["title"]}',
                     "-metadata", f'album={doc["title"]}',
                     "-metadata", f'artist={doc["author"]}',
                     "-metadata", f"track={i}"]
            encode_to_ceiling(["-i", str(wavs[cid])], base_filters, codec, dest,
                              args.peak, ".mp3")
        print(f"-> {mp3dir}/  ({len(manifest)} files)")

    if args.format in ("m4b", "both"):
        concat = work / "concat.txt"
        concat.write_text("".join(f"file '{wavs[cid].resolve()}'\n" for cid in manifest))
        meta = work / "chapters.ffmeta"
        meta.write_text(ffmetadata(manifest, doc["title"], doc["author"]))

        inputs = ["-f", "concat", "-safe", "0", "-i", str(concat), "-i", str(meta)]
        maps = ["-map", "0:a"]
        if args.cover:
            inputs += ["-i", args.cover]
            maps += ["-map", "2:v", "-disposition:v", "attached_pic", "-c:v", "mjpeg"]
        codec = ["-map_metadata", "1", *maps, "-c:a", "aac", "-b:a", args.bitrate,
                 "-ac", "1", "-movflags", "+faststart"]

        dest = out / f"{slug}.m4b"
        encode_to_ceiling(inputs, base_filters, codec, dest, args.peak, ".m4b")

        probe = subprocess.run(["ffprobe", "-v", "error", "-show_chapters",
                                "-show_entries", "format=duration", "-of", "json", str(dest)],
                               capture_output=True, text=True)
        info = json.loads(probe.stdout)
        dur = float(info["format"]["duration"])
        peak, mean = peak_db(dest), mean_db(dest)
        verdict = "ok" if peak <= args.peak + 0.5 else \
            f"CHECK — peak above {args.peak} dB, retailers reject this"
        print(f"-> {dest}")
        print(f'   {len(info.get("chapters", []))} chapter marks, {dur/3600:.2f}h, '
              f'{dest.stat().st_size/1e6:.0f} MB')
        print(f"   peak {peak:.1f} dB, mean {mean:.1f} dB  [{verdict}]")


if __name__ == "__main__":
    main()
