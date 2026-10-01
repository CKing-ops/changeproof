# A change must not add cryptography that Shor's algorithm breaks (RSA, ECC, DSA, DH), or change the
# algorithm or key size of such a use. Unchanged uses are left to the crypto inventory (Week 16).
package changeproof.rules.no_new_quantum_vulnerable_crypto

import rego.v1

deny contains finding if {
	some c in input.crypto
	c.quantum_vulnerable == true
	not unchanged(c)
	finding := {
		"message": sprintf("%s adds %s, which a large quantum computer can break", [c.service, label(c)]),
		"provenance": c.provenance,
	}
}

warn contains finding if {
	some c in input.crypto
	c.quantum_vulnerable == null
	finding := {
		"message": sprintf("%s uses public-key cryptography whose algorithm could not be read from the program", [c.service]),
		"provenance": c.provenance,
	}
}

unchanged(c) if {
	c.previous.quantum_vulnerable == true
	c.previous.algorithm == c.algorithm
	c.previous.key_bits == c.key_bits
}

label(c) := sprintf("%s-%d", [c.algorithm, c.key_bits]) if c.key_bits != null

label(c) := c.algorithm if c.key_bits == null
