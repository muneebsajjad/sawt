"""The engine keeps reading through chunks it cannot say. A lone "[" from a footnote marker once
raised inside the synthesis thread, which stopped all audio while /health still said ok."""
import time

import numpy as np
import pytest

from sawt import serve


class FakeKokoro:
    """Stands in for the model: speaks anything, except text containing "BOOM", which raises
    like Kokoro does for text with no phonemes."""
    has_timings = True

    def get_voices(self):
        return ["af_bella", "bm_fable"]

    def _audio(self, text):
        if "BOOM" in text:
            raise ValueError(f"Nothing to synthesize, {text!r} produced no phonemes")
        return np.zeros(2400, dtype="float32"), 24000

    def create(self, text, voice, speed, lang):
        return self._audio(text)

    def create_timed(self, text, voice, speed, lang):
        audio, sr = self._audio(text)
        return audio, sr, []


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(serve.models, "load", lambda: FakeKokoro())
    monkeypatch.setattr(serve.wordtime, "spoken_words", lambda timings: [])
    return serve.Engine(tmp_path / "cache", tmp_path / "pronounce.json")


def read_all(engine, text):
    s, _ = engine.start(text, "bm_fable", 1.0, 0)
    return [engine.wait_for(p["key"]) for p in s.pieces]


def test_unspeakable_and_failing_chunks_become_silence(engine):
    paths = read_all(engine, "First sentence.\n\n[\n\nThis one goes BOOM.\n\nLast sentence.")
    assert all(p is not None and p.exists() for p in paths)          # nothing hangs or is lost
    assert engine.worker.is_alive()                                  # and the engine still works
    after = read_all(engine, "A new article after the failures.")
    assert after[0] is not None and after[0].exists()


def test_speakable_text_is_recognised():
    for text in ["Hello", "42", "ß", "مرحبا", "日本"]:
        assert serve.SPEAKABLE_RE.search(text)
    for text in ["[", "—", "…", "* * *", "()", "_"]:
        assert not serve.SPEAKABLE_RE.search(text)


def test_health_reports_a_stopped_worker(engine):
    class Dead:
        def is_alive(self):
            return False
    engine.worker = Dead()
    sent = {}
    handler = serve.Handler.__new__(serve.Handler)
    handler.engine, handler.path = engine, "/health"
    handler._allowed = lambda: True
    handler._send = lambda code, body, *a: sent.update(code=code, body=body)
    handler.do_GET()
    assert sent["code"] == 503 and sent["body"]["ok"] is False and "Restart" in sent["body"]["error"]
