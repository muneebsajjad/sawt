"""The engine and the extension ship separately (PyPI, the Chrome Web Store) but are released
together and say so with one version number. A release that bumps one and forgets the other fails here."""
import json
from pathlib import Path

import sawt

ROOT = Path(__file__).resolve().parent.parent


def test_extension_and_engine_versions_match():
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text())
    assert manifest["version"] == sawt.__version__, (
        f"extension {manifest['version']} vs engine {sawt.__version__}: bump both")
