"""results/<n>.trafilatura.txt for each snapshot (run with: uv run --with trafilatura)."""
import glob, re, trafilatura
for f in sorted(glob.glob("pages/*.html")):
    n = f[6:9]
    html = open(f, encoding="utf-8", errors="replace").read()
    url = (re.match(r"<!-- (\S+) -->", html) or [None, None])[1]
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True,
                               favor_precision=False) or ""
    open(f"results/{n}.trafilatura.txt", "w").write(text)
    print(n, len(text))
