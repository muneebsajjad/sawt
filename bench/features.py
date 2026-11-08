"""Per-block features for the read/skip classifier. Mirrored in the extension (classify.js)."""
import re
from review import read_set, norm
STOP = set("the a an and or of to in on for with is are was were be been it this that as at by from "
           "we you they he she i our their its not but can will has have had so if than then there "
           "which who what when how all more one about into also".split())
TAGS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "span", "a", "td", "th", "blockquote",
        "pre", "figcaption", "button", "label", "dd", "dt", "section", "time"]
WORDS = ["nav", "menu", "footer", "header", "aside", "sidebar", "comment", "related", "share",
         "social", "newsletter", "subscribe", "signup", "promo", "sponsor", "advert", "byline",
         "author", "bio", "caption", "credit", "cookie", "consent", "banner", "cta", "breadcrumb",
         "tag", "meta", "date", "toc", "article", "main", "content", "post", "entry", "body", "prose",
         "story", "text", "quote", "table"]
SENT = re.compile(r"[.!?:”\"')]\s*$")
NAMES = FEATURES = None


def block_features(b, page):
    t = b["text"]; ws = norm(t).split(); n = len(ws) or 1
    anc = " ".join(b.get("anc", [])).lower()
    f = {
        "readability": 1.0 if b["i"] in page["R"] else 0.0,
        "prev_readability": 1.0 if b["i"] - 1 in page["R"] else 0.0,
        "next_readability": 1.0 if b["i"] + 1 in page["R"] else 0.0,
        "words": min(len(ws), 400) / 400, "few_words": 1.0 if len(ws) <= 3 else 0.0,
        "sentence_end": 1.0 if SENT.search(t) else 0.0,
        "stopwords": sum(w in STOP for w in ws) / n,
        "digits": sum(c.isdigit() for c in t) / max(len(t), 1),
        "titlecase": sum(w[:1].isupper() for w in t.split()) / max(len(t.split()), 1),
        "links": min(b.get("links", 0) / max(len(t), 1), 1.0),
        "interactive": 1.0 if b.get("interactive") else 0.0,
        "visible": 1.0 if b.get("visible", True) else 0.0,
        "font": (b.get("font", 16) or 16) / page["font"],
        "bold": 1.0 if str(b.get("weight", "400")) in ("600", "700", "800", "900", "bold") else 0.0,
        "x": (b.get("x", 0) - page["x0"]) / page["w"], "width": b.get("w", 0) / page["w"],
        "y": b.get("y", 0) / page["h"], "order": b["i"] / page["n"],
        "depth": len(b.get("anc", [])) / 8,
    }
    for tg in TAGS:
        f["tag_" + tg] = 1.0 if b["tag"] == tg else 0.0
    for w in WORDS:
        f["anc_" + w] = 1.0 if w in anc else 0.0
    return f


def page_context(d, read_text=None):
    R = read_set(d if read_text is None else {"blocks": d["blocks"], "sawt": {"text": read_text}})
    vis = [b for b in d["blocks"] if b.get("visible", True) and b.get("w", 0) > 0]
    big = sorted(vis, key=lambda b: -len(b["text"]))[:20] or d["blocks"]
    fonts = sorted(b.get("font", 16) or 16 for b in big)
    xs = sorted(b.get("x", 0) for b in big)
    return {"R": R, "font": fonts[len(fonts) // 2] or 16, "x0": xs[len(xs) // 2],
            "w": max((b.get("w", 0) for b in d["blocks"]), default=1) or 1,
            "h": max((b.get("y", 0) for b in d["blocks"]), default=1) or 1,
            "n": max(len(d["blocks"]), 1)}
