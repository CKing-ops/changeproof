# Code outside a change's impact set must behave as it did before the change.
package changeproof.rules.equivalence_required_outside_impact_set

import rego.v1

deny contains finding if {
	some d in input.equivalence.differing
	finding := {
		"message": sprintf("%s behaves differently after the change (test %s), but the change does not touch it", [d.program, d.test]),
		"provenance": d.provenance,
	}
}

warn contains finding if {
	some u in input.equivalence.untested
	finding := {"message": sprintf("%s has no equivalence tests: %s", [object.get(u, "program", u.provenance.file), u.reason]), "provenance": u.provenance}
}

warn contains finding if {
	some e in input.equivalence.errors
	finding := {"message": sprintf("%s test %s could not run after the change", [e.program, e.test]), "provenance": e.provenance}
}
