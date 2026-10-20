"""List extracted books and switch which one the other commands act on by default."""
import argparse

from . import paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--use", help="make this slug the active book")
    args = ap.parse_args()

    if args.use:
        if not (paths.WORK / args.use / "chapters.json").exists():
            raise SystemExit(f"no such book: {args.use}")
        paths.set_active(args.use)
        print(f"active book: {args.use}")
        return

    books = paths.list_books()
    if not books:
        print("no books yet — sawt extract books/<file>")
        return
    try:
        active = paths.active_slug()
    except SystemExit:
        active = None

    for b in books:
        mark = "*" if b["slug"] == active else " "
        state = "rendered" if b["rendered"] else "not synthesised"
        print(f'{mark} {b["slug"]:<28} {b["chapters"]:>3} ch  {b["words"]:>7,} w  {state}')
        print(f'    "{b["title"]}" — {b["author"] or "unknown"}')
    print("\n* = active. switch with: sawt books --use <slug>")


if __name__ == "__main__":
    main()
