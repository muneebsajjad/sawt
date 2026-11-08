"""pages/<n>.pdf -> results/<n>.json in the same shape as web pages: blocks are the paragraphs
pdftext rebuilds before any filtering, "sawt" is what Sawt reads (the reading copy)."""
import glob, io, json, sys
sys.path.insert(0, "../src")
from pypdf import PdfReader
from sawt import pdftext
for f in sorted(glob.glob("pages/*.pdf")):
    n = f[6:9]
    data = open(f, "rb").read()
    try:
        out = pdftext.read(data, f)
    except pdftext.NoText as e:
        print(n, "no text", e); continue
    r = PdfReader(io.BytesIO(data))
    pages = [[pdftext._norm(l) for l in (p.extract_text() or "").split("\n")] for p in r.pages]
    paras = pdftext.paragraphs(pages)
    blocks = [{"i": i, "tag": "pdf", "text": p, "visible": True, "links": 0, "anc": []}
              for i, p in enumerate(paras)]
    json.dump({"url": f, "blocks": blocks, "sawt": {"text": out["text"], "title": out["title"]},
               "truncated": out["truncated"]}, open(f"results/{n}.json", "w"))
    print(n, len(paras), "paragraphs;", len(out["text"]), "chars read", "(truncated)" if out["truncated"] else "")
