// Renders chrome.storage.session.player and sends commands to the background worker.
const $ = (id) => document.getElementById(id);
const DEFAULTS = { voice: "bm_fable", speed: 1.1, meanings: "3.0", zoom: false };

const send = (cmd, extra = {}) => chrome.runtime.sendMessage({ to: "bg", cmd, ...extra });

let player = { status: "idle" };

function render(p = { status: "idle" }) {
  player = p;
  const total = p.chunks?.length || 0;
  const active = p.status === "playing" || p.status === "paused";

  $("title").textContent = p.title || "Sawt";
  $("status").dataset.state = p.status;
  $("status").textContent = {
    idle: "Idle",
    loading: "Reading the page…",
    playing: `Playing · ${p.index + 1} of ${total}`,
    paused: `Paused · ${p.index + 1} of ${total}`,
    error: "Stopped",
  }[p.status] || p.status;
  const c = active ? p.chunks[p.index] : null;
  $("sentence").textContent = c ? p.sentences?.[c.sentence] ?? c.text : "";
  $("progress").hidden = !active;
  if (active) $("progress").firstElementChild.style.width = `${((p.index + 1) / total) * 100}%`;

  $("resumed").hidden = !(active && p.resumedFrom);
  $("error").hidden = p.status !== "error";
  $("error").textContent = p.error || "";

  $("read").textContent = active ? "Read this page instead" : "Read this page";
  $("read").disabled = p.status === "loading";
  for (const id of ["prev", "toggle", "next", "stop"]) $(id).disabled = !active;
  $("toggle").textContent = p.status === "paused" ? "▶" : "⏸";
  if (active) renderWords(); else $("words").hidden = true;
  chrome.storage.local.get("queue").then(({ queue }) => renderQueue(queue));
}

function host(url) {
  try {
    const u = new URL(url);
    return u.protocol === "file:" ? decodeURIComponent(u.pathname.split("/").pop()) : u.hostname;
  } catch {
    return "";
  }
}

function renderQueue(queue = []) {
  queueLength = queue.length;
  if ($("share").hidden) renderShare(null);
  const now = player.queueId;
  const fromQueue = queue.some((i) => i.id === now)
    && ["loading", "playing", "paused"].includes(player.status);
  $("queue-count").textContent = queue.length ? `· ${queue.length} of 3` : "";
  $("queue-empty").hidden = queue.length > 0;
  $("queue-play").hidden = !queue.length;
  $("queue-play").textContent = fromQueue
    ? (queue.length > 1 ? "Skip to the next article" : "Done with this one")
    : "Play the queue";
  $("queue-list").replaceChildren(...queue.map((item) => {
    const li = document.createElement("li");
    li.classList.toggle("now", fromQueue && item.id === now);
    const play = document.createElement("button");
    play.className = "item";
    play.title = "Read this one now";
    const t = document.createElement("span");
    t.className = "t";
    t.textContent = item.title || host(item.url);
    const h = document.createElement("span");
    h.className = "h muted";
    h.textContent = (fromQueue && item.id === now ? "Now reading · " : "")
      + (item.source === "pdf" ? "PDF · " : "") + host(item.url);
    play.append(t, h);
    play.onclick = () => send("playQueue", { id: item.id });
    const del = document.createElement("button");
    del.className = "del";
    del.title = "Remove from the queue";
    del.setAttribute("aria-label", `Remove ${item.title} from the queue`);
    del.textContent = "×";
    del.onclick = () => send("dequeue", { id: item.id });
    li.append(play, del);
    return li;
  }));
}

// ---- Send to phone ----
let shareTimer = null;
let queueLength = 0;

function renderShare(st) {
  const live = st && ["working", "ready", "error"].includes(st.state);
  $("share").hidden = !live;
  $("share-start").hidden = live;
  $("share-label").textContent = queueLength > 1 ? "Send the queue to my phone"
    : queueLength === 1 ? "Send the queued article to my phone" : "Send this page to my phone";
  clearTimeout(shareTimer);
  if (!live) return;
  $("share-working").hidden = st.state !== "working";
  $("share-ready").hidden = st.state !== "ready";
  $("share-error").hidden = st.state !== "error";
  $("share-error").textContent = st.error || "";
  if (st.state === "working") {
    const pct = st.total ? Math.round((st.done / st.total) * 100) : 0;
    $("share-progress-text").textContent = `Making the audio… ${pct}%`;
    $("share-bar").style.width = `${pct}%`;
    $("share-done").textContent = "Cancel";
  } else if (st.state === "ready") {
    if ($("share-qr").src !== st.qr) $("share-qr").src = st.qr;
    const what = st.titles.length > 1 ? `${st.titles.length} articles` : st.titles[0];
    const min = Math.max(1, Math.round(st.seconds / 60));
    const left = Math.ceil(st.expiresIn / 60);
    $("share-what").classList.toggle("sent", st.fetched);
    $("share-what").textContent = st.fetched ? "✓ Your phone has it"
      : `${what} · ${min} min of audio`;
    $("share-how").hidden = st.fetched;
    $("share-net").hidden = st.fetched || !st.network;
    $("share-prefix").textContent = st.network || "";
    $("share-done").textContent = st.fetched ? "Done" : `Stop sharing (link closes in ${left} min)`;
  } else {
    $("share-done").textContent = "Close";
  }
  if (st.state !== "error") shareTimer = setTimeout(pollShare, st.state === "working" ? 700 : 2000);
}

