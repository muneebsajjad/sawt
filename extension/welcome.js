// First-run setup: shows the install commands and polls until the local engine answers.
const PACKAGE = "sawt";       // the PyPI name; keep in step with pyproject.toml
const $ = (id) => document.getElementById(id);

$("install-cmd").textContent = `uv tool install ${PACKAGE}`;

for (const pre of document.querySelectorAll("pre")) {
  const btn = document.createElement("button");
  btn.className = "copy";
  btn.textContent = "Copy";
  btn.onclick = async () => {
    await navigator.clipboard.writeText(pre.querySelector("code").textContent);
    btn.textContent = "Copied";
    setTimeout(() => { btn.textContent = "Copy"; }, 1500);
  };
  pre.append(btn);
}

const tabs = document.querySelectorAll("[role=tab]");
function showOs(os) {
  for (const t of tabs) t.setAttribute("aria-selected", String(t.dataset.os === os));
  for (const pre of document.querySelectorAll("pre[data-os]")) pre.hidden = pre.dataset.os !== os;
}
for (const t of tabs) t.onclick = () => showOs(t.dataset.os);
if (/Win/.test(navigator.platform)) showOs("win");

async function check() {
  const health = await chrome.runtime.sendMessage({ to: "bg", cmd: "health" }).catch(() => null);
  $("status").dataset.state = health ? "ok" : "missing";
  $("status-text").textContent = health
    ? `Engine running (v${health.version || "?"}) — you're ready`
    : "Engine not running yet — follow the steps below; this updates by itself";
  $("done").hidden = !health;
}

check();
setInterval(check, 2000);
