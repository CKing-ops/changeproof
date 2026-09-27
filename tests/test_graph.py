from pathlib import Path

import pytest

from changeproof.config import load_config
from changeproof.graph import build_graph, load_graph, save_graph
from changeproof.graph.build import sql_tables
from changeproof.graph.check import check_edges

ROOT = Path(__file__).resolve().parent / "fixtures" / "graph"


@pytest.fixture(scope="module")
def graph():
    return build_graph(ROOT, programs=["src/BATCH1.cbl", "src/SUBPGM.cbl"], copybook_dirs=["copy"],
                       jcl=["jcl/RUNBATCH.jcl"], csd=["csd/TESTGRP.csd"], config=load_config(ROOT / "changeproof.yaml"))


def edge(graph, src, dst, kind):
    found = [e for e in graph.edges if (e.src, e.dst, e.kind) == (src, dst, kind)]
    assert len(found) == 1, (src, dst, kind, found)
    return found[0]


def test_every_edge_has_provenance(graph):
    assert graph.edges
    assert all(e.provenance.file and e.provenance.line >= 1 for e in graph.edges)


def test_every_edge_endpoint_is_a_node(graph):
    ids = {n.id for n in graph.nodes}
    assert all(e.src in ids and e.dst in ids for e in graph.edges)


def test_perform_edges_include_thru_ranges(graph):
    thru = edge(graph, "paragraph:BATCH1.MAIN-PARA", "paragraph:BATCH1.OPEN-PARA", "performs")
    assert (str(thru.provenance), thru.attributes["thru"]) == ("src/BATCH1.cbl:20", "paragraph:BATCH1.OPEN-EXIT")
    assert str(edge(graph, "paragraph:BATCH1.MAIN-PARA", "paragraph:BATCH1.END-PARA", "goes-to").provenance) == \
        "src/BATCH1.cbl:25"


def test_calls_resolve_through_value_clauses_and_cics(graph):
    call = edge(graph, "paragraph:BATCH1.MAIN-PARA", "program:SUBPGM", "calls")
    assert (str(call.provenance), call.attributes["via"]) == ("src/BATCH1.cbl:22", "call")
    xctl = edge(graph, "paragraph:SUBPGM.MAIN-PARA", "program:BATCH1", "calls")
    assert (str(xctl.provenance), xctl.attributes["via"]) == ("src/SUBPGM.cbl:10", "cics-xctl")


def test_copybook_file_and_table_edges(graph):
    inc = edge(graph, "program:BATCH1", "copybook:ACCTWS", "includes")
    assert str(inc.provenance) == "src/BATCH1.cbl:15"
    assert str(edge(graph, "program:BATCH1", "file:BATCH1.ACCT-IN", "declares").provenance) == "src/BATCH1.cbl:6"
    reads = [e.dst for e in graph.edges if e.kind == "reads-table"]
    assert sorted(reads) == ["table:ACCOUNTS", "table:CUSTOMERS"]
    writes = edge(graph, "paragraph:BATCH1.READ-PARA", "table:ACCOUNTS", "writes-table")
    assert str(writes.provenance) == "src/BATCH1.cbl:36-38"
    cics = edge(graph, "paragraph:SUBPGM.MAIN-PARA", "cics-file:ACCTDAT", "cics-file")
    assert (str(cics.provenance), cics.attributes["command"]) == ("src/SUBPGM.cbl:11-12", "READ")


def test_crypto_calls_link_to_the_service(graph):
    crypto = edge(graph, "paragraph:SUBPGM.MAIN-PARA", "crypto-service:CSNBOWH", "uses-crypto")
    assert (str(crypto.provenance), crypto.attributes["category"]) == ("src/SUBPGM.cbl:13", "hash")


def test_jcl_edges_bind_program_files_to_datasets(graph):
    assert str(edge(graph, "job:RUNBATCH", "step:RUNBATCH.STEP01", "contains").provenance) == "jcl/RUNBATCH.jcl:4"
    assert str(edge(graph, "step:RUNBATCH.STEP01", "program:BATCH1", "runs").provenance) == "jcl/RUNBATCH.jcl:4"
    dd = edge(graph, "step:RUNBATCH.STEP01", "dataset:TEST.ACCT.DATA", "dd")
    assert (str(dd.provenance), dd.attributes["ddname"]) == ("jcl/RUNBATCH.jcl:5-6", "ACCTIN")
    bind = edge(graph, "file:BATCH1.ACCT-IN", "dataset:TEST.ACCT.DATA", "binds")
    assert (str(bind.provenance), bind.attributes["step"]) == ("jcl/RUNBATCH.jcl:5-6", "step:RUNBATCH.STEP01")


