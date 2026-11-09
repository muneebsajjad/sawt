"""Save as MP3: an article, or the queue, as one MP3 in the Downloads folder.

From there it goes to a phone however the person likes (AirDrop, a messenger, a cable). Nothing
here touches the network: the engine still only listens on 127.0.0.1.
"""
import hmac
import pathlib
import re
import secrets
import subprocess
import sys
import threading

import numpy as np
import soundfile as sf

from . import paths
from .synth import chunk_key

SR = 24000                  # Kokoro's sample rate
GAP_SENTENCE = 0.18         # the same pauses the browser player leaves
GAP_PARA = 0.55
GAP_ARTICLE = 1.8
MAX_ITEMS = 3


class ShareError(Exception):
    pass


def file_name(titles):
    base = titles[0] if len(titles) == 1 else f"{len(titles)} articles"
    base = re.sub(r'[^\w\s.,()&\'-]', '', base).strip()[:80] or "Sawt"
    return f"{base}.mp3"


def downloads():
    d = pathlib.Path.home() / "Downloads"
    return d if d.is_dir() else pathlib.Path.home()


def unique(path):
    """name.mp3, then name (2).mp3, ...: never overwrite something already saved."""
    n = 2
    out = path
    while out.exists():
        out = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return out


class Share:
    """One save: synthesizes in the background, then moves the MP3 into Downloads."""

    def __init__(self, engine, items, voice, speed):
        self.id = secrets.token_hex(8)
        self.engine, self.items, self.voice, self.speed = engine, items, voice, speed
        self.titles = [it["title"] for it in items]
        self.name = file_name(self.titles)
        self.state = "working"          # working -> saved, or error, or closed (cancelled)
        self.error = None
        self.done = self.total = 0
        self.seconds = 0.0
        self.file = paths.WORK / "share" / f"{self.id}.mp3"
        self.cancelled = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def status(self):
        out = {"id": self.id, "state": self.state, "done": self.done, "total": self.total,
               "titles": self.titles, "name": self.name, "error": self.error,
               "seconds": round(self.seconds)}
        if self.state == "saved":
            out["path"] = str(self.file)
            out["folder"] = self.file.parent.name
        return out

    def _run(self):
        part = self.file.with_suffix(".part")
        try:
            plans = [self.engine.plan(f"{it['title']}\n\n{it['text']}")[0] for it in self.items]
            self.total = sum(len(p) for p in plans)
            part.parent.mkdir(parents=True, exist_ok=True)
            # written as it is made: an hour of float audio would not fit in memory comfortably
            with sf.SoundFile(part, "w", SR, 1, format="MP3") as out:
                for n, chunks in enumerate(plans):
                    if n:
                        self._write(out, GAP_ARTICLE)
                    for c in chunks:
                        if self.cancelled.is_set():
                            return
                        audio = self.engine.audio_of(chunk_key(c["text"], self.voice, self.speed),
                                                     c["text"], self.voice, self.speed)
                        out.write(np.asarray(audio, dtype="float32"))
                        self.seconds += len(audio) / SR
                        self._write(out, GAP_PARA if c["para_end"] else GAP_SENTENCE)
                        self.done += 1
            self.file = unique(downloads() / self.name)
            part.replace(self.file)
            self.state = "saved"
        except Exception as e:                      # disk, encoder: report it, keep the engine
            self.state, self.error = "error", f"Could not make the audio ({e})."
        finally:
            if self.state != "saved":
                part.unlink(missing_ok=True)

    def _write(self, out, seconds):
        out.write(np.zeros(int(SR * seconds), dtype="float32"))
        self.seconds += seconds

    def close(self):
        """Cancel one still being made; a saved file is the user's and stays."""
        self.cancelled.set()
        if self.state == "working":
            self.state = "closed"

    def reveal(self):
        """Show the saved file in Finder / Explorer / the file manager."""
        if self.state != "saved" or not self.file.exists():
            return False
        f = str(self.file)
        if sys.platform == "darwin":
            cmd = ["open", "-R", f]
        elif sys.platform == "win32":
            cmd = ["explorer", f"/select,{f}"]
        else:
            cmd = ["xdg-open", str(self.file.parent)]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            return False
        return True


class Shares:
    """At most one save at a time: a new one cancels one still being made."""

    def __init__(self, engine):
        self.engine = engine
        self.current = None
        self.lock = threading.Lock()

    def start(self, items, voice, speed):
        if not 1 <= len(items) <= MAX_ITEMS:
            raise ShareError(f"Save between 1 and {MAX_ITEMS} articles.")
        clean = []
        for it in items:
            title = " ".join(str(it.get("title") or "Untitled").split())[:200]
            text = str(it.get("text") or "")
            if not text.strip():
                raise ShareError(f"“{title}” has no text to read.")
            clean.append({"title": title, "text": text})
        with self.lock:
            if self.current:
                self.current.close()
            self.current = Share(self.engine, clean, voice, speed)
            return self.current

    def get(self, sid):
        s = self.current
        return s if s and hmac.compare_digest(s.id, sid) else None

    def stop(self, sid):
        s = self.get(sid)
        if s:
            s.close()
        return s
