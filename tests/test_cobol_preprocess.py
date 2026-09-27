from pathlib import Path

import pytest

from changeproof.adapters.cobol.preprocess import CopybookLibrary, preprocess, read_fixed_format

ROOT = Path(__file__).resolve().parent / "fixtures" / "cobol"
PAYCALC = ROOT / "src" / "PAYCALC.cbl"


@pytest.fixture
def library() -> CopybookLibrary:
    return CopybookLibrary(ROOT, ["copy"])


def where(source, needle: str) -> str:
    matches = [f"{ln.file}:{ln.line}" for ln in source.lines if needle in ln.text]
    assert len(matches) == 1, (needle, matches)
    return matches[0]


def test_fixed_format_keeps_code_area_and_line_numbers():
    lines = read_fixed_format(PAYCALC, ROOT)
    assert lines[0].file == "src/PAYCALC.cbl"
    assert (lines[0].line, lines[0].text.strip()) == (1, "IDENTIFICATION DIVISION.")
    assert not any(ln.text.startswith("0000") for ln in lines)


def test_comment_and_debug_lines_are_dropped():
    texts = [ln.text for ln in read_fixed_format(PAYCALC, ROOT)]
    assert not any("SYNTHETIC TEST PROGRAM" in t or "DEBUG ONLY" in t for t in texts)


def test_continued_literal_joins_the_line_it_continues():
    lines = read_fixed_format(PAYCALC, ROOT)
    note = next(ln for ln in lines if "WS-NOTE" in ln.text)
    assert (note.line, note.end_line) == (19, 20)
    assert "'CONTINUED LITERAL THAT RUNS" in note.text and "PAST ONE LINE'." in note.text
    assert not any(ln.line == 20 for ln in lines)


def test_copybook_lines_keep_their_own_provenance(library):
    source = preprocess(PAYCALC, ROOT, library)
    assert where(source, "WS-TOTALS") == "copy/PAYWS.cpy:2"
    assert where(source, "WS-NO-ROWS") == "copy/PAYWS.cpy:5"
    assert where(source, "WS-RATE-TABLE") == "src/PAYCALC.cbl:15"


def test_copy_statement_is_recorded_and_removed(library):
    source = preprocess(PAYCALC, ROOT, library)
    payws = next(c for c in source.copies if c.name == "PAYWS")
    assert (payws.file, payws.line, payws.resolved) == ("src/PAYCALC.cbl", 14, "copy/PAYWS.cpy")
    assert not any("COPY" in ln.text.upper().split() for ln in source.lines)


def test_replacing_does_partial_words_and_multi_word_pseudo_text(library):
    source = preprocess(PAYCALC, ROOT, library)
    assert where(source, "COMPUTE") == "copy/PAYRULE.cpy:2"
    compute = next(ln.text for ln in source.lines if "COMPUTE" in ln.text)
    assert "WS-TOTAL = WS-TOTAL * WS-RATE (1)" in " ".join(compute.split())
    assert "ADD 1 TO WS-COUNT" in " ".join(next(ln.text for ln in source.lines if "ADD 1" in ln.text).split())
    rule = next(c for c in source.copies if c.name == "PAYRULE")
    assert rule.replacing == [(":PFX:", "WS"), ("BONUS-RATE", "WS-RATE (1)")]


def test_replace_statement_applies_until_replace_off(library):
    source = preprocess(ROOT / "src" / "REPLDEMO.cbl", ROOT, library)
    texts = " ".join(ln.text for ln in source.lines)
    assert "NEW-NAME" in texts and "OLD-KEPT" in texts
    assert "OLD-NAME" not in texts and "REPLACE" not in texts
    assert where(source, "NEW-NAME") == "src/REPLDEMO.cbl:6"


def test_recursive_copy_is_cut_and_reported(library):
    source = preprocess(ROOT / "src" / "REPLDEMO.cbl", ROOT, library)
    cycle = [c for c in source.copies if c.problem]
    assert [(c.name, c.problem) for c in cycle] == [("LOOPA", "recursive COPY")]
    assert where(source, "DISPLAY 'B'") == "copy/LOOPB.cpy:2"


def test_missing_copybook_is_reported_not_fatal(library):
    source = preprocess(ROOT / "src" / "NOCOPY.cbl", ROOT, library)
    (copy,) = source.copies
    assert (copy.name, copy.resolved, copy.problem) == ("NOSUCHBOOK", None, "copybook not found")


def test_exec_blocks_are_extracted_with_line_ranges_and_masked(library):
    source = preprocess(PAYCALC, ROOT, library)
    sql, cics = source.execs
    assert (sql.kind, sql.file, sql.line, sql.end_line) == ("SQL", "src/PAYCALC.cbl", 34, 37)
    assert "HASH_SHA256(EMP_NAME)" in sql.text
    assert (cics.kind, cics.line, cics.end_line) == ("CICS", 38, 38)
    assert not any("END-EXEC" in ln.text for ln in source.lines)
    continues = [f"{ln.file}:{ln.line}" for ln in source.lines if ln.text.split() == ["CONTINUE"]]
    assert continues == ["src/PAYCALC.cbl:34", "src/PAYCALC.cbl:38"]


def test_separator_commas_become_spaces_outside_literals(library):
    source = preprocess(PAYCALC, ROOT, library)
    call = next(ln.text for ln in source.lines if "WS-HASH-SVC USING" in ln.text)
    assert "," not in call
