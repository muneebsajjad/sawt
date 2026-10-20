"""Local TTS server for the browser extension: article text in, sentence wavs out.

The extension cannot run Kokoro, so this keeps the model loaded and speaks whatever page the
extension sends. Same text path as a book — normalize, pronounce.json, sentence chunks — and
the same content-addressed cache, so an article re-opened tomorrow plays without synthesis.

Only one article is live at a time. The worker synthesizes a few chunks ahead of whatever the
player last asked for, so a long article you abandon after two paragraphs costs two paragraphs.
"""
import argparse
import io
import json
import os
import pathlib
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf

from . import __version__, models, paths
from .synth import apply_dict, chunk, chunk_key, load_dict
from .textnorm import normalize

PORT = 7865
LOOKAHEAD = 6            # chunks synthesized ahead of the player's position
MAX_TEXT = 200_000       # chars; a whole book belongs in the book pipeline, not here
WAIT_SECONDS = 90        # how long a /chunk request blocks on synthesis before giving up
# One sentence per chunk, unlike a book's 420-char groups: the first chunk is the wait before
# any sound, and a short chunk after a short one is what keeps the start gapless.
CHUNK_CHARS = 220
SENTENCE_RE = re.compile(r'(?<=[.!?:;]) +')
# a period after these is not a sentence end: "Dr. Smith" must stay one sentence
NO_BREAK_RE = re.compile(r'\b(?:Mr|Mrs|Ms|Dr|Prof|St|Mt|Jr|Sr|vs|cf|ca|vol|pp|p|ch|fig|No|approx'
                         r'|i\.e|e\.g|a\.m|p\.m|[A-Z])\.$')
KEY_RE = re.compile(r'^[0-9a-f]{24}$')
# Extensions allowed to drive the server. Any extension the user installs can reach 127.0.0.1,
# so the published one is pinned here; SAWT_EXTENSION_IDS adds a local unpacked copy.
PUBLISHED_EXTENSION_IDS = set()          # fill in once the Chrome Web Store assigns the ID


def split_sentences(para):
    out = []
    for part in SENTENCE_RE.split(para):
        if out and NO_BREAK_RE.search(out[-1]):
            out[-1] += " " + part
        elif part.strip():
            out.append(part)
    return out


class Session:
    """The one article currently being read."""

    def __init__(self, sid, pieces, voice, speed, start):
        self.sid = sid
        self.pieces = pieces          # [{"key", "text", "para_end", "sentence"}]
        self.voice = voice
        self.speed = speed
        self.cursor = start           # index the player most recently asked for
        # a repeated sentence repeats its key, so a key maps to every position it occupies
        self.positions = {}
        for i, p in enumerate(pieces):
            self.positions.setdefault(p["key"], []).append(i)

    def position(self, key):
        """Where a requested key sits: its first occurrence at or after the cursor."""
        at = self.positions[key]
        return next((i for i in at if i >= self.cursor), at[0])


class Engine:
    def __init__(self, cache, pron_path):
        self.kokoro = models.load()
        self.voices = sorted(v for v in self.kokoro.get_voices() if v[0] in "ab")
        self.kokoro.create("Ready.", voice="af_bella", speed=1.0, lang="en-us")   # cold start
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.pron_path = pron_path
        self.session = None
        self.next_sid = 1
        self.cond = threading.Condition()
        threading.Thread(target=self._worker, daemon=True).start()

    def path(self, key):
        return self.cache / f"{key}.wav"

    def plan(self, text):
        """Spoken chunks plus the original sentences they came from.

        Sentences are split before normalizing, not after, so each chunk can point back at text
        that actually appears on the page: "$5m" is what the page shows, not "five million
        dollars". The extension highlights by that pointer. A sentence too long for one chunk
        becomes several chunks sharing one sentence index.
        """
        # re-read each time so an edit to pronounce.json applies to the next article
        pron = load_dict(self.pron_path)
        chunks, sentences = [], []
        for para in re.split(r'\n\s*\n', text):
            para = " ".join(para.split())
            for raw in split_sentences(para):
                pieces = chunk(apply_dict(normalize(raw), pron), CHUNK_CHARS)
                if not pieces:
                    continue
                chunks += [{"text": p["text"], "para_end": False, "sentence": len(sentences)}
                           for p in pieces]
                sentences.append(raw)
            if chunks:
                chunks[-1]["para_end"] = True
        return chunks, sentences

    def start(self, text, voice, speed, start):
        chunks, sentences = self.plan(text)
        pieces = [dict(c, key=chunk_key(c["text"], voice, speed)) for c in chunks]
        with self.cond:
            s = Session(self.next_sid, pieces, voice, speed, min(start, max(len(pieces) - 1, 0)))
            self.next_sid += 1
            self.session = s
            self.cond.notify_all()
        return s, sentences

    def stop(self):
        with self.cond:
            self.session = None
            self.cond.notify_all()

    def _next_job(self):
        """First uncached chunk in [cursor, cursor + LOOKAHEAD], or None."""
        s = self.session
        if s is None:
            return None
        for i in range(s.cursor, min(s.cursor + LOOKAHEAD + 1, len(s.pieces))):
            if not self.path(s.pieces[i]["key"]).exists():
                return s, s.pieces[i]
        return None

    def _worker(self):
        while True:
            with self.cond:
                job = self._next_job()
                while job is None:
                    self.cond.wait()
                    job = self._next_job()
            s, piece = job
            audio, sr = self.kokoro.create(piece["text"], voice=s.voice, speed=s.speed,
                                           lang="en-us")
            cached = self.path(piece["key"])
            # same .part + rename as synth.py: a kill mid-write must not leave a wav we trust
            tmp = cached.with_suffix(".part")
            sf.write(tmp, np.asarray(audio, dtype="float32"), sr, format="WAV")
            tmp.replace(cached)
            with self.cond:
                self.cond.notify_all()

    def wait_for(self, key):
        """Block until the chunk is on disk. Moves the cursor so the worker serves it next."""
        deadline = time.time() + WAIT_SECONDS
        with self.cond:
            s = self.session
            if s is not None and key in s.positions:
                s.cursor = s.position(key)
                self.cond.notify_all()
            elif not self.path(key).exists():
                return None                          # not part of the live article
            while not self.path(key).exists():
                left = deadline - time.time()
                if left <= 0 or self.session is not s:
                    return None
                self.cond.wait(left)
        return self.path(key)


