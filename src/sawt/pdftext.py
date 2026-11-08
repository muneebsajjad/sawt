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


def _page_number_lines(pages):
    """Edge lines that carry the page number: "1.3. The first program 3", "2 Chapter 1. Data".
    Their text changes with the section, but the number at their start or end goes up by one
    with each page, so the same offset from the page index recurs on most pages."""
    found = []                            # (page, line index, offset)
    for p, lines in enumerate(pages):
        for i in set(range(min(2, len(lines)))) | set(range(max(0, len(lines) - 2), len(lines))):
            for m in (re.match(r'^(\d{1,4})\s', lines[i]), re.search(r'\s(\d{1,4})$', lines[i])):
                if m and len(lines[i]) <= 90:
                    found.append((p, i, int(m[1]) - p))
    offsets = {}
    for p, _, off in found:
        offsets.setdefault(off, set()).add(p)
    good = {off for off, ps in offsets.items() if len(ps) >= max(3, 0.3 * len(pages))}
    return {(p, i) for p, i, off in found if off in good}


def _strip_furniture(pages):
    """Drop page numbers, running headers that carry them, and lines repeated at the top or
    bottom of most pages."""
    numbered = _page_number_lines(pages) if len(pages) >= 6 else set()
    edge = lambda lines: lines[:3] + lines[-3:]
    counts = {}
    for lines in pages:
        for k in {_key(l) for l in edge(lines) if l}:
            counts[k] = counts.get(k, 0) + 1
    repeated = {k for k, n in counts.items() if len(pages) >= 3 and n >= max(3, len(pages) / 2)}
    out = []
    for p, lines in enumerate(pages):
        edges = set(range(min(3, len(lines)))) | set(range(max(0, len(lines) - 3), len(lines)))
        out.append([l for i, l in enumerate(lines)
                    if not ((p, i) in numbered
                            or i in edges and (PAGE_NUM.match(l) or _key(l) in repeated))])
    return out


def _is_heading(line):
    if not line or len(line) > 90 or ENDS_SENTENCE.search(line) or line.endswith(","):
        return False
    if re.search(r'[;{}=]', line):            # "3 lock(&mutex);": a numbered line of code
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
# Notices nobody wants read: where the paper appeared, licences, preprint stamps, author notes.
NOTICE = re.compile(r'^(\d+(st|nd|rd|th)\s+(annual\s+)?(conference|workshop|international)|'
                    r'proceedings of|published (as|in|at)\b|preprint|under review|arxiv:|'
                    r'(provided proper attribution|permission to (make|reproduce))|copyright|©|'
                    r'(work|research) (was )?(done|performed|conducted) (while|during|at)|'
                    r'equal contribution|corresponding author|author contributions|'
                    r'accepted (to|at|for)\b|license[ds]? under|this work is licensed|'
                    r'code (and \S+ )?(is |are )?available)', re.I)
# "Figure 2:", "Table 3.1." label a caption; "Figure 2.1 shows ..." is a sentence of the text
CAPTION = re.compile(r'^(figure|fig\.|table|algorithm|listing)\s*[A-Z]?\d+(\.\d+)*\s*[.:](\s|$)', re.I)
DOT_LEADER = re.compile(r'(\.\s?){5,}')
AFFILIATION = re.compile(r'\b(universit|institut|college|school of|department|dept\.|faculty|'
                         r'laborator|lab\b|centre|center for|academy|research|inc\.|corp|ltd|'
                         r'gmbh|foundation|hospital|google|microsoft|meta|openai|deepmind|'
                         r'anthropic|nvidia|amazon|apple|ibm|baidu|alibaba|tencent)', re.I)
NAME_WORD = re.compile(r"^([A-Z][\w'’.-]*|[A-Z]\.|and|&|de|van|von|der|da|di|le|la|y)[,∗*†‡§¶\d]*$")


def _is_byline(p, loose=True):
    """Authors, affiliations, emails, addresses: the block under a paper's title. loose: also
    affiliations and lines of nothing but names, which a title in title case can look like."""
    if "@" in p or CONTACT.match(p) or NOTICE.match(p) or FOOTNOTE.match(p):
        return True
    if not loose or SECTION_NAMES.match(p) or HEADING_NUM.match(p):
        return False
    if len(p) <= 200 and AFFILIATION.search(p) and not ENDS_SENTENCE.search(p):
        return True
    names = p.replace(",", " ").split()
    return (0 < len(names) <= 30 and not ENDS_SENTENCE.search(p)
            and all(NAME_WORD.match(w) for w in names))


