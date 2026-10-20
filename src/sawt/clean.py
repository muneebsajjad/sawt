"""Repair scanned-book text: drop citation debris, fix OCR letter confusions.

Scanned editions carry two kinds of damage that matter more than they look:

1. **Citation debris.** The scan's reading order interleaves endnotes into the prose, so a
   chapter contains "Twitter, May 15, 2018, https://twitter.com/naval/status/996460948029362176".
   Narrated, that is a minute of spoken punctuation in the middle of a paragraph. Worse than
   any typo, and purely mechanical to remove.

2. **Letter confusion.** OCR reads "you'll" as "yov'll", "I'm" as "t'm". A correction is only
   accepted when the original is not an English word and the candidate is a common one, so
   proper nouns and coinages are never "corrected" into something else.

Default is a dry run: it reports, it does not write. Pass --apply to commit.
"""
import argparse
import collections
import json
import re
import shutil

from wordfreq import zipf_frequency

from . import paths

# A sentence carrying any of these is reference apparatus, not prose.
CITATION_MARKERS = re.compile(
    r'https?://|www\.|doi:|doi\.org|isbn|\.pdf\b|\.html?\b|retrieved from|'
    r'accessed (on )?\w+ \d|\bvol\.\s*\d+|\bno\.\s*\d+,|\bpp?\.\s*\d+[-–]\d+|'
    r'\b[a-z0-9-]+\.(com|org|net|edu|gov|io|co\.uk)\b',
    re.I)

# Shapes that cannot occur in English, so a fix needs no frequency evidence. OCR reads a
# capital I with a serif as T, which the conservative proper-noun guard would otherwise skip.
CURLY = "\u2019"
LITERAL_FIXES = [
    (re.compile(r"\bT'(m|ve|ll|d)\b"), "I'" + r"\1"),
    (re.compile("\\bT" + CURLY + r"(m|ve|ll|d)\b"), "I" + CURLY + r"\1"),
    (re.compile(r"\bl'(m|ve|ll|d)\b"), "I'" + r"\1"),
]

# Glyph pairs OCR routinely swaps. Digits only ever map TO letters: a first pass that
# "corrected" battleship's into battleship'5 showed what happens when that runs backwards.
CONFUSIONS = [
    ("rn", "m"), ("cl", "d"), ("vv", "w"), ("ii", "n"), ("li", "h"),
    ("v", "u"), ("v", "y"), ("c", "e"), ("i", "l"), ("l", "t"), ("t", "f"),
    ("h", "b"), ("o", "a"), ("n", "h"), ("u", "a"), ("j", "i"), ("a", "o"),
]
DIGIT_FIXES = [("0", "o"), ("1", "l"), ("5", "s"), ("8", "b"), ("3", "e")]

GOOD = 3.0          # zipf: a word an ordinary reader uses, not merely one that exists
POSSESSIVE = re.compile(r"['\u2019]s$")
SENT_SPLIT = re.compile(r'(?<=[.!?]) +')


def is_word(token):
    return zipf_frequency(token.lower(), "en") > 0


def candidates(word):
    """Single- and double-substitution variants of a word, from the confusion table."""
    seen = {word}
    out = []
    pairs = [(a, b) for a, b in CONFUSIONS] + [(b, a) for a, b in CONFUSIONS]
    pairs += DIGIT_FIXES                       # digit -> letter only, never the reverse
    for src, dst in pairs:
        for src, dst in ((src, dst),):
            if src not in word.lower():
                continue
            # replace each occurrence individually, then all at once
            low = word.lower()
            positions = [i for i in range(len(low)) if low.startswith(src, i)]
            variants = [word[:i] + dst + word[i + len(src):] for i in positions]
            variants.append(re.sub(re.escape(src), dst, word, flags=re.I))
            for v in variants:
                if v not in seen:
                    seen.add(v)
                    out.append(v)
    return out


