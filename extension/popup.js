// Renders chrome.storage.session.player and sends commands to the background worker.
const $ = (id) => document.getElementById(id);
const DEFAULTS = { voice: "af_bella", speed: 0.85 };

const send = (cmd, extra = {}) => chrome.runtime.sendMessage({ to: "bg", cmd, ...extra });

function render(p = { status: "idle" }) {
  const total = p.chunks?.length || 0;
  const active = p.status === "playing" || p.status === "paused";

  $("title").textContent = p.title || "Sawt";
  $("status").textContent = {
    idle: "Idle",
    loading: "Reading the page…",
    playing: `Playing · ${p.index + 1} / ${total}`,
    paused: `Paused · ${p.index + 1} / ${total}`,
    error: "Stopped",
  }[p.status] || p.status;
  const c = active ? p.chunks[p.index] : null;
  $("sentence").textContent = c ? p.sentences?.[c.sentence] ?? c.text : "";

  $("resumed").hidden = !(active && p.resumedFrom);
  $("error").hidden = p.status !== "error";
  $("error").textContent = p.error || "";

  $("read").textContent = active ? "Read this page instead" : "Read this page";
  $("read").disabled = p.status === "loading";
  for (const id of ["prev", "toggle", "next", "stop"]) $(id).disabled = !active;
  $("toggle").textContent = p.status === "paused" ? "▶" : "⏸";
}

// Without the engine nothing else in the popup can work, so it is replaced by the way to get one.
async function checkEngine() {
  const ok = !!(await send("health"));
  $("setup").hidden = ok;
  for (const id of ["read", "controls", "settings"]) $(id).hidden = !ok;
  return ok;
}

async function loadSettings() {
  const s = { ...DEFAULTS, ...(await chrome.storage.local.get(["voice", "speed"])) };
  const voices = (await send("voices")) || [s.voice];
  $("voice").replaceChildren(...voices.map((v) => new Option(v, v, false, v === s.voice)));
  $("speed").value = String(s.speed);
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
$("setup-open").onclick = () => send("setup").then(() => window.close());
$("voice").onchange = changeSettings;
$("speed").onchange = changeSettings;

chrome.storage.session.onChanged.addListener((changes) => {
  if (changes.player) render(changes.player.newValue);
});

chrome.storage.session.get("player").then(({ player }) => render(player));
checkEngine().then((ok) => ok && loadSettings());
