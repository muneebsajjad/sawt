"""`sawt <command> [args]`: one entry point for the pipeline and the read-aloud server.

Each command is a module with its own argparse main(), so this only picks the module and hands
it the rest of the command line.
"""
import importlib
import os
import pathlib
import subprocess
import sys

from . import __version__, paths

COMMANDS = {
    "extract": ("extract", "book file (EPUB/PDF/TXT) -> chapters"),
    "books": ("books", "list books, switch the active one"),
    "inspect": ("inspect_book", "check what extraction produced"),
    "trim": ("trim", "drop or retitle chapters"),
    "clean": ("clean", "repair scanned text: citation debris, OCR typos"),
    "names": ("names", "proper nouns to fix in pronounce.json"),
    "voices": ("voices", "list and audition voices"),
    "synth": ("synth", "synthesize the book (resumable)"),
    "progress": ("progress", "how far synth has got"),
    "qa": ("qa", "pace outliers and an audition file"),
    "build": ("assemble", "-> .m4b with chapters and/or mp3s"),
    "batch": ("batch", "several books, unattended"),
    "serve": ("serve", "read-aloud server for the browser extension"),
}

LABEL = "local.sawt.serve"
PLIST = pathlib.Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"


def usage():
    lines = [f"sawt {__version__} - local text-to-speech, no cloud", "",
             "usage: sawt <command> [args]", ""]
    lines += [f"  {name:<10}{desc}" for name, (_, desc) in COMMANDS.items()]
    lines += [f"  {'agent':<10}install | uninstall | status - start `serve` at login (macOS)",
              "", f"files live in {paths.ROOT}  (set SAWT_HOME to move them)"]
    return "\n".join(lines)


def agent(action):
    """launchd keeps `serve` running from login onward, and restarts it if it dies."""
    if sys.platform != "darwin":
        raise SystemExit("start-at-login is macOS only for now - run `sawt serve` yourself")
    domain = f"gui/{os.getuid()}"
    log = paths.WORK / "serve.log"
    if action == "install":
        PLIST.parent.mkdir(parents=True, exist_ok=True)
        paths.WORK.mkdir(parents=True, exist_ok=True)
        PLIST.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>{sys.executable}</string><string>-m</string><string>sawt</string><string>serve</string></array>
  <key>WorkingDirectory</key><string>{paths.ROOT}</string>
  <key>EnvironmentVariables</key>
  <dict><key>SAWT_HOME</key><string>{paths.ROOT}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
""")
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
        subprocess.run(["launchctl", "bootstrap", domain, str(PLIST)], check=True)
        print(f"installed: {PLIST}  (log: {log})")
    elif action == "uninstall":
        subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)
        PLIST.unlink(missing_ok=True)
        print(f"removed {LABEL}")
    elif action == "status":
        out = subprocess.run(["launchctl", "print", f"{domain}/{LABEL}"],
                             capture_output=True, text=True).stdout
        state = [l.strip() for l in out.splitlines() if l.strip().startswith(("state =", "pid ="))]
        print("\n".join(state) if state else "not installed - run: sawt agent install")
    else:
        raise SystemExit("usage: sawt agent <install|uninstall|status>")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(usage())
        sys.exit(0 if args else 1)
    if args[0] in ("-V", "--version"):
        print(__version__)
        return
    cmd, rest = args[0], args[1:]
    if cmd == "agent":
        return agent(rest[0] if rest else "status")
    if cmd not in COMMANDS:
        raise SystemExit(f"unknown command: {cmd}\n\n{usage()}")
    module = importlib.import_module(f".{COMMANDS[cmd][0]}", __package__)
    sys.argv = [f"sawt {cmd}", *rest]
    module.main()