SMALL_WORDS = {"a", "an", "the", "of", "for", "and", "or", "in", "on", "to", "with", "via", "from",
               "by", "at", "as", "towards", "into", "beyond", "without"}


def _unsmallcap(line):
    """Small capitals come out as "L OW-R ANK" and "I NTRODUCTION": rejoin the split words."""
    from wordfreq import zipf_frequency
    def join(m):
        head, rest = m[1], m[2]
        if zipf_frequency((head + rest).lower(), "en") > zipf_frequency(rest.lower(), "en"):
            return head + rest
        return m[0]
    return re.sub(r'\b([A-Z]) ([A-Z]{2,})', join, line)


def _title_of(paras):
    """The first heading-shaped line, with the next line when the title runs onto it
    ("... Transformers for" / "Language Understanding")."""
    for i, q in enumerate(paras):
        if _is_heading(q) and len(q.split()) >= 2 and not _is_byline(q, loose=False):
            nxt = paras[i + 1] if i + 1 < len(paras) else ""
            last = q.split()[-1].lower()
            if nxt and _is_heading(nxt) and (q.endswith("-") or last in SMALL_WORDS):
                q = _join_hyphen(q, nxt) if q.endswith("-") else f"{q} {nxt}"
            return q, i
    return None, -1


def _front_matter(paras):
    """Papers open with names, affiliations and emails. When an Abstract comes early, start
    there; otherwise skip the author block under the title. Returns the title found there."""
    for i, p in enumerate(paras[:60]):
        m = re.search(r'(^|\s)abstract\b[.:—-]?\s*', p, re.I)
        if m and m.start() < 150 and (m.start() == 0 or CONTACT.match(p[:m.start()].strip())
                                     or len(p[:m.start()].split()) <= 4):
            title, _ = _title_of(paras[:i])
            rest = p[m.end():].strip()
            return title, ([rest] if rest else []) + paras[i + 1:]
    # no Abstract: a title, then a run of names, affiliations and emails, then the text
    head = paras[:40]
    title, t = _title_of(head[:8])
    if title is None:
        return None, paras
    j = t + 1
    while j < len(head) and (_is_byline(head[j]) or title.startswith(head[j])
                             or (title.endswith(head[j]) and j == t + 1)):
        j += 1
    if j - t - 1 >= 2 or any("@" in q or AFFILIATION.search(q) for q in head[t + 1:j]):
        return title, paras[:t] + paras[j:]
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
        if CAPTION.match(line) and (not cur or ENDS_SENTENCE.search(cur)):
            # only after a finished sentence: "shown in" / "Table 6. In this table..." is the
            # sentence running on, not a caption
            # a caption starts its own paragraph, and a short one ends there, so the text after
            # it ("Figure 1. Local version control diagram" / "One of the most...") is kept
            flush()
            if len(line) < 0.8 * width:
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


def _is_clutter(p):
    """Anywhere in the text: footnotes, contact lines, notices, figure and table captions, and
    the dot leaders of a table of contents."""
    return bool(FOOTNOTE.match(p) or CONTACT.match(p) or CAPTION.match(p) or DOT_LEADER.search(p)
                or (len(p) < 400 and NOTICE.match(p))
                or (len(p) < 300 and re.match(r'^\d{1,2}[A-Z][a-z]', p))     # "1All code is..."
                or re.match(r'^(table of )?contents$', p, re.I))


def _without_contents(paras):
    """A table of contents: numbered headings ending in a page number ("2 Approach 6"), several
    together. One alone is a real heading ("4.2 Convergence of Algorithm 1")."""
    toc = [bool(HEADING_NUM.match(p) and _is_heading(p) and re.search(r'\s\d{1,3}$', p))
           for p in paras]
    near = lambda i: sum(toc[max(0, i - 2):i + 3]) >= 2
    return [p for i, p in enumerate(paras) if not (toc[i] and near(i))]


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
    paras = [_unsmallcap(p) if _is_heading(p) else p
             for p in _without_references(paragraphs(pages))]
    paras = _without_contents([p for p in paras if not _is_clutter(p)])
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
