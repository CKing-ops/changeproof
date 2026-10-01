import importlib.util
import json
from pathlib import Path

import pytest

from changeproof.config import load_config
from changeproof.graph import build_graph
from changeproof.graph.check import check_edges
from changeproof.impact import impact
from changeproof.predicates import PREDICATE_TYPES, statement, validate_predicate

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "impact"
SYSTEM = FIXTURES / "system"
EXPECTED = json.loads((FIXTURES / "expected.json").read_text())
GATE_KINDS = set(EXPECTED["gate_kinds"])
TIERS = ("definite", "probable", "possible")


@pytest.fixture(scope="module")
def graph():
    programs = sorted(p.relative_to(SYSTEM).as_posix() for p in SYSTEM.glob("src/**/*.cbl"))
    return build_graph(SYSTEM, programs, ["copy"], ["jcl/INVJOB.jcl", "jcl/AUDJOB.jcl"],
                       load_config(SYSTEM / "changeproof.yaml"), ["csd/BILLING.csd"])


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("impact_seed", FIXTURES / "seed.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    root = tmp_path_factory.mktemp("billing") / "repo"
    return root, dict(seed.seed(root))


@pytest.fixture(scope="module")
def results(repo):
    root, shas = repo
    return {name: impact(root, sha, copybook_dirs=["copy"]) for name, sha in shas.items()}


def found(predicate):
    return {i["id"]: i["confidence"] for i in predicate["impacted"]}


def test_flow_edges_name_their_paragraph(graph):
    flows = [e for e in graph.edges if e.kind == "flows-to" and e.src == "data:INVMAIN.WS-TOTAL"]
    assert {e.attributes["paragraph"] for e in flows} == {"paragraph:INVMAIN.POST-PARA"}


def test_exec_statements_use_data_items(graph):
    uses = {(e.src, e.dst, e.attributes["mode"]) for e in graph.edges if e.kind == "uses-data"}
    assert ("paragraph:INVONL.MAIN-PARA", "data:INVONL.CUST-REC", "write") in uses
    assert ("paragraph:INVONL.MAIN-PARA", "data:INVONL.CUST-REC.CUST-ID", "read") in uses
    assert ("paragraph:INVONL.MAIN-PARA", "data:INVONL.WS-AMOUNT", "read") in uses
    assert ("paragraph:CUSTUPD.MAIN-PARA", "data:CUSTUPD.CUST-REC", "read") in uses
    assert ("paragraph:INVMAIN.POST-PARA", "data:INVMAIN.WS-TOTAL", "read") in uses
    assert ("paragraph:INVRPT.SUM-PARA", "data:INVRPT.WS-TOTAL", "write") in uses


def test_new_edges_pass_the_provenance_check(graph):
    assert check_edges(graph, SYSTEM) == []


def test_exit_check_recall_on_seeded_changes(results):
    expected = [(name, node) for name, change in EXPECTED["changes"].items() for node in change["impacted"]]
    missed = [(name, node) for name, node in expected if node not in found(results[name])]
    assert len(expected) >= 100
    assert 1 - len(missed) / len(expected) >= 0.95, missed


def test_confidence_tiers_match_the_labels(results):
    wrong = {(name, node): (tier, found(results[name]).get(node))
             for name, change in EXPECTED["changes"].items() for node, tier in change["impacted"].items()
             if found(results[name]).get(node) != tier}
    assert wrong == {}


def test_nothing_outside_the_labels_is_reported_in_the_gate_kinds(results):
    extra = {name: sorted(set(found(results[name])) - set(change["impacted"]))
             for name, change in EXPECTED["changes"].items()}
    extra = {name: [node for node in nodes if node.split(":", 1)[0] in GATE_KINDS] for name, nodes in extra.items()}
    assert {name: nodes for name, nodes in extra.items() if nodes} == {}


def test_a_move_impacts_nothing(results):
    assert results["move-report-program"]["changed"] == []
    assert results["move-report-program"]["impacted"] == []


def test_crypto_flag(results):
    assert {name: p["touches_crypto"] for name, p in results.items()} == \
        {name: change["touches_crypto"] for name, change in EXPECTED["changes"].items()}


def test_every_impacted_entity_has_a_path_from_a_changed_entity(results):
    for name, predicate in results.items():
        changed = {c["id"] for c in predicate["changed"]}
        for item in predicate["impacted"]:
            via = item["via"]
            assert via[0]["from"] in changed, (name, item["id"])
            assert via[-1]["to"] == item["id"]
            assert all(a["to"] == b["from"] for a, b in zip(via, via[1:])), (name, item["id"])
            assert all(step["provenance"]["file"] and step["provenance"]["line"] >= 1 for step in via)


def test_reliant_systems_come_from_the_config_with_their_line(results):
    reliant = {(r["id"], r["via_component"], r["provenance"]["file"], r["provenance"]["line"])
               for r in results["tax-rounding"]["reliant_systems"]}
    assert reliant == {
        ("finance-reporting", "invoice-batch", "changeproof.yaml", 13),
        ("customer-portal", "customer-online", "changeproof.yaml", 18),
        ("payment-partner", "customer-online", "changeproof.yaml", 18),
    }
    assert results["audit-stamp-text"]["reliant_systems"][0]["id"] == "finance-reporting"


def test_a_call_to_a_removed_program_is_reported_unresolved(results):
    unresolved = results["retire-signing-program"]["unresolved"]
    assert any("INVSIGN" in u["description"] and u["provenance"]["file"] == "src/batch/INVMAIN.cbl"
               for u in unresolved)


def test_a_changed_input_is_probable_for_the_program_reading_it(results):
    via = next(i["via"] for i in results["report-reads-v2-file"]["impacted"] if i["id"] == "program:INVRPT")
    assert [(s["from"], s["edge"]) for s in via] == [
        ("jcl-dd:INVJOB.STEP02.INVIN", "contained-in"), ("step:INVJOB.STEP02", "runs")]


def test_predicates_validate_and_wrap_in_a_statement(results):
    for predicate in results.values():
        validate_predicate(PREDICATE_TYPES["impact"], predicate)
    head = results["tax-rounding"]["change"]["head"]
    wrapped = statement([{"name": "billing-platform", "digest": {"gitCommit": head}}], PREDICATE_TYPES["impact"],
                        results["tax-rounding"])
    assert wrapped["predicate"]["change"]["vcs"] == "git"


def test_a_range_covers_every_commit_in_it(repo):
    root, shas = repo
    predicate = impact(root, f"{shas['tax-rounding']}^..{shas['customer-tier-field']}", copybook_dirs=["copy"])
    assert predicate["change"]["base"] != predicate["change"]["head"] == shas["customer-tier-field"]
    assert {w["id"] for w in predicate["who"] if w["role"] == "author"} == \
        {"priya.raman@billing.example", "jonas.berg@billing.example"}
    assert {w["ref"] for w in predicate["why"]} == {"BILL-201", "BILL-202"}
    assert {"program:TAXCALC", "program:CUSTUPD"} <= set(found(predicate))


def test_the_first_commit_compares_with_an_empty_tree_and_lists_unanalyzed_files(repo):
    root, shas = repo
    predicate = impact(root, f"{shas['tax-rounding']}^", copybook_dirs=["copy"])
    assert {c["change"] for c in predicate["changed"]} == {"added"}
    assert "program:INVMAIN" in {c["id"] for c in predicate["changed"]}
    assert {"description": "changeproof.yaml changed but was not analyzed: no adapter for this file type",
            "provenance": {"file": "changeproof.yaml", "line": 1}} in predicate["unresolved"]
