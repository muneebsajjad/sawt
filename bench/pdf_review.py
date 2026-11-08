import json, glob, re, sys
from review import read_set
SENT = re.compile(r"[.!?:”\"')]\s*$")
for f in sys.argv[1:]:
    d = json.load(open(f)); R = read_set(d); n = f[8:11]
    last = max(R) if R else 0
    junk = [b for b in d["blocks"] if b["i"] in R and (len(b["text"].split()) <= 6 and not SENT.search(b["text"])
            or sum(c.isdigit() for c in b["text"]) > 0.25 * len(b["text"]))]
    miss = [b for b in d["blocks"] if b["i"] not in R and b["i"] < last and len(b["text"].split()) >= 15]
    print(f"## {n} {d['sawt']['title'][:60]}  read={len(R)}/{len(d['blocks'])}")
    for tag, bs in (("READ?", junk), ("MISS?", miss)):
        for b in bs[:18]: print(f"  {tag} {b['i']:>5} {b['text'][:95]!r}")
        if len(bs) > 18: print(f"  {tag} ... {len(bs)-18} more")
