"""The Kokoro model files: where they live, and fetching them on first use.

They are ~350MB, so they are downloaded once rather than shipped in the package. Every file is
checked against a pinned SHA-256: a truncated or tampered download is deleted, never loaded.

The model comes from model-files-v1.1, the first release whose export reports when each phoneme
is spoken; the extension follows along word by word with that. It keeps the upstream file name
kokoro-v1.0.onnx, so it is saved under a name of its own: an install holding the older file
would otherwise never fetch it.
"""
import hashlib
import os
import pathlib
import sys
import urllib.request

RELEASES = "https://github.com/thewh1teagle/kokoro-onnx/releases/download"
# local name -> (release file, SHA-256)
FILES = {
    "kokoro-v1.1.onnx": ("model-files-v1.1/kokoro-v1.0.onnx",
                         "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a"),
    "voices-v1.0.bin": ("model-files-v1.0/voices-v1.0.bin",
                        "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
}
MODEL, VOICES = FILES
REPLACED = ["kokoro-v1.0.onnx"]      # earlier models, deleted once their successor is in place


def model_dir():
    if os.environ.get("SAWT_MODELS"):
        return pathlib.Path(os.environ["SAWT_MODELS"]).expanduser()
    return pathlib.Path.home() / ".cache/sawt/models"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _download(name, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    remote, digest = FILES[name]
    with urllib.request.urlopen(f"{RELEASES}/{remote}") as res, open(tmp, "wb") as fh:
        total = int(res.headers.get("Content-Length", 0))
        done = 0
        while block := res.read(1 << 20):
            fh.write(block)
            done += len(block)
            if total:
                print(f"\r  {name}: {done * 100 // total}% of {total >> 20}MB", end="",
                      file=sys.stderr, flush=True)
    print(file=sys.stderr)
    if sha256(tmp) != digest:
        tmp.unlink()
        raise SystemExit(f"{name}: checksum mismatch after download - try again")
    tmp.replace(dest)


def ensure():
    """Paths to (model, voices), downloading whatever is missing."""
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    missing = [n for n in FILES if not (d / n).exists()]
    if missing:
        print(f"downloading the Kokoro voice model to {d} (one time, ~350MB)…",
              file=sys.stderr, flush=True)
        for name in missing:
            _download(name, d / name)
    for old in REPLACED:
        (d / old).unlink(missing_ok=True)
    return str(d / MODEL), str(d / VOICES)


def load():
    from kokoro_onnx import Kokoro
    return Kokoro(*ensure())
