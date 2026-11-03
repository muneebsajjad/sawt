"""A PDF as readable prose for the browser: title plus paragraphs, without page furniture.

PDFs store lines, not paragraphs. This rebuilds paragraphs from the shape of the text (a short
line that ends a sentence ends its paragraph), drops running headers, footers and page numbers,
rejoins words hyphenated across lines, and leaves out what nobody wants read aloud: numeric
citation markers like "[13]" and the reference list at the end.
"""
import io
import re
import statistics
import unicodedata

HEADING_NUM = re.compile(r'^(\d+(\.\d+)*\.?|[IVX]+\.|[A-Z]\.)\s+\S')
PAGE_NUM = re.compile(r'^(page\s+)?\d{1,4}(\s*(/|of)\s*\d{1,4})?$', re.I)
CITATION = re.compile(r'\s?\[\s*\d+(\s*[,–-]\s*\d+)*\s*\]')
ENDS_SENTENCE = re.compile(r'[.?!:]["”’)\]]?$')
REFERENCES = re.compile(r'^((\d+|[IVX]+)\.?\s+)?(references|bibliography|works cited|literature cited)$',
                        re.I)
JUNK_TITLE = re.compile(r'^(untitled|microsoft word|document\d*$)|\.(docx?|pdf|tex|indd)$', re.I)


class NoText(ValueError):
    """The PDF has no text layer (a scan), or is not a PDF."""


def _norm(line):
    line = unicodedata.normalize("NFKC", line).replace("­", "")    # ligatures, soft hyphens
    return re.sub(r'\s+', ' ', line).strip()


def _key(line):
    return re.sub(r'\d+', '#', line.lower())


def _strip_furniture(pages):
    """Drop page numbers, and lines repeated at the top or bottom of most pages."""
    edge = lambda lines: lines[:3] + lines[-3:]
    counts = {}
    for lines in pages:
        for k in {_key(l) for l in edge(lines) if l}:
            counts[k] = counts.get(k, 0) + 1
    repeated = {k for k, n in counts.items() if len(pages) >= 3 and n >= max(3, len(pages) / 2)}
    out = []
    for lines in pages:
        edges = set(range(min(3, len(lines)))) | set(range(max(0, len(lines) - 3), len(lines)))
        out.append([l for i, l in enumerate(lines)
                    if not (i in edges and (PAGE_NUM.match(l) or _key(l) in repeated))])
    return out


def _is_heading(line):
    if not line or len(line) > 90 or ENDS_SENTENCE.search(line) or line.endswith(","):
        return False
    words = line.split()
    if HEADING_NUM.match(line) and len(words) <= 12:
        return True
    letters = [w for w in words if w[0].isalpha()]
    return (len(words) <= 10 and letters
            and (line.isupper() or all(w[0].isupper() for w in letters if len(w) > 3)))


def _is_junk(line):
    """Table cells and equations: mostly digits and symbols."""
    letters = sum(c.isalpha() for c in line)
    return len(line) < 60 and letters < 0.5 * len(line.replace(" ", ""))


def _join_hyphen(cur, line):
    """"transduc-" + "tion" -> "transduction", but "English-" + "to" stays "English-to"."""
    from wordfreq import zipf_frequency
    head = re.search(r'([\w\u00C0-\uFFFF]+)-$', cur)
    tail = re.match(r'[\w\u00C0-\uFFFF]+', line)
    if head and tail and zipf_frequency((head[1] + tail[0]).lower(), "en") > 0:
        return cur[:-1] + line
    return cur + line


FOOTNOTE = re.compile(r'^[∗*†‡§¶]')
CONTACT = re.compile(r'^(\S+@\S+|https?://\S+|www\.\S+)(\s+(\S+@\S+|https?://\S+|www\.\S+))*$')


def _front_matter(paras):
    """Papers open with names, affiliations and emails. When an Abstract comes early, start
    there, and return the title found above it (the first heading-shaped line)."""
    for i, p in enumerate(paras[:60]):
        m = re.search(r'(^|\s)abstract\b[.:—-]?\s*', p, re.I)
        if m and m.start() < 150 and (m.start() == 0 or CONTACT.match(p[:m.start()].strip())
                                     or len(p[:m.start()].split()) <= 4):
            title = next((q for q in paras[:i] if _is_heading(q) and len(q.split()) >= 2), None)
            rest = p[m.end():].strip()
            return title, ([rest] if rest else []) + paras[i + 1:]
    return None, paras


