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
