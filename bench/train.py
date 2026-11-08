"""Train and cross-validate the read/skip classifier on the frozen labels (by page, 5 folds)."""
import json, glob, sys
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import GroupKFold
from features import block_features, page_context
from review import norm
TRUTH = json.load(open("truth.json"))
X, y, g, W, pages = [], [], [], [], {}
for n in sorted(TRUTH):
    d = json.load(open(f"results/{n}.json")); ctx = page_context(d)
    neutral = set(TRUTH[n]["neutral"]); read = set(TRUTH[n]["read"])
    for b in d["blocks"]:
        if b["i"] in neutral:
            continue
        f = block_features(b, ctx)
        X.append(list(f.values())); y.append(1 if b["i"] in read else 0); g.append(n)
        W.append(len(norm(b["text"]).split()))
    names = list(f.keys())
X, y, g, W = np.array(X), np.array(y), np.array(g), np.array(W)
print(f"{len(y)} blocks on {len(set(g))} pages, {y.sum()} to read")

def scoreboard(pred):
    junk = (W * ((pred == 1) & (y == 0))).sum(); miss = (W * ((pred == 0) & (y == 1))).sum()
    return 100 * junk / max((W * (pred == 1)).sum(), 1), 100 * miss / (W * (y == 1)).sum()

base = X[:, names.index("readability")].astype(int)
print("today's Sawt (Readability): junk %.2f%%  missed %.2f%%" % scoreboard(base))
pred = np.zeros_like(y); prob = np.zeros(len(y))
for tr, te in GroupKFold(5).split(X, y, g):
    m = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.1, subsample=0.8,
                                   random_state=0)
    m.fit(X[tr], y[tr], sample_weight=np.sqrt(W[tr] + 1))
    prob[te] = m.predict_proba(X[te])[:, 1]
for th in (0.3, 0.4, 0.5, 0.6):
    p = (prob >= th).astype(int)
    print(f"classifier, threshold {th}: junk %.2f%%  missed %.2f%%" % scoreboard(p))
np.save("results/cv_prob.npy", prob); json.dump({"names": names}, open("results/feature_names.json", "w"))
