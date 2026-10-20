"""Where a book's files live.

Each book gets work/<slug>/, so a second book cannot silently overwrite the first. The most
recently extracted book is the active one; every command falls back to it, and --book overrides.
The chunk cache stays global on purpose: it is keyed by content hash, so two books sharing a
sentence share the audio.
"""
import json
import os
import pathlib
import re


def _root():
    """Where books, output and pronounce.json live.

    A source checkout keeps everything next to the code, as it always has; an installed copy has
    no such place, so it uses ~/Sawt. SAWT_HOME overrides both.
    """
    if os.environ.get("SAWT_HOME"):
        return pathlib.Path(os.environ["SAWT_HOME"]).expanduser()
    checkout = pathlib.Path(__file__).resolve().parents[2]
    if (checkout / "pyproject.toml").exists():
        return checkout
    return pathlib.Path.home() / "Sawt"


ROOT = _root()
WORK = ROOT / "work"
CACHE = WORK / "cache"
ACTIVE = WORK / ".active"


def slugify(text, fallback="book"):
    slug = re.sub(r'[^a-z0-9]+', '-', str(text).lower()).strip('-')[:60]
    return slug or fallback


def set_active(slug):
    WORK.mkdir(parents=True, exist_ok=True)
    ACTIVE.write_text(slug)


def active_slug():
    if ACTIVE.exists():
        slug = ACTIVE.read_text().strip()
        if slug and (WORK / slug).exists():
            return slug
    books = sorted(p.name for p in WORK.iterdir()
                   if p.is_dir() and p.name != "cache" and (p / "chapters.json").exists()) \
        if WORK.exists() else []
    if len(books) == 1:
        return books[0]
    if not books:
        raise SystemExit("no book extracted yet — run: sawt extract books/<file>")
    raise SystemExit("several books present, pass --book <slug>:\n  " + "\n  ".join(books))


def book_dir(slug=None):
    slug = slug or active_slug()
    d = WORK / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def chapters_path(slug=None, override=None):
    return pathlib.Path(override) if override else book_dir(slug) / "chapters.json"


def manifest_path(slug=None, override=None):
    return pathlib.Path(override) if override else book_dir(slug) / "manifest.json"


def wav_path(manifest_path, entry):
    """Resolve a manifest wav entry, tolerating both the relative form and older absolute ones."""
    raw = pathlib.Path(entry["wav"])
    if raw.is_absolute():
        return raw
    here = manifest_path.parent / raw
    if here.exists():
        return here
    return ROOT / raw          # manifests written before paths became book-relative


def list_books():
    if not WORK.exists():
        return []
    out = []
    for d in sorted(WORK.iterdir()):
        cj = d / "chapters.json"
        if not d.is_dir() or d.name == "cache" or not cj.exists():
            continue
        doc = json.loads(cj.read_text())
        out.append({"slug": d.name, "title": doc.get("title", ""),
                    "author": doc.get("author", ""),
                    "chapters": len(doc.get("chapters", [])),
                    "words": sum(c.get("words", 0) for c in doc.get("chapters", [])),
                    "rendered": (d / "manifest.json").exists()})
    return out
