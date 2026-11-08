// pages/<n>.html -> results/<n>.json: blocks (blocks.js) plus what today's extractor reads.
import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from "node:fs";
const require = createRequire("/Users/muneeb/Projects/demo-reel/package.json");
const { chromium } = require("playwright-core");
const { chromePath } = await import("/Users/muneeb/Projects/demo-reel/drive/browser.mjs");
const HERE = new URL(".", import.meta.url).pathname, EXT = HERE + "../extension/";
const BAD = /<title[^>]*>\s*(Just a moment|Human Verification)/i;
mkdirSync(HERE + "results", { recursive: true });
const b = await chromium.launch({ executablePath: chromePath() });
const ctx = await b.newContext({ javaScriptEnabled: false, viewport: { width: 1280, height: 900 } });
const blocksJs = readFileSync(HERE + "blocks.js", "utf8");
const readability = readFileSync(EXT + "vendor/Readability.js", "utf8");
const content = readFileSync(EXT + "content.js", "utf8");
for (const f of readdirSync(HERE + "pages").filter((f) => f.endsWith(".html")).sort()) {
  const html = readFileSync(HERE + "pages/" + f, "utf8");
  if (BAD.test(html)) continue;
  const url = (html.match(/^<!-- (\S+) -->/) || [])[1];
  const p = await ctx.newPage();
  try {
    await p.route("**/*", (r) => ["image", "media", "font"].includes(r.request().resourceType()) ? r.abort() : r.continue());
    await p.setContent(html, { waitUntil: "load", timeout: 30000 }).catch(() => {});
    const blocks = await p.evaluate(blocksJs);
    // extraction with scripts off in the page: run ours through CDP's isolated evaluate
    const sawt = await p.evaluate(`(() => { ${readability}; return (\n${content.trim().replace(/;$/, "")}\n); })()`);
    writeFileSync(HERE + `results/${f.replace(".html", ".json")}`, JSON.stringify({ url, blocks, sawt }));
    console.log(f, blocks.length, "blocks;", sawt?.text?.length, "chars read");
  } catch (e) {
    console.log(f, "FAIL", e.message.split("\n")[0]);
  }
  await p.close();
}
await b.close();
