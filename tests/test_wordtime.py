"""Matching the model's spoken words back to the words on the page. No voice model needed."""
from kokoro_onnx.sliding import Timing

from sawt.wordtime import align, page_words, spoken_words


def timed(phonemes, step=0.1):
    """Fake per-phoneme timings: every phoneme lasts `step` seconds."""
    return [Timing(p, i * step, (i + 1) * step) for i, p in enumerate(phonemes)]


def test_spoken_words_group_phonemes_between_spaces():
    words = spoken_words(timed("ab cd, e."))
    assert [(round(a, 2), round(b, 2)) for a, b in words] == [(0.0, 0.2), (0.3, 0.5), (0.7, 0.8)]


def test_page_words_trim_punctuation():
    s = "Dr. Smith's “well-known” plan."
    assert [s[a:b] for a, b in page_words(s)] == ["Dr", "Smith's", "well-known", "plan"]


def test_words_spoken_as_written_get_their_own_span():
    sentence = "Critics called it myopic."
    got = align(sentence, sentence, [(0, 1), (1, 2), (2, 3), (3, 4)])
    assert [(sentence[a:b], t0, t1) for a, b, t0, t1 in got] == [
        ("Critics", 0, 1), ("called", 1, 2), ("it", 2, 3), ("myopic", 3, 4)]


def test_a_number_spoken_as_several_words_shares_their_span():
    sentence = "He spent $5m today."
    spoken = "He spent five million dollars today."
    got = align(sentence, spoken, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6)])
    assert [(sentence[a:b], t0, t1) for a, b, t0, t1 in got] == [
        ("He", 0, 1), ("spent", 1, 2), ("5m", 2, 5), ("today", 5, 6)]


def test_word_count_mismatch_spreads_time_instead_of_failing():
    sentence = "one two three"
    got = align(sentence, sentence, [(0.0, 3.0)])       # the phonemizer saw one word
    assert [sentence[a:b] for a, b, *_ in got] == ["one", "two", "three"]
    assert got[0][2] == 0.0 and got[-1][3] == 3.0
    assert all(t0 < t1 for *_, t0, t1 in got)


def test_second_chunk_of_a_long_sentence_matches_its_own_words():
    sentence = "First half of it, and the second half here."
    got = align(sentence, "and the second half here.", [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)])
    assert [sentence[a:b] for a, b, *_ in got] == ["and", "the", "second", "half", "here"]
