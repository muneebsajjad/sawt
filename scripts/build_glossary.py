"""Build the offline glossary: short English meanings for hard words, from Wiktionary.

Input is Kaikki.org's English extraction of Wiktionary (wiktextract), one JSON entry per line:
    https://kaikki.org/dictionary/English/kaikki.org-dictionary-English.jsonl.gz
Output is one SQLite file the engine looks words up in:

    words(word, senses)   senses: JSON [[part of speech, meaning, label], ...], best first
    forms(form, word)     inflections pointing at the headword: "heuristics" -> "heuristic"
    meta(key, value)      where the data came from, for the attribution line

Only the first few usable meanings of each word are kept. Obsolete, archaic and spelling-variant
senses are dropped, and a sub-sense keeps its own gloss rather than repeating its parent's.

Wiktionary text is CC BY-SA 4.0, so the file is a separate download with attribution and never
part of the MIT-licensed package.

Usage: python scripts/build_glossary.py kaikki.org-dictionary-English.jsonl.gz [out.sqlite]
"""
import gzip
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_SENSES = 3
MAX_GLOSS = 220             # longer glosses are usually lists of usages, not explanations

# Parts of speech a reader meets as a word in a sentence. Proper names stay: NASA, FAA and
# Kubernetes are exactly what a reader stops on. "character", "symbol", affixes and phrases
# add size without helping.
KEEP_POS = {"noun", "verb", "adj", "adv", "prep", "conj", "intj", "pron", "det", "num",
            "abbrev", "contraction", "name"}
DROP_TAGS = {"obsolete", "archaic", "form-of", "alt-of", "misspelling", "nonstandard",
             "dated", "historical", "rare", "uncommon", "pronunciation-spelling",
             "eye-dialect", "obsolete-form", "archaic-form"}
ABBR_TAGS = {"abbreviation", "initialism", "acronym"}
# Usage notes worth a word on the card: "myopic" means one thing literally, another figuratively.
LABEL_TAGS = ["figuratively", "informal", "slang", "colloquial", "formal", "derogatory",
              "humorous", "literary", "jargon"]
# Inflections worth a pointer back to their headword.
FORM_TAGS = {"plural", "past", "participle", "comparative", "superlative", "third-person"}

POS_SHORT = {"noun": "n.", "verb": "v.", "adj": "adj.", "adv": "adv.", "prep": "prep.",
             "conj": "conj.", "intj": "interj.", "pron": "pron.", "det": "det.", "num": "num.",
             "abbrev": "abbr.", "contraction": "contr.", "name": "name"}

POINTER = re.compile(r"^(alternative|archaic|obsolete|dated|nonstandard|rare)?\s*"
                     r"(form|spelling|plural|past|present|comparative|superlative|"
                     r"misspelling|abbreviation)\b.*\bof\b", re.I)
WORD = re.compile(r"^[A-Za-z][A-Za-z0-9'-]*$")


def senses_of(entry):
    """Usable (pos, gloss, label) for one entry, in Wiktionary's order."""
    out = []
    for s in entry.get("senses", ()):
        glosses = s.get("glosses")
        if not glosses:
            continue
        tags = set(s.get("tags", ()))
        # Wiktionary files an acronym as an alternative form of its expansion, but the
        # expansion is exactly the meaning a reader wants: "Initialism of ...".
        abbr = bool(tags & ABBR_TAGS)
        if tags & (DROP_TAGS - {"alt-of"} if abbr else DROP_TAGS):
            continue
        if s.get("form_of") or (s.get("alt_of") and not abbr):
            continue
        gloss = " ".join(glosses[-1].split())
        if not gloss or len(gloss) > MAX_GLOSS or (POINTER.match(gloss) and not abbr):
            continue
        label = next((t for t in LABEL_TAGS if t in tags), "")
        out.append((POS_SHORT[entry["pos"]], gloss, label))
    return out


def pointers_of(entry):
    """(form, headword) pairs: listed inflections, and entries that only say "plural of X"."""
    word = entry["word"]
    for f in entry.get("forms", ()):
        form, tags = f.get("form", ""), set(f.get("tags", ()))
        if form != word and WORD.match(form) and tags & FORM_TAGS and not tags & DROP_TAGS:
            yield form, word
    for s in entry.get("senses", ()):
        for target in s.get("form_of", ()):
            if WORD.match(target.get("word", "")) and not set(s.get("tags", ())) & {"misspelling"}:
                yield word, target["word"]


def build(src, out):
    words = {}                                       # word -> [(pos, gloss, label), ...]
    forms = {}
    n = 0
    with gzip.open(src, "rt", encoding="utf-8") as fh:
        for line in fh:
            n += 1
            if n % 200_000 == 0:
                print(f"\r  {n:,} entries, {len(words):,} words", end="", file=sys.stderr,
                      flush=True)
            e = json.loads(line)
            if e.get("lang_code") != "en" or e.get("pos") not in KEEP_POS:
                continue
            if not WORD.match(e.get("word", "")):
                continue
            for form, head in pointers_of(e):
                forms.setdefault(form, head)
            got = senses_of(e)
            if got:
                have = words.setdefault(e["word"], [])
                for s in got:
                    if len(have) < MAX_SENSES * 2 and s[1] not in {h[1] for h in have}:
                        have.append(s)
    print(file=sys.stderr)

    # A word with meanings of its own never redirects; a redirect must land somewhere real.
    forms = {f: h for f, h in forms.items() if f not in words and h in words}

    out.unlink(missing_ok=True)
    db = sqlite3.connect(out)
    db.executescript("""
        CREATE TABLE words(word TEXT PRIMARY KEY, senses TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE forms(form TEXT PRIMARY KEY, word TEXT NOT NULL) WITHOUT ROWID;
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    db.executemany("INSERT INTO words VALUES (?, ?)",
                   ((w, json.dumps(pick(s), ensure_ascii=False, separators=(",", ":")))
                    for w, s in sorted(words.items())))
    db.executemany("INSERT INTO forms VALUES (?, ?)", sorted(forms.items()))
    db.executemany("INSERT INTO meta VALUES (?, ?)", [
        ("source", "Wiktionary, via Kaikki.org (wiktextract)"),
        ("license", "CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/"),
        ("input", Path(src).name),
    ])
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(f"{len(words):,} words, {len(forms):,} forms -> {out} "
          f"({out.stat().st_size / 1e6:.1f}MB)", file=sys.stderr)


def pick(senses):
    """The best few meanings: two from the main part of speech, then the next one.

    Wiktionary lists the main part of speech first. "myopic" is mostly met as an adjective, so
    its figurative adjective sense must beat the rare noun ("a short-sighted individual").
    """
    main = [s for s in senses if s[0] == senses[0][0]]
    rest = [s for s in senses if s[0] != senses[0][0]]
    chosen = main[:2] + rest[:1]
    chosen += [s for s in main[2:] + rest[1:]][:MAX_SENSES - len(chosen)]
    return [list(s) for s in chosen[:MAX_SENSES]]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    build(sys.argv[1], Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "dist" / "glossary.sqlite")
