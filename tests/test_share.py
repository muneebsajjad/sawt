"""Save as MP3: one MP3 made from the articles, in Downloads, never overwriting."""
import time

import numpy as np
import pytest

from sawt import share


class FakeEngine:
    def plan(self, text):
        paras = [p for p in text.split("\n\n") if p.strip()]
        return [{"text": p, "para_end": True} for p in paras], paras

    def audio_of(self, key, text, voice, speed):
        return np.zeros(share.SR // 2, dtype="float32")


def wait(s, seconds=120):
    """Until the MP3 is made. CI machines are far slower than a laptop, and the first MP3 a
    fresh macOS runner writes has taken over 30 s."""
    end = time.time() + seconds
    while s.state == "working" and time.time() < end:
        time.sleep(0.02)
    return s


@pytest.fixture
def shares(tmp_path, monkeypatch):
    monkeypatch.setattr(share.paths, "WORK", tmp_path / "work")
    monkeypatch.setattr(share, "downloads", lambda: tmp_path)
    return share.Shares(FakeEngine())


def test_save_puts_one_mp3_in_downloads(shares, tmp_path):
    a = wait(shares.start([{"title": "My: Article?", "text": "Hello."},
                           {"title": "Two", "text": "Bye now."}], "v", 1.0))
    assert a.state == "saved" and a.file == tmp_path / "2 articles.mp3"
    assert a.file.stat().st_size > 1000 and a.status()["path"] == str(a.file)
    assert a.seconds > 2 and not list((tmp_path / "work" / "share").glob("*"))


def test_a_second_save_never_overwrites(shares, tmp_path):
    a = wait(shares.start([{"title": "My: Article?", "text": "Hello."}], "v", 1.0))
    b = wait(shares.start([{"title": "My: Article?", "text": "Hello."}], "v", 1.0))
    assert a.file.name == "My Article.mp3" and b.file.name == "My Article (2).mp3"
    shares.stop(b.id)
    assert a.file.exists() and b.file.exists()          # Done keeps the user's files


def test_limits(shares):
    with pytest.raises(share.ShareError):
        shares.start([], "v", 1.0)
    with pytest.raises(share.ShareError):
        shares.start([{"title": "x", "text": "y"}] * 4, "v", 1.0)
    with pytest.raises(share.ShareError):
        shares.start([{"title": "Empty", "text": "  "}], "v", 1.0)
