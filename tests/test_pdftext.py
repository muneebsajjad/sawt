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


def test_author_block_is_skipped_without_an_abstract():
    paras = ["Attention Is All You Need", "Ashish Vaswani∗", "Google Brain",
             "avaswani@google.com", "Noam Shazeer, Niki Parmar", "Department of Computer Science",
             "University of Toronto", "1 Introduction", "Recurrent models came first."]
    title, body = pdftext._front_matter(paras)
    assert title == "Attention Is All You Need"
    assert body == ["1 Introduction", "Recurrent models came first."]


def test_a_title_followed_by_one_heading_is_not_a_byline():
    paras = ["The Long Walk Home", "Chapter One", "It was raining."]
    assert pdftext._front_matter(paras) == (None, paras)


def test_a_title_that_runs_onto_the_next_line():
    title, _ = pdftext._front_matter(["BERT: Pre-training of Deep Bidirectional Transformers for",
                                      "Language Understanding", "Jacob Devlin Ming-Wei Chang",
                                      "Google AI Language", "Abstract", "We introduce BERT."])
    assert title == "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding"


def test_small_capitals_are_rejoined():
    assert pdftext._unsmallcap("LORA: L OW-R ANK ADAPTATION") == "LORA: LOW-RANK ADAPTATION"
    assert pdftext._unsmallcap("1 I NTRODUCTION") == "1 INTRODUCTION"
    assert pdftext._unsmallcap("A SIMPLE BASELINE") == "A SIMPLE BASELINE"


@pytest.mark.parametrize("p", [
    "31st Conference on Neural Information Processing Systems (NIPS 2017), Long Beach, CA, USA.",
    "Provided proper attribution is provided, Google hereby grants permission to reproduce.",
    "arXiv:1706.03762v7 [cs.CL] 2 Aug 2023", "Published as a conference paper at ICLR 2022",
    "∗Equal contribution. Listing order is random.", "Author contributions listed at end of paper.",
    "Work done while at Google Brain.", "Figure 1: The Transformer - model architecture.",
    "Table 2: Results on the test set.", "Contents",
    "2.1 Model and Architectures . . . . . . . . . . . 8",
    "1All code and hyperparameters available at http://www.github.com/x"])
def test_clutter_is_left_out(p):
    assert pdftext._is_clutter(p)


@pytest.mark.parametrize("p", [
    "1 Introduction", "Figures of speech are everywhere in the text that follows here.",
    "Published work in this area is scarce, and we set out to change that.",
    "The table shows that the model wins on every task we tried."])
def test_prose_is_kept(p):
    assert not pdftext._is_clutter(p)


def test_table_of_contents_is_cut_but_a_heading_ending_in_a_number_is_kept():
    paras = ["Contents", "1 Introduction 3", "2 Approach 6", "3 Results 10", "1 Introduction",
             "Text.", "4.2 Convergence of Algorithm 1", "More text."]
    paras = pdftext._without_contents([p for p in paras if not pdftext._is_clutter(p)])
    assert paras == ["1 Introduction", "Text.", "4.2 Convergence of Algorithm 1", "More text."]


def test_running_headers_that_carry_the_page_number_are_dropped():
    # the header text changes with the section, the number goes up with the page
    heads = ["1.3. The first program 3", "4 Chapter 1. The way of the program",
             "1.5. Values and types 5", "6 Chapter 1. The way of the program",
             "2.1. Assignment statements 7", "8 Chapter 2. Variables"]
    pages = [[h, BODY, "the page ends here."] for h in heads]
    text = " ".join(pdftext.paragraphs(pages))
    assert "Chapter" not in text and "first program" not in text


def test_a_sentence_that_mentions_a_figure_is_not_a_caption():
    assert not pdftext._is_clutter("Figure 2.1 shows the four methods using the example.")
    assert not pdftext._is_clutter("Table 2.2 shows the final mixture of datasets we used.")
    assert pdftext._is_clutter("Figure 1.2: Larger models make better use of context.")
    assert pdftext._is_clutter("Figure 3. Distributed version control diagram")


def test_a_short_caption_does_not_swallow_the_paragraph_after_it():
    pages = [["Figure 1. Local version control diagram", BODY, "and that is the point."]]
    paras = pdftext.paragraphs(pages)
    assert paras[0] == "Figure 1. Local version control diagram"
    assert paras[1].endswith("and that is the point.")


def test_numbered_code_lines_are_not_headings():
    assert not pdftext._is_heading("3 lock(&mutex);")
    assert not pdftext._is_heading("4 balance = balance + 1;")
    assert pdftext._is_heading("3 Model Architecture")


def test_a_sentence_wrapping_onto_a_line_that_starts_with_table_is_kept():
    pages = [[BODY, "Results on selected GLUE tasks are shown in",
              "Table 6. In this table, we report the average accuracy.", BODY, "and so on."]]
    text = " ".join(pdftext.paragraphs(pages))
    assert "shown in Table 6. In this table, we report the average accuracy." in text
