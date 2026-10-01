"""Week 11: impact for Java changes through the same graph, walk and predicate as COBOL."""

import importlib.util
import json
from pathlib import Path

import pytest

from changeproof.gate import gate
from changeproof.graph.check import check_edges
from changeproof.impact import impact
from changeproof.impact.run import system_graph
from changeproof.config import load_config
from changeproof.predicates import PREDICATE_TYPES, validate_predicate
from changeproof.signer import digest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "java"
SYSTEM = FIXTURES / "system"
EXPECTED = {k: v for k, v in json.loads((FIXTURES / "expected.json").read_text()).items() if not k.startswith("_")}

_spec = importlib.util.spec_from_file_location("java_seed", FIXTURES / "seed.py")
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("java") / "repo"
    return root, dict(_seed.seed(root))


@pytest.fixture(scope="module")
def results(repo):
    root, shas = repo
    return {name: impact(root, sha) for name, sha in shas.items()}


@pytest.fixture(scope="module")
def graph():
    return system_graph(SYSTEM, [], load_config(SYSTEM / "changeproof.yaml"))


def test_the_java_graph_resolves_calls_fields_and_inheritance(graph):
    found, failed = graph
    assert failed == {}
    edges = {(e.src, e.kind, e.dst) for e in found.edges}
    pay = "method:com.example.pay.core.PaymentService.pay(Payment)"
    assert (pay, "calls", "method:com.example.pay.core.FeeCalculator.fee(long)") in edges
    assert (pay, "calls", "method:com.example.pay.core.Ledger.post(long)") in edges
    assert (pay, "calls", "method:com.example.pay.crypto.ReceiptSigner.sign(String)") in edges
    assert (pay, "calls", "method:com.example.pay.core.Payment.amount()") in edges
    assert ("method:com.example.pay.core.RecurringPaymentService.payMonthly(Payment)", "calls", pay) in edges
    assert ("class:com.example.pay.core.RecurringPaymentService", "extends",
            "class:com.example.pay.core.PaymentService") in edges
    assert ("method:com.example.pay.core.FeeCalculator.fee(long)", "uses-field",
            "field:com.example.pay.core.FeeCalculator.RATE_BASIS_POINTS") in edges
    assert ("method:com.example.pay.crypto.ReceiptSigner.sign(String)", "uses-crypto",
            "crypto-service:java.security.Signature") in edges
    nodes = {n.id: n for n in found.nodes}
    assert nodes["class:com.example.pay.core.FeeCalculator"].attributes["component"]["criticality"] == "high"


def test_every_java_edge_passes_the_provenance_check(graph):
    assert check_edges(graph[0], SYSTEM) == []


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_exit_check_seeded_java_changes_match_the_hand_marked_impact(results, name):
    predicate, expected = results[name], EXPECTED[name]
    assert set(expected["changed"]) <= {c["id"] for c in predicate["changed"]}
    assert {i["id"] for i in predicate["impacted"]} == set(expected["impacted"])
    assert predicate["touches_crypto"] is expected["crypto"]
    validate_predicate(PREDICATE_TYPES["impact"], predicate)


def test_impact_paths_cite_java_lines(results):
    found = {i["id"]: i for i in results["fee-rate"]["impacted"]}
    path = found["method:com.example.pay.core.RecurringPaymentService.payMonthly(Payment)"]["via"]
    assert [step["edge"] for step in path] == ["used-by", "called-by", "called-by"]
    assert path[-1]["provenance"]["file"].endswith("RecurringPaymentService.java")


def test_the_gate_blocks_rsa_added_in_java(repo):
    root, shas = repo
    rule = next(r for r in gate(root, shas["rsa-receipts"]).decision["rules"]
                if r["rule"] == "no-new-quantum-vulnerable-crypto")
    assert rule["status"] == "fail"
    assert [d["message"] for d in rule["deny"]] == [
        "java.security.KeyPairGenerator adds rsa-2048, which a large quantum computer can break",
        "java.security.Signature adds rsa, which a large quantum computer can break"]
    assert gate(root, shas["fee-rate"]).decision["ok"] is True


# SHA-384 prefixes of the core schemas as merged at the end of Week 10 (main at fe3f33d)
CORE = {
    "src/changeproof/adapters/base.py": "438633a0766653294ec0b634261d3af9",
    "src/changeproof/graph/model.py": "bc1504d092c0f39a2859d252e2d56316",
    "src/changeproof/predicates/schemas/behavioral-equivalence-v0.1.json": "6824e6142a3d65e96d2e9b73db47c997",
    "src/changeproof/predicates/schemas/common-v0.1.json": "04ccd30ad586a0618e44f18d64491db2",
    "src/changeproof/predicates/schemas/crypto-inventory-v0.1.json": "b7ae3031a75eefe2d5d3dcd451e49ab0",
    "src/changeproof/predicates/schemas/impact-v0.1.json": "ebdd8fcf2a5ab447d83b58edad804c54",
    "src/changeproof/predicates/schemas/release-v0.1.json": "7754b6a4f7b95201f2f957b01b7a66f7",
    "src/changeproof/provenance.py": "d55c1ef3de4a9db82cab0348ffd6295e",
    "src/changeproof/schema/changeproof.schema.json": "679dcdf27971bd149d03dd13b85cc0e5",
}


def test_exit_check_the_java_adapter_needed_no_core_schema_change():
    root = Path(__file__).resolve().parent.parent
    assert {path: digest((root / path).read_bytes())["sha-384"][:32] for path in CORE} == CORE
