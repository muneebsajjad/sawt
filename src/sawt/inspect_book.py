"""Eyeball the extraction before spending hours of CPU on it.

Prints the chapter table plus the head and tail of each chapter's text, which is where
extraction damage shows: a title page welded onto chapter one, a running header repeated
every page, a table of contents parsed as prose.
"""
import argparse
import json
import pathlib

from . import paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--chapters", help="override chapters.json path")
    ap.add_argument("--book", help="book slug (default: most recent)")
    ap.add_argument("-n", "--chars", type=int, default=160, help="head/tail characters to show")
    ap.add_argument("--only", help="inspect one chapter id, e.g. ch003")
    args = ap.parse_args()

    doc = json.loads(paths.chapters_path(args.book, args.chapters).read_text())
    chapters = doc["chapters"]
    if args.only:
        chapters = [c for c in chapters if c["id"] == args.only]

    print(f'"{doc["title"]}" — {doc["author"] or "unknown"}')
    print(f'{len(doc["chapters"])} chapters, {sum(c["words"] for c in doc["chapters"]):,} words\n')

    for c in chapters:
        mins = c["words"] / 152
        print(f'{c["id"]}  {c["words"]:>6,} words  {mins:>5.1f} min  {c["title"][:60]}')
        head = c["text"][:args.chars].replace("\n", " ⏎ ")
        tail = c["text"][-args.chars:].replace("\n", " ⏎ ")
        print(f'      HEAD  {head}')
        print(f'      TAIL  {tail}\n')

    words = [c["words"] for c in doc["chapters"]]
    if words:
        avg = sum(words) / len(words)
        odd = [c for c in doc["chapters"] if c["words"] < avg * 0.25 or c["words"] > avg * 3]
        if odd:
            print("outlier chapters (very short or very long — check these first):")
            for c in odd:
                print(f'  {c["id"]}  {c["words"]:,} words  {c["title"][:50]}')


if __name__ == "__main__":
    main()
