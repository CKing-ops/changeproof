"""Week 12: the evidence pack's PDF, written by the engine itself so the same evidence gives the same bytes."""

import io

from pypdf import PdfReader

from changeproof.pack.pdf import LINE_CHARS, render

BLOCKS = [("title", "Evidence pack v1.4"), ("heading", "Change 1 of 2"),
          ("text", "Approved by dana.okafor@billing.example (git-commit/ab12:8)."),
          ("code", "src/batch/FEECALC.cbl:31  LK-FEE  modified")]


def text_of(data: bytes) -> list[str]:
    return [page.extract_text() for page in PdfReader(io.BytesIO(data)).pages]


def test_a_reader_gets_back_the_text_on_numbered_pages():
    pages = text_of(render(BLOCKS, "Evidence pack v1.4"))
    assert len(pages) == 1
    for _, line in BLOCKS:
        assert line in pages[0]
    assert "page 1 of 1" in pages[0]


def test_the_same_blocks_give_the_same_bytes():
    assert render(BLOCKS, "t") == render(BLOCKS, "t")
    assert render(BLOCKS, "t") != render(BLOCKS + [("text", "one more line")], "t")


def test_long_text_wraps_at_word_boundaries_and_runs_onto_new_pages():
    words = " ".join(f"word{n}" for n in range(4000))
    pages = text_of(render([("text", words)], "t"))
    assert len(pages) > 3
    assert "page 2 of" in pages[1]
    joined = " ".join(" ".join(p.split("\n")[:-1]) for p in pages)
    assert "word0 word1" in joined and "word3999" in joined


def test_brackets_backslashes_and_characters_outside_latin_1_survive_or_show_as_question_marks():
    pages = text_of(render([("text", r"(a) \b [c] Grüße → done")], "t"))
    assert r"(a) \b [c] Grüße ? done" in pages[0]


def test_a_line_never_runs_past_the_margin():
    assert all(len(line) <= LINE_CHARS["text"] for line in text_of(render([("text", "x" * 500)], "t"))[0].split("\n"))
