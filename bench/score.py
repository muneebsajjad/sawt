"""Scoreboard: how much junk an extractor reads and how much content it misses, against labels.

truth = what Sawt read (2026-11-09) + labels.json corrections + rules below, frozen in
truth.json (block numbers per page) so a later extractor is scored against the same key.
  python score.py                 # today's Sawt (results/*.json "sawt")
  python score.py trafilatura     # results/<n>.trafilatura.txt
"""
import json, glob, re, sys
from review import read_set, norm
CREDIT = re.compile(r"^(photograph|photo|image|illustration)s?( by)?:|getty images|courtesy of|"
                    r"/quanta magazine|public domain|cc by|shutterstock|reuters|^ap$|^afp$", re.I)
DATELINE = re.compile(r"^(\d+ (min|minute)s? read|\d+ (hours?|days?|minutes?) ago|"
                      r"(\d{1,2}(st|nd|rd|th)? )?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w* "
                      r"\d{1,2}?(st|nd|rd|th)?,? ?\d{4})$", re.I)
CTA = re.compile(r"^(sign in|sign up|subscribe|follow|share|log ?in|start free trial|get started|"
                 r"read more|\d+ comments?|apply to attend|cancel)$", re.I)
L = json.load(open("labels.json"))

def truth(n, d):
    lab = L.get(n, {})
    T = read_set(d) | set(lab.get("add", []))
    neutral = set(lab.get("neutral", []))
    for b in d["blocks"]:
        t = b["text"].strip()
        if CREDIT.search(t) or DATELINE.match(t) or CTA.match(t) or not b["visible"] and b["i"] in T:
            T.discard(b["i"])
        if b["tag"] in ("pre", "figcaption", "code"):
            neutral.add(b["i"])
    return T - set(lab.get("drop", [])), neutral

FROZEN = json.load(open("truth.json")) if __import__("os").path.exists("truth.json") else {}


def score(pred_text, n, d):
    if n in FROZEN:                       # the answer key, fixed when the labels were made
        T, neutral = set(FROZEN[n]["read"]), set(FROZEN[n]["neutral"])
        assert FROZEN[n]["blocks"] == len(d["blocks"]), f"{n}: page split differently"
    else:
        T, neutral = truth(n, d)
    P = read_set({"blocks": d["blocks"], "sawt": {"text": pred_text}})
    w = {b["i"]: len(norm(b["text"]).split()) for b in d["blocks"]}
    junk = sum(w[i] for i in P - T - neutral)
    miss = sum(w[i] for i in T - P - neutral)
    want = sum(w[i] for i in T - neutral) or 1
    got = sum(w[i] for i in P - neutral) or 1
    return junk, miss, want, got

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "sawt"
    rows, tot = [], [0, 0, 0, 0]
    for f in sorted(glob.glob("results/[0-9][0-9][0-9].json")):
        n = f[8:11]
        if "exclude" in L.get(n, {}) or int(n) >= 85:      # papers are scored on their own
            continue
        d = json.load(open(f))
        if which == "sawt":
            text = (d["sawt"] or {}).get("text", "")
        else:
            try: text = open(f"results/{n}.{which}.txt").read()
            except FileNotFoundError: text = ""
        j, m, want, got = score(text, n, d)
        rows.append((n, j, m, want, got)); tot = [a + b for a, b in zip(tot, (j, m, want, got))]
    bad = sorted(rows, key=lambda r: -(r[1] / r[4] + r[2] / r[3]))[:8]
    print(f"{which}: {len(rows)} pages | junk read {100*tot[0]/tot[3]:.1f}% of what it reads | "
          f"content missed {100*tot[1]/tot[2]:.1f}% of what it should read")
    print("worst:", ", ".join(f"{n} (junk {100*j/g:.0f}%, missed {100*m/w:.0f}%)" for n, j, m, w, g in bad))
