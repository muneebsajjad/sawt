"""Pick recent post URLs from the feeds in feeds.txt -> urls.tsv (kind, url)."""
import pathlib, sys, urllib.request, xml.etree.ElementTree as ET
HERE = pathlib.Path(__file__).parent
PER_FEED = 3
out = []
for line in (HERE / "feeds.txt").read_text().splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    kind, feed = line.split()
    try:
        req = urllib.request.Request(feed, headers={"User-Agent": "Mozilla/5.0 (sawt-bench)"})
        root = ET.fromstring(urllib.request.urlopen(req, timeout=20).read())
    except Exception as e:
        print(f"skip {feed}: {e}", file=sys.stderr)
        continue
    links = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "item":
            l = next((c.text for c in el if c.tag.split("}")[-1] == "link" and c.text), None)
            if l: links.append(l.strip())
        elif tag == "entry":
            alt = [c for c in el if c.tag.split("}")[-1] == "link"]
            l = next((c.get("href") for c in alt if c.get("rel") in (None, "alternate")), None)
            if l: links.append(l.strip())
    for l in links[:PER_FEED]:
        out.append((kind, l.split("?source=")[0]))
    print(f"{len(links[:PER_FEED])} from {feed}", file=sys.stderr)
(HERE / "urls.tsv").write_text("".join(f"{k}\t{u}\n" for k, u in out))
print(len(out), "urls")
