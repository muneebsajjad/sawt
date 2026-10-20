"""Drop or rename chapters in chapters.json before synthesis.

Extraction gets front matter, dedications and licence pages wrong in ways no heuristic fixes
reliably — so inspect, then trim by hand. Ids are renumbered; the original is kept as a .bak.
"""
import argparse
import json
import pathlib

from . import paths
import shutil


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--chapters", help="override chapters.json path")
    ap.add_argument("--book", help="book slug (default: most recent)")
    ap.add_argument("--drop", default="", help="comma-separated ids, e.g. ch001,ch005")
    ap.add_argument("--retitle", action="append", default=[],
                    help='ch002="Part One"  (repeatable)')
    ap.add_argument("--renumber", action="store_true",
                    help="renumber remaining chapters to ch001..chNNN")
    ap.add_argument("--start-at", help="cut everything before this text (front matter, OCR notices)")
    ap.add_argument("--end-at", help="cut everything from this text onward (indexes, appendices)")
    ap.add_argument("--in", dest="in_chapter", default="ch001",
                    help="which chapter --start-at/--end-at apply to")
    args = ap.parse_args()

    path = paths.chapters_path(args.book, args.chapters)
    doc = json.loads(path.read_text())
    shutil.copy(path, path.with_suffix(".json.bak"))

    drop = {d.strip() for d in args.drop.split(",") if d.strip()}
    kept = [c for c in doc["chapters"] if c["id"] not in drop]
    for spec in args.retitle:
        cid, _, title = spec.partition("=")
        for c in kept:
            if c["id"] == cid.strip():
                c["title"] = title.strip().strip('"')

    # Scanned books weld front matter onto the first chapter, so the cut is by content, not index.
    for c in kept:
        if c["id"] != args.in_chapter:
            continue
        if args.start_at:
            i = c["text"].find(args.start_at)
            if i < 0:
                raise SystemExit(f'--start-at text not found in {c["id"]}')
            c["text"] = c["text"][i:].strip()
        if args.end_at:
            j = c["text"].find(args.end_at)
            if j < 0:
                raise SystemExit(f'--end-at text not found in {c["id"]}')
            c["text"] = c["text"][:j].strip()
        c["words"] = len(c["text"].split())

    if args.renumber:
        for i, c in enumerate(kept, 1):
            c["id"] = f"ch{i:03d}"

    doc["chapters"] = kept
    path.write_text(json.dumps(doc, indent=2))
    words = sum(c["words"] for c in kept)
    print(f'dropped {len(drop)}, kept {len(kept)} chapters, {words:,} words '
          f'(~{words/152/60:.1f}h audio)')
    for c in kept:
        print(f'  {c["id"]}  {c["words"]:>6,} words  {c["title"][:50]}')
    print(f"backup: {path.with_suffix('.json.bak')}")


if __name__ == "__main__":
    main()
