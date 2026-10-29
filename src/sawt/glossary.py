"""Meanings for the hard words in an article, so a reader need not stop and look them up.

Two sources, both on this machine:

- the page itself: an article that writes "maximum allowable operating pressure (MAOP)" has
  defined MAOP better than any dictionary can, and MAOP is in none of them;
- the glossary: short meanings from Wiktionary, built by scripts/build_glossary.py and
  downloaded once, like the voice model. Wiktionary text is CC BY-SA 4.0, which is why it is a
  separate download and not part of the package.

"Hard" is decided by how often a word appears in English (wordfreq's Zipf scale, 7 for "the",
about 2.6 for "myopic"). The engine reports every candidate with its score; the extension holds
the reader's threshold and the words they have marked as known, so changing either is instant.
"""
import hashlib
import json
import lzma
import os
import pathlib
import re
import sqlite3
import sys
import threading
import urllib.request

from wordfreq import zipf_frequency

from . import models

VERSION = "2026.10"
URL = f"https://github.com/muneebsajjad/sawt/releases/download/glossary-{VERSION}/glossary.sqlite.xz"
SHA256 = "e654309b38dfbd28746ae2d0b03159fa76610b775f48d21da8b8aef04f117de8"   # of the .xz

# Candidates at or below this score go to the extension, which applies the reader's own cutoff.
MAX_SCORE = 3.5
# A capitalised word mid-sentence is usually a name. Everyday ones score high ("Paris" 4.8,
# "Smith" 4.9); the ones a reader stops on score low ("Kubernetes" 2.3, "Postgres" 2.0).
MAX_NAME_SCORE = 2.5
# Acronyms are judged a point more leniently: "LLM" is common in tech writing and still opaque.
ACRONYM_BONUS = 1.0

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[’'-][A-Za-z0-9]+)*")
ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9]{1,7}s?$")
POSSESSIVE_RE = re.compile(r"[’']s$")
# "long form (ABBR)": the defining pattern Schwartz & Hearst (2003) look for.
DEFINED_RE = re.compile(r"\(\s*([A-Z][A-Za-z0-9]{1,9})s?\s*\)")


def path():
    if os.environ.get("SAWT_GLOSSARY"):
        return pathlib.Path(os.environ["SAWT_GLOSSARY"]).expanduser()
    return models.model_dir() / f"glossary-{VERSION}.sqlite"


def ensure():
    """The glossary's path, downloading and unpacking it the first time."""
    dest = path()
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading the glossary to {dest.parent} (one time, ~15MB)…", file=sys.stderr,
          flush=True)
    xz = dest.with_suffix(".sqlite.xz.part")
    h = hashlib.sha256()
    with urllib.request.urlopen(URL) as res, open(xz, "wb") as fh:
        while block := res.read(1 << 20):
            h.update(block)
            fh.write(block)
    if h.hexdigest() != SHA256:
        xz.unlink()
        raise RuntimeError("glossary: checksum mismatch after download")
    tmp = dest.with_suffix(".part")
    with lzma.open(xz) as src, open(tmp, "wb") as out:
        while block := src.read(1 << 20):
            out.write(block)
    xz.unlink()
    tmp.replace(dest)
    return dest


class Glossary:
    def __init__(self, db_path):
        # read-only, and shared by the server's request threads
        self.db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
        self.lock = threading.Lock()

    def lookup(self, word):
        """[[part of speech, meaning, label], ...] for a word or its inflection, or None."""
        with self.lock:
            for w in dict.fromkeys((word, word.lower())):
                row = self.db.execute("SELECT senses FROM words WHERE word = ?", (w,)).fetchone()
                if row is None:
                    head = self.db.execute("SELECT word FROM forms WHERE form = ?",
                                           (w,)).fetchone()
                    if head:
                        row = self.db.execute("SELECT senses FROM words WHERE word = ?",
                                              head).fetchone()
                if row:
                    return json.loads(row[0])
        return None


def load_in_background(engine):
    """Fetch and open the glossary without delaying the first article."""
    def run():
        try:
            engine.glossary = Glossary(ensure())
            print("glossary ready", flush=True)
        except Exception as e:                       # reading works fine without it
            print(f"glossary unavailable: {e}", flush=True)
    threading.Thread(target=run, daemon=True).start()


def defined_on_page(text):
    """{ABBR: long form} for every acronym the text spells out as "long form (ABBR)"."""
    found = {}
    for m in DEFINED_RE.finditer(text):
        abbr = m.group(1)
        if abbr in found or sum(c.isupper() for c in abbr) < 2:
            continue
        before = text[max(0, m.start() - 200):m.start()].split()
        window = before[-min(len(abbr) + 5, len(abbr) * 2):]
        long_form = best_long_form(abbr, " ".join(window))
        if long_form:
            found[abbr] = long_form
    return found


def best_long_form(abbr, candidate):
    """Schwartz & Hearst: the shortest tail of `candidate` whose letters spell `abbr` in order,
    with the abbreviation's first letter starting a word."""
    s, l = len(abbr) - 1, len(candidate) - 1
    while s >= 0:
        c = abbr[s].lower()
        if not c.isalnum():
            s -= 1
            continue
        while l >= 0 and (candidate[l].lower() != c
                          or (s == 0 and l > 0 and candidate[l - 1].isalnum())):
            l -= 1
        if l < 0:
            return None
        l -= 1
        s -= 1
    start = candidate.rfind(" ", 0, l + 1) + 1
    long_form = candidate[start:].strip(" ,;:-")
    # the expansion must be longer than the acronym and more than one word
    if len(long_form) <= len(abbr) or " " not in long_form:
        return None
    return long_form


def hard_words(sentences, glossary, page_text=""):
    """Each hard word's first appearance in the article.

    [{"sentence": i, "word": w, "score": zipf, "senses": [...], "source": "page"|"glossary"}]
    """
    on_page = defined_on_page(page_text) if page_text else {}
    explained = set()      # keys already given a card: "Myopic" and "myopic" get one between them
    rejected = set()       # (word, first) already judged not hard, so a long article is cheap
    out = []
    for i, sentence in enumerate(sentences):
        for k, m in enumerate(TOKEN_RE.finditer(sentence)):
            word = POSSESSIVE_RE.sub("", m.group())
            key = word if ACRONYM_RE.match(word) else word.lower()
            first = k == 0
            if key in explained or (word, first) in rejected:
                continue
            got = judge(word, first=first, glossary=glossary, on_page=on_page)
            if got:
                explained.add(key)
                out.append({"sentence": i, "word": word, **got})
            else:
                rejected.add((word, first))
    return out


def judge(word, first, glossary, on_page):
    """Score and meanings if `word` is worth explaining, else None."""
    acronym = bool(ACRONYM_RE.match(word))
    if acronym:
        bare = word[:-1] if word.endswith("s") and word[:-1] in on_page else word
        if bare in on_page:
            return {"score": round(zipf_frequency(bare, "en"), 2), "source": "page",
                    "senses": [["abbr.", on_page[bare], ""]]}
        limit = MAX_SCORE + ACRONYM_BONUS
    elif len(word) < 4:
        return None
    elif word[0].isupper() and not first:
        limit = MAX_NAME_SCORE                       # most likely a name
    else:
        limit = MAX_SCORE
    score = zipf_frequency(word, "en")
    if score > limit or glossary is None:
        return None
    senses = glossary.lookup(word)
    if not senses and acronym and word.endswith("s"):
        senses = glossary.lookup(word[:-1])           # "LLMs"
    if not senses:
        return None
    return {"score": round(score, 2), "source": "glossary", "senses": senses}
