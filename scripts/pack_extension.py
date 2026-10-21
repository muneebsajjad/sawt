"""Zip extension/ for the Chrome Web Store: dist/extension-<version>.zip.

The manifest's "key" pins the store's extension ID on unpacked copies (so a local checkout
talks to the engine without --allow-extension). The store assigns that ID itself and rejects
uploads that carry a key, so it is dropped from the packaged manifest.
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "extension"

manifest = json.loads((SRC / "manifest.json").read_text())
manifest.pop("key", None)
out = ROOT / "dist" / f"extension-{manifest['version']}.zip"
out.parent.mkdir(exist_ok=True)

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(SRC.rglob("*")):
        rel = f.relative_to(SRC)
        if f.is_dir() or any(part.startswith(".") for part in rel.parts):
            continue
        if rel.as_posix() == "manifest.json":
            z.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        else:
            z.write(f, rel.as_posix())
print(out.relative_to(ROOT))
