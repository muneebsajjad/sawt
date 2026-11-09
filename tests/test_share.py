"""Send to phone: one MP3 made from the articles, served under a token to the local network."""
import time
import urllib.error
import urllib.request

import numpy as np
import pytest

from sawt import share


class FakeEngine:
    def plan(self, text):
        paras = [p for p in text.split("\n\n") if p.strip()]
        return [{"text": p, "para_end": True} for p in paras], paras

    def audio_of(self, key, text, voice, speed):
        return np.zeros(share.SR // 2, dtype="float32")


@pytest.fixture
def ready(tmp_path, monkeypatch):
    monkeypatch.setattr(share.paths, "WORK", tmp_path)
    monkeypatch.setattr(share, "lan_ip", lambda: "127.0.0.1")
    shares = share.Shares(FakeEngine())
    s = shares.start([{"title": "One", "text": "Hello there."},
                      {"title": "Two", "text": "Bye now."}], "bm_fable", 1.0, "phone")
    for _ in range(200):
        if s.state != "working":
            break
        time.sleep(0.02)
    yield shares, s
    s.close()


def get(url, headers=None):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}))
        return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_the_phone_gets_a_page_and_the_audio(ready):
    _, s = ready
    assert s.state == "ready" and s.name == "2 articles.mp3"
    code, _, body = get(s.url)
    assert code == 200 and b"Save to phone" in body and b"<li>One</li>" in body
    code, h, mp3 = get(s.url + "/audio.mp3")
    assert code == 200 and h["Content-Type"] == "audio/mpeg" and len(mp3) > 1000
    assert s.fetched and s.status()["qr"].startswith("data:image/svg+xml")


def test_ranges_for_safari(ready):
    _, s = ready
    code, h, body = get(s.url + "/audio.mp3", {"Range": "bytes=0-1"})
    assert code == 206 and body and len(body) == 2 and h["Content-Range"].endswith(
        f"/{s.file.stat().st_size}")
    assert get(s.url + "/audio.mp3", {"Range": "bytes=99999999-"})[0] == 416


def test_without_the_token_there_is_nothing(ready):
    _, s = ready
    base = s.url.rsplit("/", 1)[0]
    for path in ["/", "/nope", "/nope/audio.mp3", f"/{s.token}/other"]:
        assert get(base + path)[0] == 404


def test_a_stopped_share_is_gone(ready):
    shares, s = ready
    url = s.url
    shares.stop(s.id)
    assert not s.file.exists() and s.state == "closed"
    with pytest.raises(OSError):          # refused (macOS) or reset (Linux): either way, gone
        urllib.request.urlopen(url, timeout=2)


def test_a_new_share_replaces_the_old(ready):
    shares, s = ready
    t = shares.start([{"title": "Three", "text": "Again."}], "bm_fable", 1.0, "phone")
    assert s.state == "closed" and shares.get(t.id) is t and shares.get(s.id) is None
    t.close()


def test_limits():
    shares = share.Shares(FakeEngine())
    with pytest.raises(share.ShareError):
        shares.start([], "v", 1.0)
    with pytest.raises(share.ShareError):
        shares.start([{"title": "x", "text": "y"}] * 4, "v", 1.0)
    with pytest.raises(share.ShareError):
        shares.start([{"title": "Empty", "text": "  "}], "v", 1.0)


def test_off_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(share.paths, "WORK", tmp_path)
    monkeypatch.setattr(share, "lan_ip", lambda: None)
    s = share.Shares(FakeEngine()).start([{"title": "x", "text": "y"}], "v", 1.0, "phone")
    for _ in range(100):
        if s.state != "working":
            break
        time.sleep(0.02)
    assert s.state == "error" and "Wi-Fi" in s.error


def wait(s):
    for _ in range(200):
        if s.state != "working":
            return s
        time.sleep(0.02)
    return s


def test_save_puts_the_mp3_in_downloads_without_opening_anything(tmp_path, monkeypatch):
    monkeypatch.setattr(share.paths, "WORK", tmp_path / "work")
    monkeypatch.setattr(share, "downloads", lambda: tmp_path)
    monkeypatch.setattr(share, "lan_ip", lambda: pytest.fail("saving must not touch the network"))
    shares = share.Shares(FakeEngine())
    a = wait(shares.start([{"title": "My: Article?", "text": "Hello."}], "v", 1.0))
    assert a.state == "saved" and a.file == tmp_path / "My Article.mp3" and a.file.stat().st_size
    assert a.server is None and a.status()["path"] == str(a.file)
    b = wait(shares.start([{"title": "My: Article?", "text": "Hello."}], "v", 1.0))
    assert b.file.name == "My Article (2).mp3" and a.file.exists()     # replaced, not deleted
