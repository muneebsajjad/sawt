// Saves each URL in urls.tsv as it renders in Chrome (pages/<n>.html) or as a PDF (pages/<n>.pdf).
// Usage: node bench/snapshot.mjs   (needs playwright-core and a Chrome; see README in this folder)
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
const require = createRequire("/Users/muneeb/Projects/demo-reel/package.json");
const { chromium } = require("playwright-core");
const { chromePath } = await import("/Users/muneeb/Projects/demo-reel/drive/browser.mjs");
const HERE = new URL(".", import.meta.url).pathname;
mkdirSync(HERE + "pages", { recursive: true });
const rows = readFileSync(HERE + "urls.tsv", "utf8").trim().split("\n").map((l) => l.split("\t"));
const b = await chromium.launch({ executablePath: chromePath() });
const ctx = await b.newContext({ viewport: { width: 1280, height: 900 },
  userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36" });
for (const [i, [kind, url]] of rows.entries()) {
  const n = String(i + 1).padStart(3, "0");
  const pdf = kind.endsWith("pdf");
  const out = `${HERE}pages/${n}.${pdf ? "pdf" : "html"}`;
  if (existsSync(out)) continue;
  try {
    if (pdf) {
      const r = await ctx.request.get(url, { timeout: 90000 });
      if (!r.ok()) throw new Error(`HTTP ${r.status()}`);
      writeFileSync(out, await r.body());
    } else {
      const p = await ctx.newPage();
      await p.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
      await p.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
      await p.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 800) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); } scrollTo(0, 0); });
      await p.waitForTimeout(800);
      const html = await p.content();
      writeFileSync(out, `<!-- ${url} -->\n` + html);
      await p.close();
    }
    console.log(n, kind, "ok", url);
  } catch (e) {
    console.log(n, kind, "FAIL", url, e.message.split("\n")[0]);
  }
}
await b.close();
