"""Find the words that will be mispronounced hundreds of times, before synthesising any of them.

A proper noun in a novel recurs constantly — "Gregor" appears 252 times in Metamorphosis — so a
single wrong pronunciation is not one defect, it is 252. This ranks candidates by frequency and
writes a starter pronounce.json you can edit.
"""
import argparse
import collections
import json
import pathlib

from . import paths
import re

# Sentence-initial capitals are not evidence of a proper noun, so they are excluded.
SENT_START = re.compile(r'(?:^|(?<=[.!?:;"’]\s))\s*([A-Z][a-z]+)')
CAPWORD = re.compile(r'\b([A-Z][A-Za-z\'\-]{1,})\b')
ACRONYM = re.compile(r'\b([A-Z]{2,6})\b')

STOP = {
    "The", "And", "But", "He", "She", "It", "They", "We", "You", "I", "His", "Her", "Their",
    "That", "This", "There", "Then", "When", "What", "Why", "How", "Who", "Which", "If", "As",
    "At", "In", "On", "Of", "To", "For", "With", "From", "By", "So", "No", "Not", "Now", "One",
    "After", "Before", "While", "Although", "Even", "Only", "Just", "Still", "Yet", "Perhaps",
    "Mr", "Mrs", "Ms", "Dr", "St", "Sir", "Madam", "Lord", "Lady",
    "Well", "Yes", "Come", "Oh", "Ah", "Good", "Dear", "Right", "Here", "Have", "Had", "Has",
    "Was", "Were", "Would", "Could", "Should", "Will", "Can", "May", "Must", "Did", "Does",
    "Let", "Look", "Take", "Get", "Go", "Make", "See", "Say", "Know", "Think", "Never",
    "Nothing", "Something", "Anything", "Everything", "Someone", "Anyone", "Everyone", "Noone",
    "Once", "Soon", "Very", "Much", "More", "Most", "Some", "Any", "All", "Both", "Each",
}


def base(word):
    """Collapse possessives and contractions onto their stem: Gregor's -> Gregor, I'm -> I."""
    return re.split(r"['\u2019]", word)[0].replace("-", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--chapters", help="override chapters.json path")
    ap.add_argument("--book", help="book slug (default: most recent)")
    ap.add_argument("-d", "--dict", default="pronounce.json")
    ap.add_argument("-n", "--top", type=int, default=25)
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--write", action="store_true",
                    help="append unlisted names to pronounce.json with placeholder spellings")
    args = ap.parse_args()

    doc = json.loads(paths.chapters_path(args.book, args.chapters).read_text())
    text = "\n".join(c["text"] for c in doc["chapters"])

    starts = collections.Counter(SENT_START.findall(text))
    allcaps = collections.Counter(CAPWORD.findall(text))

    # Possessives and contractions are the same spoken word as their stem, so they are merged
    # onto it — otherwise "Gregor" and "Gregor's" compete as two separate entries.
    merged, mid_counts = collections.Counter(), collections.Counter()
    for word, n in allcaps.items():
        stem = base(word)
        if not stem or len(stem) < 3 or stem in STOP:
            continue
        merged[stem] += n
        mid_counts[stem] += n - starts.get(word, 0)

    names = collections.Counter({w: n for w, n in merged.items()
                                 if mid_counts[w] >= args.min_count})

    acronyms = collections.Counter(
        a for a in ACRONYM.findall(text) if a not in {"I", "A"} and len(a) >= 2)

    existing = {}
    dpath = pathlib.Path(args.dict)
    if not dpath.is_absolute():
        dpath = paths.ROOT / dpath
    if dpath.exists():
        existing = json.loads(dpath.read_text())

    print(f'"{doc["title"]}" — {sum(c["words"] for c in doc["chapters"]):,} words\n')
    print(f"{'count':>6}  {'word':<22} in dict?")
    print(f"{'-'*6}  {'-'*22} --------")
    missing = []
    for word, n in names.most_common(args.top):
        mark = "yes" if word in existing else ""
        if not mark:
            missing.append(word)
        print(f"{n:>6}  {word:<22} {mark}")

    if acronyms:
        print("\nacronyms (spell these out — TTS reads them as words):")
        for a, n in acronyms.most_common(10):
            mark = "yes" if a in existing else ""
            print(f"{n:>6}  {a:<22} {mark}")
            if not mark:
                missing.append(a)

    total_risk = sum(names[w] for w in missing)
    print(f"\n{len(missing)} words not in {args.dict}, "
          f"{total_risk} spoken occurrences riding on them")

    if args.write and missing:
        for w in missing:
            existing.setdefault(w, w)      # placeholder: edit the value to a phonetic spelling
        dpath.write_text(json.dumps(existing, indent=2, sort_keys=True))
        print(f"\nwrote {len(missing)} placeholders to {dpath} — edit the VALUES, e.g.")
        print(f'  "{missing[0]}": "{missing[0].lower()} ..."   <- how it should sound')
        print("then: sawt synth --only ch001 --max-words 300   (only changed chunks regenerate)")
    elif missing:
        print(f"\nadd them with:  sawt names --write")


if __name__ == "__main__":
    main()
