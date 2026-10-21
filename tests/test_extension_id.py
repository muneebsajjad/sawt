import base64
import hashlib
import json
from pathlib import Path

from sawt.serve import PUBLISHED_EXTENSION_IDS

MANIFEST = Path(__file__).resolve().parent.parent / "extension" / "manifest.json"


def test_manifest_key_matches_pinned_store_id():
    # Chrome derives an extension's ID from its public key: SHA-256, first 16 bytes, hex
    # digits mapped 0-f -> a-p. The key in the manifest must give the ID the engine trusts.
    key = json.loads(MANIFEST.read_text())["key"]
    digest = hashlib.sha256(base64.b64decode(key)).hexdigest()[:32]
    ext_id = digest.translate(str.maketrans("0123456789abcdef", "abcdefghijklmnop"))
    assert ext_id in PUBLISHED_EXTENSION_IDS