def test_cics_definitions_link_transactions_screens_and_datasets(graph):
    assert str(edge(graph, "transaction:TB01", "program:SUBPGM", "starts").provenance) == "csd/TESTGRP.csd:3-4"
    back = edge(graph, "paragraph:SUBPGM.MAIN-PARA", "transaction:TB01", "starts-transaction")
    assert (str(back.provenance), back.attributes["command"]) == ("src/SUBPGM.cbl:15", "RETURN")
    screen = edge(graph, "paragraph:SUBPGM.MAIN-PARA", "mapset:SUBMAP", "uses-screen")
    assert (str(screen.provenance), screen.attributes["map"]) == ("src/SUBPGM.cbl:14", "SUBSCR")
    assert str(edge(graph, "cics-file:ACCTDAT", "dataset:TEST.ACCT.DATA", "cics-dataset").provenance) == \
        "csd/TESTGRP.csd:1-2"


def test_edges_between_components_are_marked(graph):
    assert edge(graph, "transaction:TB01", "program:SUBPGM", "starts").attributes["crosses"] == \
        ["online-cics", "batch-core"]
    assert edge(graph, "step:RUNBATCH.STEP01", "program:BATCH1", "runs").attributes["crosses"] == \
        ["batch-schedule", "batch-core"]
    assert "crosses" not in edge(graph, "program:BATCH1", "paragraph:BATCH1.MAIN-PARA", "contains").attributes


def test_resources_used_by_several_components_are_marked(graph):
    nodes = {n.id: n for n in graph.nodes}
    assert nodes["dataset:TEST.ACCT.DATA"].attributes["shared_by"] == ["batch-core", "batch-schedule"]
    assert "shared_by" not in nodes["table:ACCOUNTS"].attributes


def test_unresolved_edges_are_reported_with_a_reason(graph):
    found = sorted((e.dst, e.attributes["reason"], str(e.provenance)) for e in graph.unresolved)
    assert found == [
        ("unresolved:dynamic:WS-ANY-PGM", "dynamic target with no VALUE", "src/BATCH1.cbl:23"),
        ("unresolved:paragraph:MISSING-PARA", "no such paragraph or section", "src/BATCH1.cbl:39"),
        ("unresolved:proc:NIGHTLY", "procedure not in the analyzed code", "jcl/RUNBATCH.jcl:13"),
        ("unresolved:program:IEFBR14", "program not in the analyzed code", "jcl/RUNBATCH.jcl:12"),
        ("unresolved:program:NOSUCHPG", "program not in the analyzed code", "src/BATCH1.cbl:24"),
    ]
    assert all(not e.resolved for e in graph.unresolved)


def test_component_config_is_on_program_nodes(graph):
    node = next(n for n in graph.nodes if n.id == "program:BATCH1")
    assert node.attributes["component"] == {
        "id": "batch-core", "criticality": "high", "data_stores": ["ACCOUNTS"], "relied_on_by": ["sepa-gateway"],
    }


def test_networkx_view_matches_the_edge_list(graph):
    g = graph.to_networkx()
    assert g.number_of_edges() == len(graph.edges)
    assert g.nodes["program:BATCH1"]["kind"] == "program"


def test_sqlite_round_trip(graph, tmp_path):
    path = tmp_path / "graph.sqlite"
    save_graph(graph, path)
    loaded = load_graph(path)
    assert sorted(loaded.nodes, key=lambda n: n.id) == sorted(graph.nodes, key=lambda n: n.id)
    assert sorted(loaded.edges, key=lambda e: e.key) == sorted(graph.edges, key=lambda e: e.key)


def test_every_edge_points_at_the_statement_it_came_from(graph):
    assert check_edges(graph, ROOT) == []


def test_edge_check_catches_a_wrong_line(graph):
    bad = graph.edges[0].model_copy(update={"provenance": graph.edges[0].provenance.model_copy(update={"line": 1, "end_line": None})})
    wrong = graph.model_copy(update={"edges": [bad]})
    assert len(check_edges(wrong, ROOT)) == 1


@pytest.mark.parametrize(("sql", "expected"), [
    ("SELECT A INTO :X FROM T1 WHERE B = 1", [("T1", "reads")]),
    ("SELECT A FROM S.T1 X, S.T2 Y WHERE X.K = Y.K", [("S.T1", "reads"), ("S.T2", "reads")]),
    ("SELECT A FROM T1 JOIN T2 ON T1.K = T2.K", [("T1", "reads"), ("T2", "reads")]),
    ("INSERT INTO T1 (A, B) VALUES (:A, :B)", [("T1", "writes")]),
    ("UPDATE T1 SET A = 1", [("T1", "writes")]),
    ("DELETE FROM T1 WHERE A = 1", [("T1", "writes")]),
    ("DECLARE C1 CURSOR FOR SELECT A FROM T1", [("T1", "reads")]),
    ("FETCH C1 INTO :A, :B", []),
    ("SELECT A FROM (SELECT B FROM T1) Z", [("T1", "reads")]),
])
def test_sql_table_references(sql, expected):
    assert sql_tables(sql) == expected