class Handler(BaseHTTPRequestHandler):
    engine = None
    port = PORT
    extension_ids = set()                # empty: any chrome-extension:// origin (development)

    def log_message(self, fmt, *args):
        pass

    def _allowed(self):
        # Only the extension may call this. Host check stops DNS rebinding; a web page cannot
        # send the custom header without a CORS preflight, and preflights are never answered.
        host_ok = self.headers.get("Host") in (f"127.0.0.1:{self.port}", f"localhost:{self.port}")
        origin = self.headers.get("Origin", "")
        if self.extension_ids:
            origin_ok = origin == "" or origin.removeprefix("chrome-extension://") in self.extension_ids
        else:
            origin_ok = origin == "" or origin.startswith("chrome-extension://")
        return host_ok and origin_ok and self.headers.get("X-Sawt") == "1"

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(403)
        self.end_headers()

    def do_GET(self):
        if not self._allowed():
            return self._send(403, {"error": "forbidden"})
        if self.path == "/health":
            return self._send(200, {"ok": True, "version": __version__})
        if self.path == "/voices":
            return self._send(200, {"voices": self.engine.voices})
        m = re.match(r'^/chunk/([0-9a-f]+)\.wav$', self.path)
        if m and KEY_RE.match(m.group(1)):
            p = self.engine.wait_for(m.group(1))
            if p is None:
                return self._send(404, {"error": "unknown or cancelled chunk"})
            return self._send(200, p.read_bytes(), "audio/wav")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._allowed():
            return self._send(403, {"error": "forbidden"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > MAX_TEXT * 4:
                return self._send(413, {"error": "article too long"})
            req = json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "bad json"})

        if self.path == "/stop":
            self.engine.stop()
            return self._send(200, {"ok": True})
        if self.path == "/read":
            text = str(req.get("text", ""))[:MAX_TEXT]
            voice = req.get("voice", "af_bella")
            if voice not in self.engine.voices:
                return self._send(400, {"error": f"unknown voice {voice}"})
            try:
                speed = float(req.get("speed", 0.85))
            except (TypeError, ValueError):
                return self._send(400, {"error": "bad speed"})
            if not 0.5 <= speed <= 2.0:
                return self._send(400, {"error": "speed must be 0.5-2.0"})
            if not text.strip():
                return self._send(400, {"error": "no text"})
            s, sentences = self.engine.start(text, voice, speed, int(req.get("start", 0)))
            return self._send(200, {"session": s.sid, "chunks": s.pieces,
                                    "sentences": sentences})
        self._send(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--dict", default="pronounce.json")
    ap.add_argument("--allow-extension", action="append", default=[], metavar="ID",
                    help="also accept this extension ID (e.g. an unpacked dev copy)")
    args = ap.parse_args()

    dpath = pathlib.Path(args.dict)
    print("loading Kokoro…", flush=True)
    Handler.engine = Engine(paths.CACHE, dpath if dpath.is_absolute() else paths.ROOT / dpath)
    Handler.port = args.port
    env_ids = os.environ.get("SAWT_EXTENSION_IDS", "")
    Handler.extension_ids = (PUBLISHED_EXTENSION_IDS | set(args.allow_extension)
                             | {i.strip() for i in env_ids.split(",") if i.strip()})
    if not Handler.extension_ids:
        print("warning: no extension ID pinned - accepting requests from any extension",
              flush=True)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    srv.daemon_threads = True
    print(f"serving on http://127.0.0.1:{args.port}  ({len(Handler.engine.voices)} voices)",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
