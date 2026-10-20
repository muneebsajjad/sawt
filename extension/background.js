// Owns the reading state. The offscreen document only plays what it is told; the popup only
// renders chrome.storage.session.player and sends commands here.
const SERVER = "http://127.0.0.1:7865";
const DEFAULTS = { voice: "af_bella", speed: 0.85 };
const NOT_RUNNING = "The voice engine is not running. Start it with: sawt serve";
const HIGHLIGHT_CSS = "::highlight(sawt-reading) { background-color: #ffe58a; color: #1a1a1a; }";
const POS = "pos:";            // chrome.storage.local key prefix: last sentence read, per page
const POS_KEEP = 300;          // pages remembered; oldest are dropped

async function api(path, body) {
  let res;
  try {
    res = await fetch(SERVER + path, {
      method: body ? "POST" : "GET",
      headers: { "X-Sawt": "1", "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error(NOT_RUNNING);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `server returned ${res.status}`);
  return data;
}

async function getState() {
  return (await chrome.storage.session.get("player")).player || { status: "idle" };
}

async function setState(patch) {
  const player = { ...(await getState()), ...patch };
  await chrome.storage.session.set({ player });
  return player;
}

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(["voice", "speed"])) };
}

// Chrome closes an AUDIO_PLAYBACK offscreen document after ~30s of silence, so a long pause
// loses the player. Every command goes through here, and a fresh document is reloaded from state.
let creating = null;
async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) return false;
  creating ??= chrome.offscreen.createDocument({
    url: "offscreen.html",
    reasons: ["AUDIO_PLAYBACK"],
    justification: "Play the narrated article",
  }).finally(() => { creating = null; });
  await creating;
  return true;
}

async function toPlayer(msg) {
  const fresh = await ensureOffscreen();
  if (fresh && msg.cmd === "stop") return;
  if (fresh && msg.cmd !== "load") {
    const s = await getState();
    if (!s.chunks) return;
    await chrome.runtime.sendMessage({ to: "offscreen", cmd: "load", chunks: s.chunks,
                                       index: s.index || 0, play: msg.cmd !== "pause" });
    if (msg.cmd === "resume") return;
  }
  return chrome.runtime.sendMessage({ to: "offscreen", ...msg });
}

async function extract(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ["vendor/Readability.js"] });
  const [{ result }] = await chrome.scripting.executeScript({ target: { tabId },
                                                              files: ["content.js"] });
  return result;
}

function toPage(tabId, msg) {
  return chrome.tabs.sendMessage(tabId, { to: "page", ...msg }).catch(() => {});
}

async function injectHighlighter(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ["highlight.js"] });
  await chrome.scripting.insertCSS({ target: { tabId }, css: HIGHLIGHT_CSS });
}

// The same article reached from a newsletter link and from the site should share a position,
// so tracking parameters and the fragment are not part of a page's identity.
function pageKey(url) {
  try {
    const u = new URL(url);
    u.hash = "";
    for (const k of [...u.searchParams.keys()]) {
      if (/^(utm_|fbclid$|gclid$|mc_|ref$)/.test(k)) u.searchParams.delete(k);
    }
    return u.href;
  } catch {
    return null;
  }
}

// Resume where the saved sentence is now, not blindly at the saved index: an article edited
// since last time shifts every index after the edit.
function resumeAt(chunks, sentences, saved) {
  let i = chunks[saved.index] && sentences[chunks[saved.index].sentence] === saved.sentence
    ? saved.index
    : chunks.findIndex((c) => sentences[c.sentence] === saved.sentence);
  if (i < 0) return 0;
  const first = chunks.findIndex((c) => c.sentence === chunks[i].sentence);
  return first;                               // the start of that sentence, not mid-way
}

async function savePosition(s, index) {
  const c = s.chunks?.[index];
  if (!s.url || !c) return;
  await chrome.storage.local.set({ [POS + s.url]: {
    index, sentence: s.sentences[c.sentence], total: s.chunks.length, title: s.title,
    at: Date.now() } });
}

async function prunePositions() {
  const all = await chrome.storage.local.get(null);
  const old = Object.entries(all).filter(([k]) => k.startsWith(POS))
    .sort((a, b) => b[1].at - a[1].at).slice(POS_KEEP).map(([k]) => k);
  if (old.length) await chrome.storage.local.remove(old);
}

async function readTab(tab, selectionText) {
  await setState({ status: "loading", error: null, title: tab.title, tabId: tab.id,
                   chunks: null, index: 0, resumedFrom: null });
  try {
    let page;
    if (selectionText) {
      page = { title: "", text: selectionText, source: "selection" };
    } else {
      page = await extract(tab.id);
    }
    if (!page || !page.text || page.text.trim().length < 20) {
      throw new Error("No readable text found on this page. Select some text and try again.");
    }
    await injectHighlighter(tab.id).catch(() => {});   // reading works without it
    // a selection is a fragment, not the article, so it has no place to resume from
    const url = page.source === "selection" ? null : pageKey(tab.url);
    const saved = url ? (await chrome.storage.local.get(POS + url))[POS + url] : null;
    const text = page.title ? `${page.title}\n\n${page.text}` : page.text;
    await start({ text, title: page.title || tab.title, source: page.source, tabId: tab.id,
                  url, index: saved?.index || 0, saved });
    prunePositions();
  } catch (e) {
    await setState({ status: "error", error: e.message });
  }
}

