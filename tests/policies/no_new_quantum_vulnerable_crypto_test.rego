package changeproof.rules.no_new_quantum_vulnerable_crypto_test

import data.changeproof.rules.no_new_quantum_vulnerable_crypto as rule
import rego.v1

where := {"file": "src/A.cbl", "line": 3}

rsa(previous) := {"service": "CSNDPKB", "algorithm": "rsa", "key_bits": 2048, "quantum_vulnerable": true,
	"change": "added", "previous": previous, "provenance": where}

test_new_rsa_is_denied if {
	count(rule.deny) == 1 with input as {"crypto": [rsa(null)]}
}

test_unchanged_rsa_is_allowed if {
	count(rule.deny) == 0 with input as {"crypto": [rsa({"algorithm": "rsa", "key_bits": 2048, "quantum_vulnerable": true})]}
}

test_hash_is_allowed if {
	count(rule.deny) == 0 with input as {"crypto": [{"service": "CSNBOWH", "algorithm": "sha-384", "key_bits": null,
		"quantum_vulnerable": false, "change": "added", "previous": null, "provenance": where}]}
}

test_unknown_public_key_warns if {
	count(rule.warn) == 1 with input as {"crypto": [{"service": "CSNDPKE", "algorithm": null, "key_bits": null,
		"quantum_vulnerable": null, "change": "added", "previous": null, "provenance": where}]}
}
