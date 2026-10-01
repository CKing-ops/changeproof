package changeproof.rules.high_criticality_needs_two_approvers_test

import data.changeproof.rules.high_criticality_needs_two_approvers as rule
import rego.v1

high := {"id": "pay", "criticality": "high", "changed": true, "provenance": {"file": "changeproof.yaml", "line": 8}}

test_two_independent_approvers_pass if {
	count(rule.deny) == 0 with input as {"components": [high], "implementers": [{"id": "a@x"}],
		"approvers": [{"id": "b@x"}, {"id": "c@x"}]}
}

test_an_implementer_does_not_count_as_an_approver if {
	count(rule.deny) == 1 with input as {"components": [high], "implementers": [{"id": "a@x"}],
		"approvers": [{"id": "a@x"}, {"id": "c@x"}]}
}

test_unchanged_or_lower_components_need_nothing if {
	count(rule.deny) == 0 with input as {"components": [object.union(high, {"changed": false}),
		object.union(high, {"criticality": "medium"})], "implementers": [], "approvers": []}
}