// `saved` is a remembered position to validate; without it `index` is trusted as-is (a voice or
// speed change restarting from the current sentence).
async function start({ text, title, source, tabId, url, index, saved }) {
  const { voice, speed } = await settings();
  const { chunks, sentences } = await api("/read", { text, voice, speed, start: index });
  const patch = {};
  if (saved) {
    index = resumeAt(chunks, sentences, saved);
    patch.resumedFrom = index > 0 ? index : null;
  }
  await setState({ status: "playing", error: null, text, title, source, chunks, sentences,
                   index, voice, speed, tabId, url, ...patch });
  toPage(tabId, { cmd: "prepare", sentences }).then(() =>
    toPage(tabId, { cmd: "show", sentence: chunks[index]?.sentence }));
  await toPlayer({ cmd: "load", chunks, index, play: true });
}

async function stop() {
  const s = await getState();
  if (s.tabId) toPage(s.tabId, { cmd: "clear" });
  await toPlayer({ cmd: "stop" }).catch(() => {});
  await api("/stop", {}).catch(() => {});
  await setState({ status: "idle", chunks: null, sentences: null, text: null, index: 0,
                   error: null, resumedFrom: null });
}

async function command(msg) {
  const s = await getState();
  switch (msg.cmd) {
    case "read": {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      return readTab(tab);
    }
    case "toggle":
      if (s.status === "playing") return command({ cmd: "pause" });
      if (s.status === "paused") return command({ cmd: "resume" });
      return command({ cmd: "read" });
    case "pause":
      await setState({ status: "paused" });
      return toPlayer({ cmd: "pause" });
    case "resume":
      await setState({ status: "playing" });
      return toPlayer({ cmd: "resume" });
    case "next":
    case "prev": {
      if (!s.chunks) return;
      const i = Math.max(0, Math.min(s.chunks.length - 1, s.index + (msg.cmd === "next" ? 1 : -1)));
      await setState({ index: i, status: "playing" });
      return toPlayer({ cmd: "seek", index: i });
    }
    case "restart":
      if (!s.chunks) return;
      await setState({ index: 0, status: "playing", resumedFrom: null });
      return toPlayer({ cmd: "seek", index: 0 });
    case "stop":
      return stop();
    case "settings":
      await chrome.storage.local.set({ voice: msg.voice, speed: msg.speed });
      // voice and speed are baked into the audio, so the rest of the article is re-requested
      // from the current sentence; chunking does not depend on either, so indexes line up
      if (s.text && (s.status === "playing" || s.status === "paused")) {
        try {
          await start({ text: s.text, title: s.title, source: s.source, tabId: s.tabId,
                        url: s.url, index: s.index });
        } catch (e) {
          await setState({ status: "error", error: e.message });
        }
      }
      return;
    case "voices":
      return api("/voices").then((d) => d.voices).catch(() => null);
    case "health":
      return api("/health").catch(() => null);
    case "setup":
      return chrome.tabs.create({ url: chrome.runtime.getURL("welcome.html") });
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg.to !== "bg") return;
  if (msg.event) {
    playerEvent(msg);
    return;
  }
  command(msg).then(reply, (e) => reply({ error: e.message }));
  return true;
});

async function playerEvent(msg) {
  if (msg.event === "index") {
    const s = await setState({ index: msg.index });
    const c = s.chunks?.[msg.index];
    if (c) toPage(s.tabId, { cmd: "show", sentence: c.sentence });
    await savePosition(s, msg.index);
  }
  if (msg.event === "ended") {
    const s = await getState();
    if (s.url) await chrome.storage.local.remove(POS + s.url);   // finished: start fresh next time
    if (s.tabId) toPage(s.tabId, { cmd: "clear" });
    await setState({ status: "idle", index: 0, resumedFrom: null });
  }
  if (msg.event === "error") {
    await setState({ status: "error",
                     error: /fetch/i.test(msg.message) ? NOT_RUNNING : msg.message });
  }
}

chrome.commands.onCommand.addListener((name) => {
  if (name === "toggle-reading") command({ cmd: "toggle" });
});

chrome.runtime.onInstalled.addListener(({ reason }) => {
  // a store install has no engine yet, so the first thing a new user sees is how to get one
  if (reason === "install") chrome.tabs.create({ url: chrome.runtime.getURL("welcome.html") });
  chrome.contextMenus.create({ id: "read-selection", title: "Read selection aloud",
                               contexts: ["selection"] });
  chrome.contextMenus.create({ id: "read-page", title: "Read this page aloud",
                               contexts: ["page"] });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "read-selection") readTab(tab, info.selectionText);
  if (info.menuItemId === "read-page") readTab(tab);
});

chrome.tabs.onRemoved.addListener(async (tabId) => {
  if ((await getState()).tabId === tabId) stop();
});
