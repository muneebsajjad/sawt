"""Book file -> chapters.json  (the clean-prose step; everything downstream assumes it worked).

EPUB gives real chapter boundaries from the spine. PDF has none, so headings are guessed and
the result always needs a human look — that is why `inspect` exists.
"""
import argparse
import html
import json
import pathlib
import re

from . import paths

WORDNUM = (r'one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|'
           r'fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty')

# Books mark chapters in several ways and plain text preserves none of the markup, so each
# shape is matched explicitly. A bare "II" on its own line is a chapter heading in most novels.
HEADING_PATTERNS = [
    re.compile(rf'^\s*(chapter|part|book|section|canto|letter)\s+'
               rf'([0-9]+|[ivxlcdm]+|{WORDNUM})\b.*$', re.I),   # Chapter 4 / Part Two
    re.compile(r'^\s*[IVXLCDM]{1,7}\.?\s*$'),                    # bare roman numeral
    re.compile(r'^\s*[0-9]{1,3}\.?\s*$'),                        # bare arabic numeral
    re.compile(r'^\s*[A-Z][A-Z \'\-,.]{3,48}\s*$'),              # SHORT ALL-CAPS TITLE
]


# Title Case headings are common in non-fiction PDFs, where extraction loses the font
# information that made them look like headings. The rule is opt-in because an aggressive
# match splits ordinary prose; constraints keep it to short, unpunctuated, mostly-capitalised
# lines of two or more words.
TITLECASE_RE = re.compile(r'^\s*([A-Z][\w\'\-]*)(\s+[\w\'\-]+){1,9}\s*$')


def is_titlecase_heading(line):
    stripped = line.strip()
    if not (4 < len(stripped) < 60) or stripped[-1] in ".,;:!?":
        return False
    if not TITLECASE_RE.match(stripped):
        return False
    words = stripped.split()
    caps = sum(1 for w in words if w[:1].isupper())
    return caps >= max(2, len(words) - 2)      # allow "of", "and", "the" in lower case


def merge_short(chapters, min_words=120):
    """Fold undersized sections into the previous one.

    Dropping them loses text — a short section is a sectioning mistake, not something the
    author did not write. Only boilerplate is ever discarded.
    """
    out = []
    for ch in chapters:
        if is_boilerplate(ch["text"]):
            continue
        if out and len(ch["text"].split()) < min_words:
            out[-1]["text"] = f'{out[-1]["text"]}\n\n{ch["title"]}\n\n{ch["text"]}'.strip()
        else:
            out.append(ch)
    # a short opening section merges forward instead
    while len(out) > 1 and len(out[0]["text"].split()) < min_words:
        out[1]["text"] = f'{out[0]["text"]}\n\n{out[1]["text"]}'.strip()
        out.pop(0)
    return out


def is_heading(line, titlecase=False):
    if any(p.match(line) for p in HEADING_PATTERNS):
        return True
    return titlecase and is_titlecase_heading(line)

# Page furniture that reads aloud as noise. Lowercase roman numerals are front-matter page
# numbers; UPPERCASE ones are chapter headings, so only the lowercase form is dropped.
# "Page 7" must match whatever its case; the roman-numeral arm stays case-sensitive so that
# UPPERCASE chapter headings are not mistaken for front-matter page numbers.
NOISE_RE = re.compile(r'^\s*(?i:page\s*)?\d{1,4}\s*$|^\s*[ivxlcdm]{1,7}\s*$')


# Project Gutenberg wraps every text in a licence header and footer. Spoken aloud that is
# ~20 minutes of legalese, so it is cut before anything else sees the text.
PG_START = re.compile(r'\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*', re.I | re.S)
PG_END = re.compile(r'\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*', re.I | re.S)


def strip_boilerplate(text):
    m = PG_START.search(text)
    if m:
        text = text[m.end():]
    return PG_END.split(text)[0] if PG_END.search(text) else text


def is_boilerplate(text):
    """True for licence/colophon pages that should never be narrated."""
    probe = text[:2500].lower()
    markers = ("project gutenberg literary archive foundation", "full project gutenberg",
               "redistribution is subject to the trademark license",
               "this ebook is for the use of anyone anywhere", "1.e.1.", "section 1. general terms")
    return sum(m in probe for m in markers) >= 2


def clean(text):
    """Normalise prose for speech. Order matters: de-hyphenate before collapsing whitespace."""
    text = strip_boilerplate(html.unescape(text))
    text = text.replace("­", "")                      # soft hyphens
    text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)     # hyphenation across a line break
    text = re.sub(r'\[\d+\]|\{\d+\}', '', text)            # footnote markers
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("—", " - ").replace("–", "-")
    text = text.replace("…", "...")
    lines = [l for l in text.split("\n") if not NOISE_RE.match(l)]
    text = "\n".join(lines)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _epub_documents(book):
    """Return the book's content documents, in reading order.

    Some EPUBs declare their content with a media type ebooklib does not classify as
    ITEM_DOCUMENT, so the typed query returns almost nothing. When that happens, fall back to
    every .html/.xhtml item, ordered by the spine where one exists.
    """
    import ebooklib

    docs = [i for i in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)]
    if len(docs) > 1:
        return docs

    by_id = {}
    for item in book.get_items():
        name = (item.get_name() or "").lower()
        if name.endswith((".html", ".xhtml", ".htm")) and "nav" not in name and "toc" not in name:
            by_id[item.get_id()] = item

    ordered = []
    for idref, _linear in (getattr(book, "spine", None) or []):
        if idref in by_id:
            ordered.append(by_id.pop(idref))
    # anything not in the spine, in natural (page_2 before page_10) order
    def natural(item):
        parts = re.split(r'(\d+)', item.get_name() or "")
        return [int(p) if p.isdigit() else p for p in parts]

    ordered.extend(sorted(by_id.values(), key=natural))
    return ordered or docs


