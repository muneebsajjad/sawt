"""The text path every chunk of speech goes through. None of this needs the voice model."""
import pytest

from sawt.serve import split_sentences
from sawt.synth import apply_dict, chunk, chunk_key
from sawt.textnorm import normalize


@pytest.mark.parametrize("text, spoken", [
    ("By 1847 he had spent $5m, roughly 12.5%",
     "By eighteen forty-seven he had spent five million dollars, roughly twelve point five percent"),
    ("the 21st time", "the twenty-first time"),
    ("the 1920s", "the nineteen twenties"),
    ("pp. 3-7", "pages three to seven"),
    ("Chapter XIV", "Chapter fourteen"),
    ("Part II", "Part two"),
])
def test_normalize(text, spoken):
    assert normalize(text) == spoken


@pytest.mark.xfail(reason="'Ch.' is only expanded lowercase, and numerals are converted before "
                          "abbreviations - see the good-first-issue in CONTRIBUTING.md",
                   strict=True)
def test_normalize_abbreviated_chapter():
    assert normalize("Ch. XIV") == "chapter fourteen"


def test_split_sentences_keeps_abbreviations_together():
    assert split_sentences("Dr. Smith arrived. He sat down! Was it late? Yes.") == [
        "Dr. Smith arrived.", "He sat down!", "Was it late?", "Yes."]


def test_chunk_keeps_short_text_whole():
    assert chunk("One. Two. Three.", 220) == [{"text": "One. Two. Three.", "para_end": True}]


def test_chunk_respects_the_limit():
    text = " ".join(f"Sentence number {i} is here." for i in range(40))
    pieces = chunk(text, 120)
    assert len(pieces) > 1
    assert all(len(p["text"]) <= 120 for p in pieces)
    assert " ".join(p["text"] for p in pieces) == text


def test_chunk_key_covers_voice_and_speed():
    # the cache is only correct if changing either one changes the key
    base = chunk_key("hello", "af_bella", 0.85)
    assert base == chunk_key("hello", "af_bella", 0.85)
    assert base != chunk_key("hello", "af_bella", 1.0)
    assert base != chunk_key("hello", "am_adam", 0.85)


def test_pronunciation_dictionary_replaces_whole_words():
    assert apply_dict("Gregor met Samsa", {"Gregor": "Gregg or"}) == "Gregg or met Samsa"
