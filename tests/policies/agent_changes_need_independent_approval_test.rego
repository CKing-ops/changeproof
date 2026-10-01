package changeproof.rules.agent_changes_need_independent_approval_test

import data.changeproof.rules.agent_changes_need_independent_approval as rule
import rego.v1

agent := {"id": "bot@x", "provenance": {"file": "git-commit/abc", "line": 4}}

test_a_change_with_no_agent_needs_nothing if {
	count(rule.deny) == 0 with input as {"agents": [], "implementers": [{"id": "a@x"}], "approvers": []}
}

test_an_independent_approver_clears_an_agent_change if {
	count(rule.deny) == 0 with input as {"agents": [agent], "implementers": [{"id": "a@x"}], "approvers": [{"id": "b@x"}]}
}

test_self_approval_does_not_clear_an_agent_change if {
	found := rule.deny with input as {"agents": [agent], "implementers": [{"id": "a@x"}], "approvers": [{"id": "a@x"}]}
	found == {{"message": "bot@x took part in this change and no independent approver is recorded",
		"provenance": agent.provenance}}
}