def repair_word(word, suspicious=None):
    """Best correction for a non-word, or None.

    Deliberately conservative. A capitalised word is left alone and merely reported: most are
    names the OCR read correctly, and "Nurco" -> "Narco" or "Aphagia" -> "Aphasia" silently
    rewrites the author's meaning. Narrating one odd name is a smaller sin than inventing text.
    """
    core = word.strip("'\u2019\"")
    suffix = ""
    m = POSSESSIVE.search(core)
    if m:                                   # battleship's -> check "battleship"
        suffix, core = core[m.start():], core[:m.start()]
    if len(core) < 3 or is_word(core):
        return None
    if core[0].isupper():                   # proper noun, or sentence start — do not touch
        if suspicious is not None:
            suspicious[core] += 1
        return None

    best, best_score = None, GOOD
    for cand in candidates(core):
        if any(ch.isdigit() for ch in cand):
            continue
        score = zipf_frequency(cand.lower(), "en")
        if score > best_score:
            best, best_score = cand, score
    if best is None:
        if suspicious is not None:
            suspicious[core] += 1
        return None
    return word.replace(core + suffix, best + suffix)


def clean_chapter(text, drop_citations=True, fix_ocr=True, log=None):
    stats = collections.Counter()
    out_paras = []
    for para in re.split(r'\n\s*\n', text):
        sents = SENT_SPLIT.split(" ".join(para.split()))
        kept = []
        for s in sents:
            if drop_citations and CITATION_MARKERS.search(s):
                stats["citation_sentences"] += 1
                stats["citation_words"] += len(s.split())
                if log is not None and len(log["citations"]) < 6:
                    log["citations"].append(s[:120])
                continue
            kept.append(s)
        if kept:
            out_paras.append(" ".join(kept))
    text = "\n\n".join(out_paras)

    if fix_ocr:
        for pattern, repl in LITERAL_FIXES:
            text, n = pattern.subn(repl, text)
            if n:
                stats["ocr_fixed"] += n
                if log is not None:
                    log["fixes"][f"{pattern.pattern} -> {repl}"] += n

        def sub(m):
            word = m.group(0)
            fixed = repair_word(word, log["suspicious"] if log is not None else None)
            if fixed and fixed != word:
                stats["ocr_fixed"] += 1
                if log is not None:
                    log["fixes"][f"{word} -> {fixed}"] += 1
                return fixed
            return word

        text = re.sub(r"[A-Za-z][A-Za-z'’\-]{2,}", sub, text)
    return text, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--chapters", help="override chapters.json path")
    ap.add_argument("--book", help="book slug (default: most recent)")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--keep-citations", action="store_true")
    ap.add_argument("--no-ocr", action="store_true")
    args = ap.parse_args()

    path = paths.chapters_path(args.book, args.chapters)
    doc = json.loads(path.read_text())

    log = {"citations": [], "fixes": collections.Counter(),
           "suspicious": collections.Counter()}
    total = collections.Counter()
    before = sum(c["words"] for c in doc["chapters"])

    for ch in doc["chapters"]:
        ch["text"], stats = clean_chapter(
            ch["text"], not args.keep_citations, not args.no_ocr, log)
        ch["words"] = len(ch["text"].split())
        total.update(stats)

    after = sum(c["words"] for c in doc["chapters"])

    print(f"citation sentences removed : {total['citation_sentences']:,} "
          f"({total['citation_words']:,} words)")
    if log["citations"]:
        for s in log["citations"]:
            print(f"    - {s}")
    print(f"\nOCR words corrected        : {total['ocr_fixed']:,}")
    for fix, n in log["fixes"].most_common(15):
        print(f"    {n:>3}x  {fix}")

    sus = [(w, n) for w, n in log["suspicious"].most_common(12)]
    if sus:
        print(f"\nleft alone ({len(log['suspicious'])} distinct) — names, or no confident fix:")
        print("   ", ", ".join(f"{w}({n})" for w, n in sus))
        print("    fix any real errors by hand in chapters.json, or let them ride")

    saved = (before - after) / 152 / 60
    print(f"\nwords {before:,} -> {after:,}   ({saved:.1f}h of narration removed)")

    if args.apply:
        shutil.copy(path, path.with_suffix(".json.bak"))
        path.write_text(json.dumps(doc, indent=2))
        print(f"\nwritten. backup at {path.with_suffix('.json.bak')}")
        print("note: changed text invalidates those chunks — re-run synth")
    else:
        print("\ndry run — nothing written. re-run with --apply")


if __name__ == "__main__":
    main()
