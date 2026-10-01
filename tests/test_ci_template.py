"""Week 7: the pull-request CI job template runs the gate offline and keeps its OSCAL output."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "ci" / "changeproof-gate.yml"


def steps():
    return yaml.safe_load(TEMPLATE.read_text())["jobs"]["gate"]["steps"]


def step(name):
    return next(s for s in steps() if s.get("name") == name)


def test_the_gate_runs_on_pull_requests_with_full_history():
    doc = yaml.safe_load(TEMPLATE.read_text())
    assert "pull_request" in doc[True]
    assert steps()[0]["with"]["fetch-depth"] == 0


def test_the_gate_step_has_no_network_and_writes_oscal():
    run = step("Policy gate (no network)")["run"]
    assert run.startswith("sudo unshare --net --")
    assert "changeproof gate" in run and "--oscal oscal-assessment-results.json" in run
    assert step("Keep the OSCAL assessment results")["if"] == "always()"


def test_installs_come_before_any_offline_step_and_the_release_is_verified():
    names = [s.get("name") for s in steps()]
    assert names.index("Install changeproof and OPA (network allowed)") < names.index("Policy gate (no network)")
    assert "changeproof verify" in step("Check the changeproof release signature (offline)")["run"]


def test_the_template_pins_the_same_opa_as_ci():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "opa@v1.21.1" in ci and "opa@v1.21.1" in TEMPLATE.read_text()
