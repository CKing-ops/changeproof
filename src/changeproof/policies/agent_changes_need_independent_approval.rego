# A change an AI agent took part in needs an approver who did not implement it.
package changeproof.rules.agent_changes_need_independent_approval

import rego.v1

deny contains finding if {
	some agent in input.agents
	count(independent) == 0
	finding := {
		"message": sprintf("%s took part in this change and no independent approver is recorded", [agent.id]),
		"provenance": agent.provenance,
	}
}

independent contains person.id if {
	some person in input.approvers
	not person.id in {i.id | some i in input.implementers}
}
