// The audio player. MV3 service workers cannot play sound, so this hidden page does.
// It knows nothing about pages or settings: it plays a chunk list and reports its position.
const SERVER = "http://127.0.0.1:7865";
const GAP_SENTENCE = 180;   // ms, same pauses as a book
const GAP_PARA = 550;
const WORD_TICK = 40;        // ms between checks of which word is being spoken

const audio = new Audio();
let chunks = [];
let index = 0;
let playing = false;
let finished = false;        // current chunk ended, next not started (paused inside a gap)
let gen = 0;                 // bumps on every load/seek/stop, so stale async work drops out
const blobs = new Map();     // key -> Promise<object URL>
const times = new Map();     // key -> Promise<[[charStart, charEnd, t0, t1], ...] | null>
let words = null;            // timings of the chunk playing now, once fetched
let word = -1;               // index into words last reported

function report(event, extra = {}) {
  chrome.runtime.sendMessage({ to: "bg", event, ...extra });
}

function fetchChunk(key) {
  if (!blobs.has(key)) {
    const p = fetch(`${SERVER}/chunk/${key}.wav`, { headers: { "X-Sawt": "1" } })
      .then((r) => {
        if (!r.ok) throw new Error(`chunk ${r.status}`);
        return r.blob();
      })
      .then((b) => URL.createObjectURL(b));
    p.catch(() => blobs.delete(key));
    blobs.set(key, p);
  }
  return blobs.get(key);
}

// Word timings are optional: an engine or model without them leaves the sentence highlight
// working exactly as before.
function fetchTimes(key) {
  if (!times.has(key)) {
    times.set(key, fetch(`${SERVER}/chunk/${key}.words.json`, { headers: { "X-Sawt": "1" } })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d?.words || null, () => null));
  }
  return times.get(key);
}

function forget(keep) {
  for (const [key, p] of blobs) {
    if (!keep.has(key)) {
      p.then(URL.revokeObjectURL, () => {});
      blobs.delete(key);
    }
  }
  for (const key of times.keys()) if (!keep.has(key)) times.delete(key);
}

// The word whose span holds the playhead; between two words, the one just finished, so the
// highlight never blinks off in the gaps.
setInterval(() => {
  if (!words?.length || audio.paused) return;
  const t = audio.currentTime;
  let i = word >= 0 && words[word][2] <= t ? word : 0;
  while (i + 1 < words.length && words[i + 1][2] <= t) i++;
  if (words[i][2] > t || i === word) return;
  word = i;
  report("word", { index, start: words[i][0], end: words[i][1] });
}, WORD_TICK);

async function playAt(i) {
  const my = ++gen;
  index = i;
  finished = false;
  if (i >= chunks.length) {
    playing = false;
    report("ended");
    return;
  }
  report("index", { index: i });
  words = null;
  word = -1;
  fetchTimes(chunks[i].key).then((w) => { if (my === gen) words = w; });
  try {
    const url = await fetchChunk(chunks[i].key);
    if (my !== gen) return;
    audio.src = url;
    if (playing) await audio.play();
    // asking for the next chunk is what moves the server's lookahead along
    if (chunks[i + 1]) fetchChunk(chunks[i + 1].key).catch(() => {});
    forget(new Set(chunks.slice(Math.max(0, i - 1), i + 2).map((c) => c.key)));
  } catch (e) {
    if (my === gen && e.name !== "AbortError") report("error", { message: e.message });
  }
}

audio.addEventListener("ended", () => {
  const my = gen;
  finished = true;
  const gap = chunks[index]?.para_end ? GAP_PARA : GAP_SENTENCE;
  setTimeout(() => {
    if (my === gen && playing) playAt(index + 1);
  }, gap);
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.to !== "offscreen") return;
  switch (msg.cmd) {
    case "load":
      forget(new Set());
      chunks = msg.chunks;
      playing = msg.play;
      playAt(msg.index || 0);
      break;
    case "pause":
      playing = false;
      audio.pause();
      break;
    case "resume":
      playing = true;
      if (finished) playAt(index + 1);
      else if (audio.src) audio.play().catch((e) => report("error", { message: e.message }));
      else playAt(index);
      break;
    case "seek":
      playing = true;
      playAt(msg.index);
      break;
    case "stop":
      gen++;
      playing = false;
      audio.pause();
      audio.removeAttribute("src");
      chunks = [];
      forget(new Set());
      break;
  }
});
