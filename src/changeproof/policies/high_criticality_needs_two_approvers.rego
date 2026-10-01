# A change to a high-criticality component needs two approvers who did not implement it.
package changeproof.rules.high_criticality_needs_two_approvers

import rego.v1

deny contains finding if {
	some component in input.components
	component.criticality == "high"
	component.changed
	n := count(independent)
	n < 2
	finding := {
		"message": sprintf("%s is high criticality and has %d independent %s; 2 are needed", [component.id, n, noun(n)]),
		"provenance": component.provenance,
	}
}

independent contains person.id if {
	some person in input.approvers
	not person.id in {i.id | some i in input.implementers}
}

noun(1) := "approver"

noun(n) := "approvers" if n != 1
