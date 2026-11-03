"""PDF text for the reader: paragraphs rebuilt from lines, page furniture and clutter left out."""
import pytest

from sawt import pdftext

BODY = "This is a long line of body text that runs the full width of the column and keeps going"


def test_short_line_ending_a_sentence_ends_its_paragraph():
    pages = [[BODY, BODY, "and ends here.", BODY, "and so does this one."]]
    assert pdftext.paragraphs(pages) == [f"{BODY} {BODY} and ends here.",
                                         f"{BODY} and so does this one."]


def test_headings_stand_alone():
    pages = [["1. Introduction", BODY, "the end."]]
    assert pdftext.paragraphs(pages)[0] == "1. Introduction"


def test_running_headers_and_page_numbers_are_dropped():
    pages = [["A Journal of Things", BODY, "first page ends.", str(n)] for n in range(1, 6)]
    text = " ".join(pdftext.paragraphs(pages))
    assert "Journal" not in text and " 3" not in text


def test_hyphenation_is_undone_only_for_real_words():
    pages = [["the sequence transduc-", "tion models and the English-", "to-German task ends."]]
    assert pdftext.paragraphs(pages) == ["the sequence transduction models and the "
                                         "English-to-German task ends."]


def test_paper_front_matter_starts_at_the_abstract():
    paras = ["Attention Is All You Need", "Ashish Vaswani", "avaswani@google.com",
             "Abstract", "The dominant models are recurrent."]
    title, body = pdftext._front_matter(paras)
    assert title == "Attention Is All You Need"
    assert body == ["The dominant models are recurrent."]


def test_abstract_on_the_same_line_as_an_email():
    title, body = pdftext._front_matter(["A Title Here", "me@x.org www.x.org Abstract. It works."])
    assert body == ["It works."]


def test_fragments_tables_and_code_are_dropped():
    paras = ["1 Introduction", "Real prose that says something useful to the listener today.",
             "1 Method", "2 Results", "Input-Input Layer5", "Self-Attention O(n2 · d) O(1) O(1)",
             "Model 27.3 38.1 3.3 1018 41.0 2.3 19.1", "double p = exp(-l); sum -= p; } return s;"]
    assert pdftext._drop_fragments(paras) == [
        "1 Introduction", "Real prose that says something useful to the listener today.",
        "1 Method", "2 Results"]


def test_reference_list_is_cut():
    paras = ["Intro", "Text."] * 3 + ["References", "[1] A. Author. A paper. 2017."]
    assert pdftext._without_references(paras) == ["Intro", "Text."] * 3


def test_not_a_pdf():
    with pytest.raises(pdftext.NoText):
        pdftext.read(b"not a pdf at all")
