"""`sawt <command> [args]`: one entry point for the pipeline and the read-aloud server.

Each command is a module with its own argparse main(), so this only picks the module and hands
it the rest of the command line.
"""
import importlib
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

def usage():
    lines = [f"sawt {__version__} - local text-to-speech, no cloud", "",
             "usage: sawt <command> [args]", ""]
    lines += [f"  {name:<10}{desc}" for name, (_, desc) in COMMANDS.items()]
    lines += [f"  {'agent':<10}install | uninstall | status - run `serve` in the background, from login",
              "", f"files live in {paths.ROOT}  (set SAWT_HOME to move them)"]
    return "\n".join(lines)


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
        from . import agent
        return agent.run(rest[0] if rest else "status")
    if cmd not in COMMANDS:
        raise SystemExit(f"unknown command: {cmd}\n\n{usage()}")
    module = importlib.import_module(f".{COMMANDS[cmd][0]}", __package__)
    sys.argv = [f"sawt {cmd}", *rest]
    module.main()