async function pollShare() {
  renderShare(await send("shareStatus"));
}

$("share-start").onclick = async () => {
  $("share-start").disabled = true;
  renderShare({ state: "working", done: 0, total: 0 });
  const st = await send("share");
  $("share-start").disabled = false;
  if (st?.error) renderShare({ state: "error", error: st.error });
  else renderShare(st);
};
$("share-done").onclick = async () => {
  await send("shareStop");
  renderShare(null);
};

function note(text, isError = false) {
  $("queue-note").hidden = !text;
  $("queue-note").textContent = text || "";
  $("queue-note").classList.toggle("err", isError);
}

// Every word explained (or due to be) in this article, so it can be reviewed afterwards.
async function renderWords() {
  const words = (await send("pageWords")) || [];
  $("words").hidden = !words.length;
  $("words-count").textContent = `· ${words.length}`;
  $("words-list").replaceChildren(...words.map((w) => {
    const li = document.createElement("li");
    const b = document.createElement("b");
    b.textContent = w.word;
    li.append(b, ` ${w.senses[0][1]}`);
    return li;
  }));
}

// Without the engine nothing else in the popup can work, so it is replaced by the way to get one.
async function checkEngine() {
  const ok = !!(await send("health"));
  $("setup").hidden = ok;
  for (const id of ["read", "controls", "queue", "settings", "zoom-row"]) $(id).hidden = !ok;
  return ok;
}

// "af_bella" -> "Bella · US": Kokoro's ids start with a for American English, b for British.
function voiceLabel(id) {
  const [, accent, name] = id.match(/^([ab])[fm]_(.+)$/) || [, "", id];
  const nice = name.charAt(0).toUpperCase() + name.slice(1);
  return accent ? `${nice} · ${accent === "a" ? "US" : "UK"}` : id;
}

async function loadSettings() {
  const s = { ...DEFAULTS,
              ...(await chrome.storage.local.get(["voice", "speed", "meanings", "zoom"])) };
  const voices = (await send("voices")) || [s.voice];
  $("voice").replaceChildren(...voices.map((v) => new Option(voiceLabel(v), v, false, v === s.voice)));
  $("speed").value = String(s.speed);
  $("meanings").value = s.meanings;
  $("zoom").checked = s.zoom;
  const { theme = "auto" } = await chrome.storage.local.get("theme");
  document.querySelector(`input[name="theme"][value="${theme}"]`).checked = true;
}

function changeSettings() {
  send("settings", { voice: $("voice").value, speed: parseFloat($("speed").value) });
}

$("read").onclick = () => send("read");
$("toggle").onclick = () => send("toggle");
$("prev").onclick = () => send("prev");
$("next").onclick = () => send("next");
$("stop").onclick = () => send("stop");
$("restart").onclick = () => send("restart");
$("queue-add").onclick = async () => {
  $("queue-add").disabled = true;
  note("Saving this page…");
  const r = await send("enqueue");
  $("queue-add").disabled = false;
  if (r?.error) note(r.error, true);
  else note(r?.already ? "Already in the queue." : "Added. Close the tab whenever you like.");
};
$("queue-play").onclick = () => {
  const reading = player.queueId && ["loading", "playing", "paused"].includes(player.status);
  send(reading ? "skip" : "playQueue");
};
$("setup-open").onclick = () => send("setup").then(() => window.close());
$("voice").onchange = changeSettings;
$("speed").onchange = changeSettings;
for (const r of document.querySelectorAll('input[name="theme"]')) {
  r.onchange = () => chrome.storage.local.set({ theme: r.value });   // theme.js applies it
}
$("zoom").onchange = () => send("zoom", { value: $("zoom").checked });
$("meanings").onchange = () => send("meanings", { value: $("meanings").value }).then(renderWords);

chrome.storage.session.onChanged.addListener((changes) => {
  if (changes.player) render(changes.player.newValue);
});
chrome.storage.local.onChanged.addListener((changes) => {
  if (changes.queue) renderQueue(changes.queue.newValue);
});

chrome.storage.session.get("player").then(({ player }) => render(player));
checkEngine().then((ok) => ok && (loadSettings(), pollShare()));
