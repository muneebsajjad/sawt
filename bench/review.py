"""Suspects per page, for labelling: blocks Sawt reads that look like junk, and blocks it skips
that look like prose. Prints a compact listing; labels go in labels.json."""
import json, glob, re, sys
def norm(s): return re.sub(r"\W+", " ", s).lower().strip()
SENT = re.compile(r"[.!?:”\"')]\s*$")
def read_set(d, share=0.7):
    """Blocks most of whose words line up, in order, with what the extractor read: a word-level
    diff of the page's blocks against the read text, so a stray "Payments" never counts."""
    from difflib import SequenceMatcher
    S = norm((d["sawt"] or {}).get("text", "")).split()
    words, owner = [], []
    for b in d["blocks"]:
        for w in norm(b["text"]).split():
            words.append(w); owner.append(b["i"])
    hit = {}
    for m in SequenceMatcher(None, words, S, autojunk=False).get_matching_blocks():
        for k in range(m.a, m.a + m.size):
            hit[owner[k]] = hit.get(owner[k], 0) + 1
    total = {}
    for o in owner:
        total[o] = total.get(o, 0) + 1
    return {i for i, n in hit.items() if n >= share * total[i]}


if __name__ == "__main__":
    pages = sys.argv[1:] or sorted(glob.glob("results/*.json"))
    for f in pages:
        d = json.load(open(f)); R = read_set(d); n = f[8:11]
        junk = [b for b in d["blocks"] if b["i"] in R and (len(b["text"].split()) <= 4 and not SENT.search(b["text"]))]
        miss = [b for b in d["blocks"] if b["i"] not in R and b["visible"] and len(b["text"].split()) >= 15
                and SENT.search(b["text"]) and b["links"] < 0.5 * len(b["text"])]
        print(f"## {n} {d['url']}  read={len(R)}/{len(d['blocks'])}")
        for tag, bs in (("READ?", junk), ("MISS?", miss)):
            for b in bs[:25]:
                print(f"  {tag} {b['i']:>5} {b['tag']:<6} {b['text'][:90]!r}")
            if len(bs) > 25: print(f"  {tag} ... {len(bs)-25} more")
