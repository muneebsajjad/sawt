"""Convert several books in one unattended run.

Each book goes through extract -> clean -> synth -> build. Stages already finished are
skipped, so a batch killed overnight resumes where it stopped rather than starting over.

Parallelism is modest on purpose: one synth saturates about 5 of this machine's 12 cores, so
--jobs 2 is near-free and --jobs 3 mostly makes both books slower.
"""
import argparse
import concurrent.futures
import json
import pathlib
import subprocess
import sys
import time

from . import paths

ROOT = paths.ROOT
DRIVER = [sys.executable, "-m", "sawt"]   # same interpreter, so an installed copy works


def run(args_list, log):
    with open(log, "a") as fh:
        fh.write(f"\n$ {' '.join(str(a) for a in args_list)}\n")
        fh.flush()
        return subprocess.run(args_list, stdout=fh, stderr=subprocess.STDOUT).returncode


def slug_for(path):
    """The slug extract would choose, without re-reading the whole book."""
    for d in sorted(paths.WORK.iterdir()) if paths.WORK.exists() else []:
        cj = d / "chapters.json"
        if d.is_dir() and cj.exists():
            doc = json.loads(cj.read_text())
            if pathlib.Path(doc.get("source", "")).name == path.name:
                return d.name
    return None


def process(path, args):
    """One book, end to end. Returns (name, status, seconds)."""
    started = time.time()
    name = path.name
    log = ROOT / "batch.log" if args.single_log else None

    slug = slug_for(path)
    if slug is None:
        probe = paths.WORK / "_batch"; probe.mkdir(parents=True, exist_ok=True)
        rc = run([*DRIVER, "extract", str(path)], log or probe / "extract.log")
        if rc != 0:
            return name, "extract failed", time.time() - started
        slug = slug_for(path)
        if slug is None:
            return name, "extract produced nothing", time.time() - started

    bdir = paths.WORK / slug
    log = log or bdir / "batch.log"

    # clean once: the marker stops a resumed batch from re-cleaning already-clean text
    cleaned = bdir / ".cleaned"
    if not args.no_clean and not cleaned.exists():
        if run([*DRIVER, "clean", "--book", slug, "--apply"], log) == 0:
            cleaned.write_text(time.strftime("%Y-%m-%d %H:%M"))

    synth = [*DRIVER, "synth", "--book", slug, "--voice", args.voice,
             "--speed", str(args.speed)]
    if args.max_words:
        synth += ["--max-words", str(args.max_words)]
    if run(synth, log) != 0:
        return name, "synth failed", time.time() - started

    run([*DRIVER, "qa", "--book", slug], log)

    if run([*DRIVER, "build", "--book", slug, "--format", args.format], log) != 0:
        return name, "build failed", time.time() - started

    return name, f"done -> out/ ({slug})", time.time() - started


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("books", nargs="+", help="book files, e.g. books/*.epub")
    ap.add_argument("--voice", default="af_bella")
    ap.add_argument("--speed", type=float, default=0.85)
    ap.add_argument("--format", choices=["m4b", "mp3", "both"], default="m4b")
    ap.add_argument("--jobs", type=int, default=1,
                    help="books at once; 2 is the sweet spot on a 12-core machine")
    ap.add_argument("--max-words", type=int, help="trial run: first N words of each book")
    ap.add_argument("--no-clean", action="store_true")
    ap.add_argument("--single-log", action="store_true", help="one batch.log for everything")
    args = ap.parse_args()

    paths_in = [pathlib.Path(b) for b in args.books]
    missing = [p for p in paths_in if not p.exists()]
    if missing:
        raise SystemExit("not found: " + ", ".join(str(m) for m in missing))

    print(f"{len(paths_in)} book(s), {args.jobs} at a time, voice {args.voice} @ {args.speed}")
    for p in paths_in:
        print(f"  - {p.name}")
    print("logs: work/<slug>/batch.log\n")

    # extract sets the active book; a batch should not quietly repoint it at its last file
    try:
        previous_active = paths.active_slug()
    except SystemExit:
        previous_active = None

    started = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(process, p, args): p for p in paths_in}
        for fut in concurrent.futures.as_completed(futures):
            name, status, secs = fut.result()
            results.append((name, status, secs))
            print(f"  [{len(results)}/{len(paths_in)}] {name}: {status}  ({secs/60:.1f} min)")

    if previous_active and (paths.WORK / previous_active).exists():
        paths.set_active(previous_active)

    print(f"\nbatch finished in {(time.time()-started)/60:.1f} min")
    failed = [r for r in results if "failed" in r[1] or "nothing" in r[1]]
    for name, status, _ in failed:
        print(f"  FAILED {name}: {status}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
