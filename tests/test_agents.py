"""Week 12: AI agents named in a commit are recorded beside the people, and a rule can ask for a human approver."""

import importlib.util
from pathlib import Path

import pytest

from changeproof.change.record import change_records
from changeproof.gate import gate
from changeproof.impact import impact

_spec = importlib.util.spec_from_file_location("pack_seed", Path(__file__).parent / "fixtures" / "pack" / "seed.py")
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)

RULE = "agent-changes-need-independent-approval"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("agents") / "repo"
    return root, _seed.seed(root)


def test_the_change_record_names_the_agent_from_its_trailer(repo):
    root, shas = repo
    record = change_records(root, shas["assisted"])[0]
    [agent] = record.who.agents
    assert (agent.name, agent.email) == ("FeeBot Assistant 2.1", "feebot@tools.example")
    assert str(agent.provenance) == f"git-commit/{shas['assisted']}:8"
    assert record.who.implementer.name == "Priya Raman"


def test_a_co_author_counts_as_an_agent_only_by_a_known_agent_address(repo):
    root, shas = repo
    assert [a.email for a in change_records(root, shas["co-authored"])[0].who.agents] == ["noreply@anthropic.com"]
    assert change_records(root, shas["base"])[0].who.agents == []


def test_the_impact_attestation_lists_the_agent_with_where_it_was_read(repo):
    root, shas = repo
    agents = [w for w in impact(root, shas["assisted"])["who"] if w["role"] == "agent"]
    assert agents == [{"role": "agent", "id": "feebot@tools.example",
                       "source": f"Assisted-by trailer, git-commit/{shas['assisted']}:8"}]
    assert not [w for w in impact(root, shas["base"])["who"] if w["role"] == "agent"]


def test_an_agent_change_needs_an_approver_who_did_not_implement_it(repo):
    root, shas = repo
    rules = {name: next(r for r in gate(root, shas[name]).decision["rules"] if r["rule"] == RULE)
             for name in ("assisted", "co-authored")}
    assert rules["assisted"]["status"] == "pass"
    assert rules["co-authored"]["status"] == "fail"
    assert rules["co-authored"]["deny"] == [{
        "message": "noreply@anthropic.com took part in this change and no independent approver is recorded",
        "provenance": {"file": f"git-commit/{shas['co-authored']}", "line": 8}}]
