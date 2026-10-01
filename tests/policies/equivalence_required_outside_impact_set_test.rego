package changeproof.rules.equivalence_required_outside_impact_set_test

import data.changeproof.rules.equivalence_required_outside_impact_set as rule
import rego.v1

where := {"file": "src/batch/RISKSCR.cbl", "line": 1}

test_equivalent_code_passes if {
	count(rule.deny) == 0 with input as {"equivalence": {"verdict": "equivalent", "differing": [], "errors": [], "untested": []}}
	count(rule.warn) == 0 with input as {"equivalence": {"verdict": "equivalent", "differing": [], "errors": [], "untested": []}}
}

test_a_behaviour_change_outside_the_impact_set_is_denied if {
	found := rule.deny with input as {"equivalence": {"verdict": "not-equivalent", "errors": [], "untested": [],
		"differing": [{"program": "RISKSCR", "test": "RISKSCR-03", "provenance": where}]}}
	found == {{"message": "RISKSCR behaves differently after the change (test RISKSCR-03), but the change does not touch it", "provenance": where}}
}

test_untested_programs_and_errors_warn if {
	found := rule.warn with input as {"equivalence": {"verdict": "inconclusive", "differing": [],
		"errors": [{"program": "INTCALC", "test": "INTCALC-01", "provenance": where}],
		"untested": [{"program": "PKDCALC", "reason": "COMP-3 items are not supported", "provenance": where}]}}
	count(found) == 2
}

test_a_file_that_does_not_parse_warns_by_its_path if {
	found := rule.warn with input as {"equivalence": {"verdict": "inconclusive", "differing": [], "errors": [],
		"untested": [{"reason": "does not parse at the head", "provenance": where}]}}
	found == {{"message": "src/batch/RISKSCR.cbl has no equivalence tests: does not parse at the head", "provenance": where}}
}

test_no_evidence_means_no_finding if {
	count(rule.deny) == 0 with input as {}
}
