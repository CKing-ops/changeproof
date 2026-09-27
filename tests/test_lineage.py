from pathlib import Path

import pytest

from changeproof.graph import build_graph
from changeproof.graph.check import check_edges
from changeproof.graph.lineage import downstream, upstream

ROOT = Path(__file__).resolve().parent / "fixtures" / "graph"


@pytest.fixture(scope="module")
def graph():
    return build_graph(ROOT, programs=["src/FLOWS.cbl", "src/SUBPGM.cbl"], copybook_dirs=["copy"])


def flows(graph):
    return sorted((e.src, e.dst, str(e.provenance)) for e in graph.edges if e.kind == "flows-to" and e.resolved)


def test_flow_facts_become_field_to_field_edges(graph):
    assert flows(graph) == [
        ("data:FLOWS.WS-LINE", "data:FLOWS.RPT-REC", "src/FLOWS.cbl:34"),
        ("data:FLOWS.WS-RATE", "data:FLOWS.WS-TXN.WS-FEE", "src/FLOWS.cbl:28-29"),
        ("data:FLOWS.WS-TOTALS.WS-NET", "data:FLOWS.WS-LINE", "src/FLOWS.cbl:33"),
        ("data:FLOWS.WS-TXN.WS-AMOUNT", "data:FLOWS.WS-TOTALS.WS-AMOUNT", "src/FLOWS.cbl:30"),
        ("data:FLOWS.WS-TXN.WS-AMOUNT", "data:FLOWS.WS-TOTALS.WS-NET", "src/FLOWS.cbl:31-32"),
        ("data:FLOWS.WS-TXN.WS-AMOUNT", "data:FLOWS.WS-TXN.WS-FEE", "src/FLOWS.cbl:28-29"),
        ("data:FLOWS.WS-TXN.WS-FEE", "data:FLOWS.WS-TOTALS.WS-NET", "src/FLOWS.cbl:31-32"),
        ("file:FLOWS.TXN-IN", "data:FLOWS.WS-TXN", "src/FLOWS.cbl:27"),
    ]


def test_an_ambiguous_field_name_is_unresolved_with_its_reason(graph):
    [edge] = [e for e in graph.unresolved if e.kind == "flows-to"]
    assert (edge.src, edge.dst, edge.attributes["reason"], str(edge.provenance)) == (
        "unresolved:data:WS-AMOUNT", "data:FLOWS.WS-LINE", "ambiguous: 2 data items have this name", "src/FLOWS.cbl:37")


def test_a_dynamic_call_resolves_through_a_moved_literal(graph):
    [call] = [e for e in graph.edges if e.kind == "calls" and e.src == "paragraph:FLOWS.MAIN-PARA"]
    assert (call.dst, call.resolved, str(call.provenance)) == ("program:SUBPGM", True, "src/FLOWS.cbl:36")
    assert call.attributes["target_from"] == "flow:FLOWS.MAIN-PARA.WS-TARGET-PGM#1"


def test_upstream_lineage_walks_back_to_the_input_file(graph):
    found = upstream(graph, "data:FLOWS.RPT-REC")
    assert set(found) >= {"data:FLOWS.WS-LINE", "data:FLOWS.WS-TOTALS.WS-NET", "data:FLOWS.WS-TXN.WS-FEE",
                          "data:FLOWS.WS-RATE", "data:FLOWS.WS-TXN.WS-AMOUNT", "file:FLOWS.TXN-IN"}
    assert "data:FLOWS.WS-TOTALS.WS-AMOUNT" not in found
    assert str(found["file:FLOWS.TXN-IN"].provenance) == "src/FLOWS.cbl:27"


def test_downstream_lineage_follows_a_group_move_into_its_fields(graph):
    found = downstream(graph, "file:FLOWS.TXN-IN")
    assert {"data:FLOWS.WS-TXN", "data:FLOWS.WS-TXN.WS-FEE", "data:FLOWS.WS-TOTALS.WS-NET",
            "data:FLOWS.RPT-REC"} <= set(found)


def test_new_edges_pass_the_provenance_check(graph):
    assert check_edges(graph, ROOT) == []
