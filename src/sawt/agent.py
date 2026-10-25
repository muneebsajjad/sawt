"""`sawt agent install | uninstall | status`: keep `serve` running in the background.

Each OS's own service manager starts the engine at login and restarts it if it dies, so nobody
has to keep a terminal open: launchd on macOS, a systemd user unit on Linux, a logon task in
Task Scheduler on Windows. install downloads the voice model first, in the foreground, so the
one slow step happens where its progress is visible.
"""
import os
import pathlib
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

from . import models, paths

NAME = "sawt"
LABEL = "local.sawt.serve"                                   # launchd
PLIST = pathlib.Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
UNIT = pathlib.Path.home() / ".config/systemd/user" / f"{NAME}.service"
TASK = "Sawt engine"                                         # Task Scheduler
LOG = paths.WORK / "serve.log"


def _serve_cmd(windowless=False):
    """The interpreter running this command, so the service uses the same install."""
    exe = pathlib.Path(sys.executable)
    if windowless:                                           # pythonw: no console window
        w = exe.with_name("pythonw.exe")
        exe = w if w.exists() else exe
    return [str(exe), "-m", "sawt", "serve"]


# --- macOS: launchd -------------------------------------------------------------------------

def plist_text():
    args = "".join(f"<string>{escape(a)}</string>" for a in _serve_cmd())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>{args}</array>
  <key>WorkingDirectory</key><string>{escape(str(paths.ROOT))}</string>
  <key>EnvironmentVariables</key>
  <dict><key>SAWT_HOME</key><string>{escape(str(paths.ROOT))}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{escape(str(LOG))}</string>
  <key>StandardErrorPath</key><string>{escape(str(LOG))}</string>
</dict>
</plist>
"""


def _launchd(action):
    domain = f"gui/{os.getuid()}"
    if action == "install":
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        PLIST.write_text(plist_text())
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
        subprocess.run(["launchctl", "bootstrap", domain, str(PLIST)], check=True)
        return f"installed {PLIST}"
    if action == "uninstall":
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
        PLIST.unlink(missing_ok=True)
        return f"removed {LABEL}"
    out = subprocess.run(["launchctl", "print", f"{domain}/{LABEL}"],
                         capture_output=True, text=True).stdout
    seen = {}
    for l in map(str.strip, out.splitlines()):          # the first of each is the service's own
        for key in ("state =", "pid ="):
            if l.startswith(key):
                seen.setdefault(key, l)
    return "\n".join(seen.values()) or None


# --- Linux: systemd user unit ---------------------------------------------------------------

def unit_text():
    cmd = " ".join(f'"{a}"' if " " in a else a for a in _serve_cmd())
    return f"""[Unit]
Description=Sawt read-aloud engine (local text-to-speech)
After=network.target

[Service]
ExecStart={cmd}
WorkingDirectory={paths.ROOT}
Environment="SAWT_HOME={paths.ROOT}"
Restart=always
RestartSec=3
StandardOutput=append:{LOG}
StandardError=append:{LOG}

[Install]
WantedBy=default.target
"""


def _systemd(action):
    if not shutil.which("systemctl"):
        raise SystemExit("no systemctl found - run `sawt serve` yourself, or start it with "
                         "your init system")
    ctl = ["systemctl", "--user"]
    if action == "install":
        UNIT.parent.mkdir(parents=True, exist_ok=True)
        UNIT.write_text(unit_text())
        subprocess.run(ctl + ["daemon-reload"], check=True)
        subprocess.run(ctl + ["enable", "--now", NAME], check=True)
        subprocess.run(ctl + ["restart", NAME], check=True)    # pick up a changed unit
        return f"installed {UNIT}"
    if action == "uninstall":
        subprocess.run(ctl + ["disable", "--now", NAME], capture_output=True)
        UNIT.unlink(missing_ok=True)
        subprocess.run(ctl + ["daemon-reload"], capture_output=True)
        return f"removed {NAME}.service"
    out = subprocess.run(ctl + ["is-active", NAME], capture_output=True, text=True).stdout.strip()
    return f"state = {out}" if UNIT.exists() else None


# --- Windows: Task Scheduler logon task -----------------------------------------------------

def task_xml():
    exe, *args = _serve_cmd(windowless=True)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Sawt read-aloud engine (local text-to-speech)</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
    <Hidden>true</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(exe)}</Command>
      <Arguments>{escape(" ".join(args))}</Arguments>
      <WorkingDirectory>{escape(str(paths.ROOT))}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(action):
    if action == "install":
        xml = paths.WORK / "sawt-task.xml"
        xml.write_text(task_xml(), encoding="utf-16")
        subprocess.run(["schtasks", "/End", "/TN", TASK], capture_output=True)
        subprocess.run(["schtasks", "/Create", "/TN", TASK, "/XML", str(xml), "/F"],
                       check=True, capture_output=True)
        subprocess.run(["schtasks", "/Run", "/TN", TASK], check=True, capture_output=True)
        xml.unlink(missing_ok=True)
        return f'installed Task Scheduler task "{TASK}"'
    if action == "uninstall":
        subprocess.run(["schtasks", "/End", "/TN", TASK], capture_output=True)
        subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], capture_output=True)
        return f'removed task "{TASK}"'
    out = subprocess.run(["schtasks", "/Query", "/TN", TASK, "/FO", "LIST"],
                         capture_output=True, text=True)
    if out.returncode:
        return None
    return "\n".join(l.strip() for l in out.stdout.splitlines() if l.startswith("Status"))


def run(action):
    if action not in ("install", "uninstall", "status"):
        raise SystemExit("usage: sawt agent <install|uninstall|status>")
    backend = {"darwin": _launchd, "win32": _schtasks}.get(sys.platform)
    if backend is None:
        backend = _systemd if sys.platform.startswith("linux") else None
    if backend is None:
        raise SystemExit(f"no background service support on {sys.platform} - run `sawt serve`")
    if action == "install":
        paths.WORK.mkdir(parents=True, exist_ok=True)
        models.ensure()                       # the one slow step, while someone is watching
        print(backend("install"))
        print(f"the engine now starts at login and restarts if it stops (log: {LOG})")
        print("after `uv tool upgrade sawt`, run `sawt agent install` again to restart it")
    elif action == "uninstall":
        print(backend("uninstall"))
    else:
        print(backend("status") or "not installed - run: sawt agent install")
