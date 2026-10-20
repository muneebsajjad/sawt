"""The Kokoro model files: where they live, and fetching them on first use.

They are ~350MB, so they are downloaded once rather than shipped in the package. Every file is
checked against a pinned SHA-256: a truncated or tampered download is deleted, never loaded.
"""
import hashlib
import os
import pathlib
import sys
import urllib.request

RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = {
    "kokoro-v1.0.onnx": "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}


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
    with urllib.request.urlopen(f"{RELEASE}/{name}") as res, open(tmp, "wb") as fh:
        total = int(res.headers.get("Content-Length", 0))
        done = 0
        while block := res.read(1 << 20):
            fh.write(block)
            done += len(block)
            if total:
                print(f"\r  {name}: {done * 100 // total}% of {total >> 20}MB", end="",
                      file=sys.stderr, flush=True)
    print(file=sys.stderr)
    if sha256(tmp) != FILES[name]:
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
    return str(d / "kokoro-v1.0.onnx"), str(d / "voices-v1.0.bin")


def load():
    from kokoro_onnx import Kokoro
    return Kokoro(*ensure())
