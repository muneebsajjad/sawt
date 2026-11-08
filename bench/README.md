# Extraction benchmark

How well Sawt picks what to read on real pages: how much junk it reads (menus, credits, ads,
sign-up boxes) and how much of the article it misses. Measured in words, per labelled block.

The pages themselves are other people's content, so they stay out of the repository
(`pages/` and `results/` are ignored); the URLs, labels and scripts are here.

```bash
python3 collect_urls.py        # recent posts from feeds.txt -> urls.tsv (papers/books added by hand)
node snapshot.mjs              # pages/<n>.html as Chrome renders them, pages/<n>.pdf
node segment.mjs               # results/<n>.json: the page's text blocks + what Sawt reads
python3 review.py results/0*.json   # suspects to label: junk read, prose missed
python3 score.py               # the scoreboard; `score.py trafilatura` for another extractor
```

`snapshot.mjs` and `segment.mjs` use playwright-core and a Chrome from a local checkout of
[demo-reel](https://github.com/muneebsajjad/demo-reel); change the two import paths to yours.

**Labels.** The truth for a page is what Sawt read when the set was made, corrected in
`labels.json` (`add`: should be read, `drop`: should not, `neutral`: not scored) and by the rules
in `score.py`: photo credits, datelines, "5 min read" and buttons are never content; captions
and code blocks are not scored. Starting from Sawt's own output favours Sawt where nobody
looked, so the review step lists every short block it reads and every sentence it skips.

Pages behind a bot check ("Just a moment…") are left out rather than worked around.
