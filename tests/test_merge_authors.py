"""Who wrote a merged change, and which identities are bots or AI (the 2026-10-14 approvals test on GitLab
Runner: mergers were taken as implementers, and an AI reviewer counted as a person)."""

import importlib.util
from pathlib import Path

import pytest

from changeproof.change.record import change_record
from changeproof.gate import gate
from changeproof.impact import impact

_spec = importlib.util.spec_from_file_location("merge_seed", Path(__file__).parent / "fixtures" / "merges" / "seed.py")
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("merges") / "repo"
    return root, _seed.seed(root)


def test_on_a_merge_commit_the_implementers_are_the_merged_authors_and_the_merger_is_kept_apart(repo):
    root, shas = repo
    who = change_record(root, shas["human"]).who
    assert [p.name for p in who.implementers] == ["Priya Raman"]
    assert str(who.implementers[0].provenance) == f"git-commit/{shas['fee']}:3"
    assert who.merged_by.name == "Dana Okafor"
    assert who.independent is True
    assert "an approver is also the implementer" not in change_record(root, shas["human"]).open_items()


def test_an_ai_reviewer_is_an_agent_not_a_person(repo):
    root, shas = repo
    who = change_record(root, shas["human"]).who
    assert [p.email for p in who.reviewers] == []
    assert [p.email for p in who.agents] == ["gitlab-duo@gitlab.com"]


def test_a_bot_author_is_an_agent_and_an_approver_who_also_pushed_is_named(repo):
    root, shas = repo
    record = change_record(root, shas["bot"])
    assert [p.name for p in record.who.implementers] == ["Billing Renovate Bot", "Lena Vogel"]
    assert [p.email for p in record.who.agents] == ["billing-bot@deps.example"]
    assert record.who.independent is True
    assert "an approver also implemented the change; another approver did not" in record.open_items()


def test_the_impact_attestation_and_the_gate_read_the_merged_authors(repo):
    root, shas = repo
    who = impact(root, shas["human"])["who"]
    assert {(w["role"], w["id"]) for w in who} >= {("author", "priya.raman@billing.example"),
                                                   ("committer", "dana.okafor@billing.example"),
                                                   ("approver", "dana.okafor@billing.example"),
                                                   ("agent", "gitlab-duo@gitlab.com")}
    assert ("author", "dana.okafor@billing.example") not in {(w["role"], w["id"]) for w in who}
    result = gate(root, shas["bot"])
    rule = next(r for r in result.decision["rules"] if r["rule"] == "agent-changes-need-independent-approval")
    assert rule["status"] == "pass"
    assert {a["id"] for a in result.input["agents"]} == {"billing-bot@deps.example"}
