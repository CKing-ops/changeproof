"""Week 2 exit check: 20 facts drawn from real CardDemo programs by scripts/sample_facts.py,
each checked by hand against its source line (docs/weekly/WEEK-02.md). This keeps them true."""

import json
from pathlib import Path

import pytest

from changeproof.adapters.cobol import CobolAdapter

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "carddemo"
GOLDEN = json.loads((ROOT / "tests" / "fixtures" / "exit_check" / "week02_facts.json").read_text())
COPYBOOK_DIRS = [
    "app/cpy", "app/cpy-bms",
    "app/app-transaction-type-db2/cpy", "app/app-transaction-type-db2/cpy-bms", "app/app-transaction-type-db2/dcl",
]
PROGRAMS = {"CBACT01C": "app/cbl/CBACT01C.cbl", "COSGN00C": "app/cbl/COSGN00C.cbl",
            "COTRTUPC": "app/app-transaction-type-db2/cbl/COTRTUPC.cbl"}


@pytest.fixture(scope="module")
def facts() -> dict:
    adapter = CobolAdapter(COPYBOOK_DIRS)
    return {e.id: e for path in PROGRAMS.values() for e in adapter.parse(CORPUS / path, CORPUS).entities}


def test_sample_has_twenty_facts_of_every_kind_found():
    assert len(GOLDEN) == 20
    assert {f["kind"] for f in GOLDEN} >= {"program", "paragraph", "data", "condition", "file", "copybook",
                                           "call", "exec-sql", "exec-cics"}


@pytest.mark.parametrize("fact", GOLDEN, ids=[f["id"] for f in GOLDEN])
def test_hand_checked_fact_keeps_its_provenance(facts, fact):
    assert str(facts[fact["id"]].provenance) == fact["provenance"]
