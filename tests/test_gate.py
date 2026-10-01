"""Week 7: the policy gate (OPA/Rego rules named in `policy:`) and its OSCAL assessment-results export."""

import importlib.util
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

from changeproof.gate import POLICY_DIR, gate, known_rules, opa_path
from changeproof.oscal import assessment_results, validate_oscal

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

_spec = importlib.util.spec_from_file_location("gate_seed", FIXTURES / "gate" / "seed.py")
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("gate") / "repo"
    return root, dict(_seed.seed(root))


@pytest.fixture(scope="module")
def results(repo):
    root, shas = repo
    return {name: gate(root, sha) for name, sha in shas.items()}


def outcome(result, rule):
    return next(r for r in result.decision["rules"] if r["rule"] == rule)


def test_opa_is_found():
    assert opa_path() is not None


def test_rego_policy_unit_tests_pass():
    proc = subprocess.run([opa_path(), "test", str(POLICY_DIR), str(Path(__file__).parent / "policies"), "-v"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_every_rule_is_a_rego_package():
    assert known_rules() == {"no-new-quantum-vulnerable-crypto": "rego", "high-criticality-needs-two-approvers": "rego",
                             "equivalence-required-outside-impact-set": "rego",
                             "agent-changes-need-independent-approval": "rego"}


def test_exit_check_policy_blocks_a_pr_that_adds_rsa_2048(results, repo):
    result = results["add-rsa-2048-key"]
    assert result.decision["ok"] is False
    rule = outcome(result, "no-new-quantum-vulnerable-crypto")
    assert rule["status"] == "fail"
    assert rule["deny"] == [{"message": "CSNDPKB adds rsa-2048, which a large quantum computer can break",
                             "provenance": {"file": "src/batch/KEYGEN.cbl", "line": 14, "end_line": 15}}]


def test_a_pr_that_adds_sha_384_passes_the_crypto_rule(results):
    assert outcome(results["add-sha-384-digest"], "no-new-quantum-vulnerable-crypto")["status"] == "pass"
    assert results["add-sha-384-digest"].decision["ok"] is True


def test_changing_an_rsa_key_size_is_new_quantum_vulnerable_crypto(results):
    rule = outcome(results["grow-rsa-key"], "no-new-quantum-vulnerable-crypto")
    assert rule["status"] == "fail"
    assert rule["deny"][0]["message"] == "CSNDPKB adds rsa-3072, which a large quantum computer can break"


def test_a_public_key_call_with_no_readable_algorithm_warns_but_passes(results):
    rule = outcome(results["unreadable-public-key-call"], "no-new-quantum-vulnerable-crypto")
    assert rule["status"] == "pass"
    assert rule["warn"][0]["message"].startswith("CSNDPKE uses public-key cryptography whose algorithm")
    assert rule["warn"][0]["provenance"]["line"] == 16


def test_a_high_criticality_change_needs_two_independent_approvers(results):
    rule = outcome(results["one-approver-on-high"], "high-criticality-needs-two-approvers")
    assert rule["status"] == "fail"
    assert rule["deny"] == [{"message": "invoice-batch is high criticality and has 1 independent approver; 2 are needed",
                             "provenance": {"file": "changeproof.yaml", "line": 8}}]
    assert outcome(results["add-sha-384-digest"], "high-criticality-needs-two-approvers")["status"] == "pass"


def test_the_equivalence_rule_warns_about_each_program_it_cannot_test(results):
    rule = outcome(results["add-sha-384-digest"], "equivalence-required-outside-impact-set")
    assert (rule["status"], rule["deny"]) == ("inconclusive", [])
    assert results["add-sha-384-digest"].decision["ok"] is True
    assert rule["warn"] and all("has no equivalence tests" in w["message"] for w in rule["warn"])
    assert all(w["provenance"]["file"].startswith("src/") for w in rule["warn"])
    assert results["add-sha-384-digest"].input["equivalence"]["verdict"] == "inconclusive"


def test_without_gnucobol_the_equivalence_rule_is_not_evaluated(repo, monkeypatch):
    root, shas = repo
    monkeypatch.setenv("CHANGEPROOF_COBC", "/nonexistent/cobc")
    rule = outcome(gate(root, shas["add-sha-384-digest"]), "equivalence-required-outside-impact-set")
    assert rule["status"] == "not-evaluated"
    assert "cobc was not found" in rule["reason"]


def test_every_policy_input_fact_carries_provenance(results):
    facts = results["add-rsa-2048-key"].input
    for item in facts["crypto"] + facts["components"]:
        assert item["provenance"]["file"] and item["provenance"]["line"] >= 1
    for person in facts["approvers"] + facts["implementers"]:
        assert person["source"]


def test_the_decision_records_the_opa_version(results):
    assert results["add-rsa-2048-key"].decision["opa"].startswith("1.")


def test_nist_example_validates_and_a_broken_one_does_not():
    example = json.loads((FIXTURES / "oscal" / "nist-ifa-assessment-results-example.json").read_text())
    validate_oscal(example)
    del example["assessment-results"]["metadata"]["title"]
    with pytest.raises(jsonschema.ValidationError):
        validate_oscal(example)


def test_exit_check_oscal_assessment_results_validate(results):
    for result in results.values():
        validate_oscal(assessment_results(result, NOW))


def test_oscal_records_policy_findings_and_cited_evidence(results):
    doc = assessment_results(results["add-rsa-2048-key"], NOW)["assessment-results"]
    result = doc["results"][0]
    states = {f["target"]["target-id"]: f["target"]["status"]["state"] for f in result["findings"]}
    assert states == {"no-new-quantum-vulnerable-crypto": "not-satisfied",
                      "high-criticality-needs-two-approvers": "satisfied",
                      "equivalence-required-outside-impact-set": "not-satisfied"}
    observed = {o["uuid"]: o for o in result["observations"]}
    crypto = next(f for f in result["findings"] if f["target"]["target-id"] == "no-new-quantum-vulnerable-crypto")
    cited = [observed[r["observation-uuid"]] for r in crypto["related-observations"]]
    assert {"name": "provenance", "ns": "urn:changeproof:oscal", "value": "src/batch/KEYGEN.cbl:14-15"} in \
        cited[0]["props"]
    assert "soc2_CC8.1" in [c["control-id"] for c in
                            result["reviewed-controls"]["control-selections"][0]["include-controls"]]
    assert doc["metadata"]["oscal-version"] == "1.1.2"


def test_oscal_output_is_reproducible(results):
    assert assessment_results(results["add-rsa-2048-key"], NOW) == assessment_results(results["add-rsa-2048-key"], NOW)


def test_a_missing_opa_is_reported_plainly(repo, monkeypatch):
    root, shas = repo
    monkeypatch.setenv("CHANGEPROOF_OPA", "/nonexistent/opa")
    with pytest.raises(FileNotFoundError, match="OPA"):
        gate(root, shas["add-sha-384-digest"])