def paragraphs(pages):
    """pages: a list of lists of lines. Returns the paragraphs, in order."""
    pages = _strip_furniture(pages)
    lines = [l for p in pages for l in p]
    long = [len(l) for l in lines if len(l) >= 40]
    width = statistics.median(long) if long else 80
    paras, cur = [], ""

    def flush():
        nonlocal cur
        if cur.strip():
            paras.append(cur.strip())
        cur = ""

    for line in lines:
        if not line or _is_junk(line):
            if not line:
                flush()
            continue
        if _is_heading(line) and len(line) < 0.8 * width:
            flush()
            paras.append(line)
            continue
        if cur.endswith("-") and line[0].islower() and cur[-2:-1].isalpha():
            cur = _join_hyphen(cur, line)
        else:
            cur = f"{cur} {line}" if cur else line
        if ENDS_SENTENCE.search(line) and len(line) < 0.8 * width:
            flush()
    flush()
    return paras


SECTION_NAMES = re.compile(r'^(abstract|introduction|conclusions?|discussion|related work|'
                           r'acknowledge?ments|appendix\b.*|summary|background|methods?|results)$',
                           re.I)


def _is_table(p):
    """Table rows run together (a third or more of the words are numbers), code, equations."""
    words = p.split()
    if sum(c in "{};=<>#·−" for c in p) >= 0.04 * len(p):      # code and equations
        return True
    return len(words) >= 6 and sum(any(c.isdigit() for c in w) for w in words) >= 0.3 * len(words)


def _drop_fragments(paras):
    """Figure labels, table rows and equations come out as short pieces that are not sentences.
    In a paper that numbers its sections, an unnumbered "heading" is one of those too."""
    numbered = sum(bool(HEADING_NUM.match(p)) and _is_heading(p) for p in paras) >= 3
    out = []
    for p in paras:
        if _is_heading(p):
            if numbered and not HEADING_NUM.match(p) and not SECTION_NAMES.match(p):
                continue
            out.append(p)
        elif _is_table(p):
            continue
        elif len(p.split()) >= 8 or (ENDS_SENTENCE.search(p) and not p.endswith("...")
                                     and len(p.split()) >= 3):
            out.append(p)
    return out


def _without_references(paras):
    """Cut the reference list: from a "References" heading in the back half to the next
    section heading that is clearly not a reference (an appendix keeps its text)."""
    for i, p in enumerate(paras):
        if i >= len(paras) / 5 and REFERENCES.match(p):
            rest = paras[i + 1:]
            for j, q in enumerate(rest):
                if re.match(r'^(appendix|[A-Z]\s+\S.*)$', q, re.I) and _is_heading(q) \
                        and not re.search(r'\d{4}', q):
                    return paras[:i] + rest[j:]
            return paras[:i]
    return paras


def read(data, filename="", limit=200_000):
    """PDF bytes -> {"title", "text", "pages", "truncated"}; text is paragraphs separated by
    blank lines, title plus text at most `limit` characters (the reader's limit)."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        reader = PdfReader(io.BytesIO(data))
        raw = [(p.extract_text() or "") for p in reader.pages]
    except (PdfReadError, ValueError, KeyError, TypeError) as e:
        raise NoText("This file could not be opened as a PDF.") from e
    pages = [[_norm(l) for l in t.split("\n")] for t in raw]
    paras = [p for p in _without_references(paragraphs(pages))
             if not FOOTNOTE.match(p) and not CONTACT.match(p)]
    if not paras:
        raise NoText("This PDF has no text to read: it is probably a scanned image.")
    front_title, paras = _front_matter(paras)

    meta = _norm(str((reader.metadata or {}).get("/Title") or ""))
    first = paras[0]
    if meta and not JUNK_TITLE.search(meta) and len(meta) > 3:
        title = meta
    elif front_title:
        title = front_title
    elif len(first) <= 120 and not ENDS_SENTENCE.search(first):
        title = first
    else:
        title = re.sub(r'\.pdf$', '', filename, flags=re.I) or "PDF"
    if first.lower() == title.lower():
        paras = paras[1:]
    paras = [CITATION.sub("", p) for p in _drop_fragments(paras)]
    paras = [p for p in paras if p.strip()]
    if sum(len(p) for p in paras) < 200:
        raise NoText("This PDF has no text to read: it is probably a scanned image.")
    kept, size = [], len(title) + 2
    for p in paras:                                   # the reader reads up to its limit, so
        if size + len(p) + 2 > limit:                 # show exactly what will be read
            break
        kept.append(p)
        size += len(p) + 2
    return {"title": title, "text": "\n\n".join(kept), "pages": len(reader.pages),
            "truncated": len(kept) < len(paras)}
