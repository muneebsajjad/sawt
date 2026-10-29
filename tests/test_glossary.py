"""Finding the hard words in an article and their meanings. Uses a tiny glossary, no download."""
import json
import sqlite3

import pytest

from sawt.glossary import Glossary, best_long_form, defined_on_page, hard_words


@pytest.fixture
def gl(tmp_path):
    db = sqlite3.connect(tmp_path / "g.sqlite")
    db.executescript("""
        CREATE TABLE words(word TEXT PRIMARY KEY, senses TEXT NOT NULL);
        CREATE TABLE forms(form TEXT PRIMARY KEY, word TEXT NOT NULL);
    """)
    words = {
        "myopic": [["adj.", "Near-sighted.", ""], ["adj.", "Shortsighted; improvident.",
                                                   "figuratively"]],
        "heuristic": [["n.", "A heuristic method.", ""]],
        "Kubernetes": [["name", "An open-source orchestrator of containers.", ""]],
        "Paris": [["name", "The capital of France.", ""]],
        "LLM": [["n.", "Initialism of large language model.", ""]],
        "house": [["n.", "A building people live in.", ""]],
    }
    db.executemany("INSERT INTO words VALUES (?, ?)",
                   [(w, json.dumps(s)) for w, s in words.items()])
    db.execute("INSERT INTO forms VALUES ('heuristics', 'heuristic')")
    db.commit()
    db.close()
    return Glossary(tmp_path / "g.sqlite")


def found(sentences, gl, text=""):
    return {w["word"]: w for w in hard_words(sentences, gl, text or " ".join(sentences))}


def test_rare_words_get_their_meanings(gl):
    got = found(["The plan was myopic.", "They lived in a house."], gl)
    assert list(got) == ["myopic"]                   # "house" is far too common to explain
    assert got["myopic"]["sentence"] == 0
    assert got["myopic"]["senses"][1] == ["adj.", "Shortsighted; improvident.", "figuratively"]


def test_inflections_find_their_headword(gl):
    assert found(["Simple heuristics work."], gl)["heuristics"]["senses"] == [
        ["n.", "A heuristic method.", ""]]


def test_each_word_is_explained_once(gl):
    got = hard_words(["Myopic, they said.", "A myopic plan."], gl)
    assert [(w["word"], w["sentence"]) for w in got] == [("Myopic", 0)]


def test_everyday_names_are_skipped_but_rare_ones_explained(gl):
    got = found(["They moved from Paris to Kubernetes."], gl)
    assert "Paris" not in got
    assert "Kubernetes" in got


def test_plural_acronym_finds_the_singular(gl):
    assert found(["Most LLMs are large."], gl)["LLMs"]["senses"][0][1].startswith("Initialism")


def test_acronym_defined_on_the_page_beats_the_dictionary(gl):
    text = ("Keep it under the maximum allowable operating pressure (MAOP). "
            "Raising the MAOP needs approval.")
    got = found(["Keep it under the maximum allowable operating pressure (MAOP).",
                 "Raising the MAOP needs approval."], gl, text)
    assert got["MAOP"]["source"] == "page"
    assert got["MAOP"]["senses"] == [["abbr.", "maximum allowable operating pressure", ""]]
    assert got["MAOP"]["sentence"] == 0


def test_page_acronyms_work_without_a_glossary():
    text = "The National Transportation Safety Board (NTSB) said so."
    assert [w["word"] for w in hard_words([text], None, text)] == ["NTSB"]


@pytest.mark.parametrize("text, expected", [
    ("the World Health Organization (WHO) said", {"WHO": "World Health Organization"}),
    ("a large language model (LLM) wrote it", {"LLM": "large language model"}),
    ("as noted before (see Fig. 2) and (In) or (A)", {}),
    ("prices rose (USD) sharply", {}),             # nothing before it spells U-S-D
])
def test_defined_on_page(text, expected):
    assert defined_on_page(text) == expected


def test_long_form_needs_the_first_letter_to_start_a_word():
    assert best_long_form("HO", "the shoe organiser") is None      # every h is mid-word
    assert best_long_form("HO", "a health organisation") == "health organisation"
