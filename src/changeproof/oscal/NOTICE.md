# oscal_complete_schema-1.1.2.json

NIST OSCAL 1.1.2 "complete" JSON Schema (`$id` http://csrc.nist.gov/ns/oscal/1.0/1.1.2/schema.json),
a work of the US government (NIST), in the public domain with a CC0 1.0 waiver
(https://github.com/usnistgov/OSCAL/blob/main/LICENSE.md).

Taken from the `oscal` npm package 2.0.7 (MIT, published by GSA), file `src/schema/oscal.complete.ts`,
with the TypeScript `export const oscalSchema=` wrapper removed. The JSON content is unchanged.
NIST publishes the same schema as a release asset of usnistgov/OSCAL v1.1.2. That page could not be
reached from the build machine, so this copy is **not yet compared byte for byte with NIST's asset**.
It does validate NIST's own assessment-results example
(`tests/test_gate.py::test_nist_example_validates_and_a_broken_one_does_not`).

SHA-384 prefix of this file: `4b903c0254680df7844e40f18f6224e1`.