def from_epub(path):
    from bs4 import BeautifulSoup
    from ebooklib import epub

    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    meta_title = (book.get_metadata("DC", "title") or [("", )])
    meta_author = (book.get_metadata("DC", "creator") or [("", )])
    title = meta_title[0][0] if meta_title and meta_title[0] else ""
    author = meta_author[0][0] if meta_author and meta_author[0] else ""

    chapters = []
    for item in _epub_documents(book):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup(["script", "style", "sup", "table", "nav"]):
            tag.decompose()
        head = soup.find(["h1", "h2", "h3"])
        name = clean(head.get_text(" ")) if head else ""
        body = clean(soup.get_text("\n"))
        if not body:
            continue
        # A document carrying a heading starts a chapter; the page-per-file books that follow
        # it have no headings, so their text accumulates into the chapter they belong to.
        if name or not chapters:
            chapters.append({"title": name or f"Section {len(chapters) + 1}", "text": body})
        else:
            chapters[-1]["text"] = f'{chapters[-1]["text"]}\n\n{body}'

    return title or path.stem, author, merge_short(chapters)


def from_pdf(path, titlecase=False):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    meta = reader.metadata or {}
    pages = [clean(p.extract_text() or "") for p in reader.pages]
    full = "\n\n".join(pages)

    # Split on heading-shaped lines. PDFs rarely mark chapters any other way.
    chapters, cur = [], {"title": "Opening", "lines": []}
    for line in full.split("\n"):
        min_lines = 8 if titlecase else 40
        if is_heading(line, titlecase) and len(cur["lines"]) > min_lines:
            chapters.append(cur)
            cur = {"title": line.strip(), "lines": []}
        else:
            cur["lines"].append(line)
    chapters.append(cur)
    out = merge_short([{"title": c["title"], "text": "\n".join(c["lines"]).strip()}
                       for c in chapters])
    return (meta.get("/Title") or path.stem), (meta.get("/Author") or ""), out


TITLE_RE = re.compile(r'^\s*Title:\s*(.+)$', re.I | re.M)
AUTHOR_RE = re.compile(r'^\s*Author:\s*(.+)$', re.I | re.M)


def from_txt(path, titlecase=False):
    raw = path.read_text(errors="replace")
    head = raw[:4000]                     # metadata block sits above the START marker
    m_title, m_author = TITLE_RE.search(head), AUTHOR_RE.search(head)
    full = clean(raw)
    chapters, cur = [], {"title": "Opening", "lines": []}
    for line in full.split("\n"):
        min_lines = 8 if titlecase else 40
        if is_heading(line, titlecase) and len(cur["lines"]) > min_lines:
            chapters.append(cur)
            cur = {"title": line.strip(), "lines": []}
        else:
            cur["lines"].append(line)
    chapters.append(cur)
    out = [{"title": c["title"], "text": "\n".join(c["lines"]).strip()} for c in chapters]
    title = m_title.group(1).strip() if m_title else path.stem
    author = m_author.group(1).strip() if m_author else ""
    return title, author, merge_short(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("-o", "--out", help="override output path")
    ap.add_argument("--slug", help="folder name for this book (default: from its title)")
    ap.add_argument("--headings", choices=["auto", "titlecase"], default="auto",
                    help="titlecase: also split on Title Case lines (non-fiction PDFs)")
    ap.add_argument("-f", "--force", action="store_true",
                    help="overwrite an existing chapters.json (discards trims and retitles)")
    args = ap.parse_args()

    path = pathlib.Path(args.book)
    ext = path.suffix.lower()
    reader = {".epub": from_epub, ".pdf": from_pdf,
              ".txt": from_txt, ".md": from_txt}.get(ext)
    if reader is None:
        raise SystemExit(
            f"unsupported format: {ext}\n"
            "  supported: .epub (best), .pdf, .txt, .md\n"
            "  for .mobi/.azw3/.docx/.html, convert first:\n"
            "    ebook-convert input.azw3 output.epub      # Calibre\n"
            "    pandoc input.docx -o output.txt")
    title, author, chapters = (from_epub(path) if ext == ".epub"
                               else reader(path, args.headings == "titlecase"))

    if not chapters:
        raise SystemExit(f"no chapters extracted from {path} — is it a scanned PDF (no text layer)?")

    for i, c in enumerate(chapters, 1):
        c["id"] = f"ch{i:03d}"
        c["words"] = len(c["text"].split())

    doc = {"title": title.strip(), "author": author.strip(),
           "source": str(path), "chapters": chapters}
    slug = args.slug or paths.slugify(title or path.stem)
    out = pathlib.Path(args.out) if args.out else paths.book_dir(slug) / "chapters.json"
    if out.exists() and not args.force:
        raise SystemExit(
            f"{out} already exists — re-extracting would discard any trims or retitles.\n"
            f"  keep it:      sawt books --use {slug}\n"
            f"  replace it:   sawt extract {path} --force")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2))
    if not args.out:
        paths.set_active(slug)

    words = sum(c["words"] for c in chapters)
    print(f'"{doc["title"]}" — {doc["author"] or "unknown author"}')
    print(f"{len(chapters)} chapters, {words:,} words")
    print(f"~{words / 152 / 60:.1f}h of audio at 152 wpm, ~{words / 152 / 2.7 / 60:.1f}h to generate")
    print(f"-> {out}   [book: {slug}]\n   (run `sawt inspect` next — extraction is the step that goes wrong)")


if __name__ == "__main__":
    main()
