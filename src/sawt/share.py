"""Send to phone: an article, or the queue, as one MP3 that a phone on the same Wi-Fi fetches.

The engine itself only ever listens on 127.0.0.1. A share opens a second, separate server on
the computer's local network address for a short while, which answers exactly two requests,
both under a long random token: a small page with a player and a save button, and the MP3.
It closes after TTL seconds, when the share is stopped, or when a new share replaces it.
Nothing goes through the internet: the phone talks to this computer over the local network.
"""
import hmac
import html
import ipaddress
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import soundfile as sf

from . import paths
from .synth import chunk_key

TTL = 15 * 60               # seconds the phone link stays open once the audio is ready
SR = 24000                  # Kokoro's sample rate
GAP_SENTENCE = 0.18         # the same pauses the browser player leaves
GAP_PARA = 0.55
GAP_ARTICLE = 1.8
MAX_ITEMS = 3


class ShareError(Exception):
    pass


def lan_ip():
    """This computer's address on the local network, or None. Connecting a UDP socket sends
    nothing; it only asks the OS which interface would carry the traffic."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    addr = ipaddress.ip_address(ip)
    # only a private network: never open a port on an address the internet can reach
    if addr.is_loopback or not addr.is_private or addr.is_link_local:
        return None
    return ip


def file_name(titles):
    base = titles[0] if len(titles) == 1 else f"{len(titles)} articles"
    base = re.sub(r'[^\w\s.,()&\'-]', '', base).strip()[:80] or "Sawt"
    return f"{base}.mp3"


class Share:
    """One send: synthesizes in the background, then serves the result to the phone."""

    def __init__(self, engine, items, voice, speed):
        self.id = secrets.token_hex(8)
        self.token = secrets.token_urlsafe(24)
        self.engine, self.items, self.voice, self.speed = engine, items, voice, speed
        self.titles = [it["title"] for it in items]
        self.name = file_name(self.titles)
        self.state = "working"          # working -> ready -> closed, or error
        self.error = None
        self.done = self.total = 0
        self.seconds = 0.0
        self.file = paths.WORK / "share" / f"{self.id}.mp3"
        self.url = None
        self.expires = None
        self.fetched = False            # the phone has asked for the audio
        self.server = None
        self.cancelled = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def status(self):
        out = {"id": self.id, "state": self.state, "done": self.done, "total": self.total,
               "titles": self.titles, "name": self.name, "error": self.error,
               "seconds": round(self.seconds), "fetched": self.fetched}
        if self.state == "ready":
            out["url"] = self.url
            # what the phone's own address must start with to be on the same network
            out["network"] = self.url.split("//")[1].rsplit(".", 1)[0] + "."
            out["expiresIn"] = max(0, round(self.expires - time.time()))
            out["size"] = self.file.stat().st_size if self.file.exists() else 0
            out["qr"] = qr_data_uri(self.url)
        return out

    def _run(self):
        try:
            ip = lan_ip()
            if ip is None:
                raise ShareError("This computer isn't on a local network. Connect to Wi-Fi "
                                 "and try again.")
            plans = [self.engine.plan(f"{it['title']}\n\n{it['text']}")[0] for it in self.items]
            self.total = sum(len(p) for p in plans)
            self.file.parent.mkdir(parents=True, exist_ok=True)
            part = self.file.with_suffix(".part")
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
            part.replace(self.file)
            self._open(ip)
        except ShareError as e:
            self.state, self.error = "error", str(e)
        except Exception as e:                      # disk, encoder: report it, keep the engine
            self.state, self.error = "error", f"Could not make the audio ({e})."
        finally:
            if self.state != "ready":
                self.file.with_suffix(".part").unlink(missing_ok=True)

    def _write(self, out, seconds):
        out.write(np.zeros(int(SR * seconds), dtype="float32"))
        self.seconds += seconds

    def _open(self, ip):
        share = self

        class Phone(PhoneHandler):
            pass
        Phone.share = share
        try:
            self.server = ThreadingHTTPServer((ip, 0), Phone)
        except OSError as e:
            raise ShareError(f"Could not open the phone link on {ip} ({e}).")
        self.server.daemon_threads = True
        self.url = f"http://{ip}:{self.server.server_address[1]}/{self.token}"
        self.expires = time.time() + TTL
        self.state = "ready"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Timer(TTL, self.close).start()

    def close(self):
        self.cancelled.set()
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            self.server.server_close()
            self.server = None
        if self.state in ("working", "ready"):
            self.state = "closed"
        self.file.unlink(missing_ok=True)


def qr_data_uri(url):
    import segno
    return segno.make(url, error="m").svg_data_uri(scale=6, border=2)


PAGE = """<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title} · Sawt</title>
<style>
:root {{ --bg:#fff; --fg:#16181d; --muted:#6b7280; --line:#e5e7eb; --accent:#0d9488;
        --accent-fg:#fff; color-scheme: light dark; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#15161b; --fg:#ececf1; --muted:#9a9ca8; --line:#2a2c35; --accent:#2dd4bf;
          --accent-fg:#06201d; }} }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg);
       font:17px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
main {{ max-width:520px; margin:0 auto; padding:28px 20px 40px; }}
.brand {{ font-size:13px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent);
         font-weight:700; }}
h1 {{ font-size:22px; line-height:1.25; margin:6px 0 4px; }}
.meta {{ color:var(--muted); font-size:14px; margin:0 0 20px; }}
ol {{ margin:0 0 20px; padding-left:20px; }} li {{ margin:4px 0; }}
audio {{ width:100%; margin:0 0 16px; }}
a.save {{ display:block; text-align:center; text-decoration:none; background:var(--accent);
         color:var(--accent-fg); font-weight:600; padding:14px; border-radius:12px; }}
.how {{ color:var(--muted); font-size:14px; margin-top:16px; }}
</style>
<main>
  <div class="brand">Sawt</div>
  <h1>{title}</h1>
  <p class="meta">{minutes} · {size}</p>
  {list}
  <audio controls preload="metadata" src="{audio}"></audio>
  <a class="save" href="{audio}?save=1" download="{name}">Save to phone</a>
  <p class="how">Save it to listen offline, on the way home or anywhere. On iPhone it goes
    to Files → Downloads; on Android, to Downloads. This link works for 15 minutes, and only
    on this Wi-Fi.</p>
</main>
</html>
"""


def page(share):
    titles = share.titles
    lst = ("<ol>" + "".join(f"<li>{html.escape(t)}</li>" for t in titles) + "</ol>"
           if len(titles) > 1 else "")
    size = share.file.stat().st_size if share.file.exists() else 0
    minutes = max(1, round(share.seconds / 60))
    return PAGE.format(title=html.escape(titles[0] if len(titles) == 1
                                         else f"{len(titles)} articles"),
                       minutes=f"{minutes} min", size=f"{size / 1e6:.1f} MB", list=lst,
                       audio=f"/{share.token}/audio.mp3", name=html.escape(share.name))


class PhoneHandler(BaseHTTPRequestHandler):
    """Answers only the share's page and its audio, under its token. Everything else is 404."""
    share = None
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _plain(self, code, text):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        s = self.share
        path, _, query = self.path.partition("?")
        parts = path.strip("/").split("/")
        if s is None or s.state != "ready" or not parts or \
                not hmac.compare_digest(parts[0].encode(), s.token.encode()):
            return self._plain(404, "This link has expired. Send it again from Sawt.")
        if len(parts) == 1:
            body = page(s).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return
        if parts[1:] != ["audio.mp3"]:
            return self._plain(404, "Not found.")
        self._audio(s, "save=1" in query)

    def _audio(self, s, save):
        size = s.file.stat().st_size
        start, end = 0, size - 1
        # players (Safari above all) fetch audio in ranges and refuse a file served without them
        m = re.match(r'^bytes=(\d*)-(\d*)$', self.headers.get("Range", ""))
        if m and (m[1] or m[2]):
            if m[1]:
                start, end = int(m[1]), min(int(m[2]) if m[2] else size - 1, size - 1)
            else:
                start = max(0, size - int(m[2]))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                return self.end_headers()
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Cache-Control", "no-store")
        if save:
            self.send_header("Content-Disposition",
                             f"attachment; filename*=UTF-8''{_quote(s.name)}")
        self.end_headers()
        s.fetched = True
        if self.command == "HEAD":
            return
        with open(s.file, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                block = f.read(min(65536, left))
                if not block:
                    break
                try:
                    self.wfile.write(block)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(block)


def _quote(name):
    from urllib.parse import quote
    return quote(name)


class Shares:
    """At most one share at a time: a new one replaces the old."""

    def __init__(self, engine):
        self.engine = engine
        self.current = None
        self.lock = threading.Lock()

    def start(self, items, voice, speed):
        if not 1 <= len(items) <= MAX_ITEMS:
            raise ShareError(f"Send between 1 and {MAX_ITEMS} articles.")
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
