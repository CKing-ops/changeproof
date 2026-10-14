import ast
import importlib.util
from pathlib import Path

from changeproof.frameworks import CONTROLS, NOT_MAPPED, PLANNED, REFERENCES, controls_for
from changeproof.markets import MARKETS

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "framework-mapping.md"


def render():
    spec = importlib.util.spec_from_file_location("framework_mapping", ROOT / "scripts" / "framework_mapping.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render()


def test_every_framework_a_profile_names_is_mapped_or_says_why_not():
    named = {f for p in MARKETS.values() for f in p.frameworks}
    assert {f for f in named if not controls_for(f) and f not in NOT_MAPPED} == set()
    assert {c.framework for c in CONTROLS} <= named
    assert set(NOT_MAPPED) <= named


def test_every_control_links_its_source():
    sources = [c.source for c in CONTROLS] + [source for _, _, source in REFERENCES]
    assert all(s.url.startswith("https://") and s.title for s in sources)


def test_every_proof_is_a_test_that_exists_or_is_planned():
    missing = []
    for control in CONTROLS:
        for evidence in control.evidence:
            if evidence.proof == PLANNED:
                continue
            path, name = evidence.proof.split("::")
            functions = {n.name for n in ast.walk(ast.parse((ROOT / path).read_text())) if isinstance(n, ast.FunctionDef)}
            if name not in functions:
                missing.append(evidence.proof)
    assert missing == []


def test_the_mapping_document_is_generated_from_the_data():
    assert DOC.read_text() == render()


def test_the_document_leads_with_general_then_eu_dora_then_us_defense():
    text = render()
    positions = [text.index(f"## `{name}`") for name in ("general", "eu-dora", "us-defense")]
    assert positions == sorted(positions)


def test_unchecked_controls_are_labelled_unverified():
    rows = [line for line in render().splitlines() if line.startswith("| ") and "](https://" in line]
    assert rows
    assert all(("unverified" in row) != ("checked " in row) for row in rows)


def test_the_sources_read_on_2026_10_07_are_checked_and_the_rest_stay_unverified():
    by_title = {c.source.title: c.source for c in CONTROLS} | {s.title: s for _, _, s in REFERENCES}
    checked = {t for t, s in by_title.items() if s.checked == "2026-10-07"}
    assert {t for t in checked if "800-53" in t} and {t for t in checked if "800-218" in t}
    assert {t for t in checked if "2016/679" in t}
    unverified = {t for t, s in by_title.items() if s.checked is None}
    assert {t for t in unverified if "2022/2554" in t} and {t for t in unverified if "AICPA" in t}
    assert {t for t in unverified if "ISO/IEC 27001" in t}


def test_cnsa2_is_checked_in_the_nsa_faq_and_swft_says_what_its_memo_page_does_not_give():
    cnsa2 = next(c.source for c in CONTROLS if c.framework == "cnsa2")
    assert cnsa2.checked == "2026-10-14" and cnsa2.url.startswith("https://media.defense.gov/")
    assert "dodcio.defense.gov" in NOT_MAPPED["swft"] and "press" in NOT_MAPPED["swft"]


def test_dora_says_where_its_wording_was_read_while_eur_lex_stays_unchecked():
    dora = next(c.source for c in CONTROLS if c.framework == "dora")
    assert dora.checked is None and "springlex.eu" in dora.note and "OJ L 333" in dora.note
    assert "springlex.eu" in next(row for row in render().splitlines() if row.startswith("| Art. 9(4)(e)"))


def test_the_week13_controls_are_mapped_from_their_checked_text():
    ids = {(c.framework, c.id) for c in CONTROLS}
    assert {("nist-800-53-cm", "CM-3(2)"), ("nist-ssdf", "PS.2.1"), ("nist-ssdf", "PS.3.1"),
            ("nist-ssdf", "PW.8.2")} <= ids
    assert ("nist-ssdf", "SP 800-218") not in ids
