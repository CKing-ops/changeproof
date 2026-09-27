from pathlib import Path

import pytest

from changeproof.adapters.cobol import CobolAdapter

ROOT = Path(__file__).resolve().parent / "fixtures" / "graph"


@pytest.fixture(scope="module")
def flows():
    module = CobolAdapter(["copy"]).parse(ROOT / "src" / "FLOWS.cbl", ROOT)
    return [e for e in module.entities if e.kind == "flow"]


def test_each_data_flow_statement_becomes_a_flow_fact(flows):
    found = [(e.name, e.attributes.get("sources"), e.attributes["targets"], str(e.provenance)) for e in flows]
    assert found == [
        ("READ", [], ["WS-TXN"], "src/FLOWS.cbl:27"),
        ("COMPUTE", ["WS-AMOUNT OF WS-TXN", "WS-RATE"], ["WS-FEE OF WS-TXN"], "src/FLOWS.cbl:28-29"),
        ("ADD", ["WS-AMOUNT OF WS-TXN"], ["WS-AMOUNT OF WS-TOTALS"], "src/FLOWS.cbl:30"),
        ("SUBTRACT", ["WS-FEE", "WS-AMOUNT OF WS-TXN"], ["WS-NET"], "src/FLOWS.cbl:31-32"),
        ("MOVE", ["WS-NET"], ["WS-LINE"], "src/FLOWS.cbl:33"),
        ("WRITE", ["WS-LINE"], ["RPT-REC"], "src/FLOWS.cbl:34"),
        ("MOVE", [], ["WS-TARGET-PGM"], "src/FLOWS.cbl:35"),
        ("MOVE", ["WS-AMOUNT"], ["WS-LINE"], "src/FLOWS.cbl:37"),
    ]


def test_flow_facts_keep_file_literal_and_paragraph(flows):
    read, move_literal = flows[0], flows[6]
    assert read.attributes["file"] == "TXN-IN"
    assert move_literal.attributes["literal"] == "SUBPGM"
    assert all(e.attributes["paragraph"] == "paragraph:FLOWS.MAIN-PARA" for e in flows)


def test_flow_ids_are_named_by_target_not_line(flows):
    assert [e.id for e in flows[4:]] == [
        "flow:FLOWS.MAIN-PARA.WS-LINE#1",
        "flow:FLOWS.MAIN-PARA.RPT-REC#1",
        "flow:FLOWS.MAIN-PARA.WS-TARGET-PGM#1",
        "flow:FLOWS.MAIN-PARA.WS-LINE#2",
    ]


def test_flow_text_ignores_line_layout(flows):
    assert flows[1].attributes["text"] == "COMPUTE WS-FEE OF WS-TXN = WS-AMOUNT OF WS-TXN * WS-RATE"
