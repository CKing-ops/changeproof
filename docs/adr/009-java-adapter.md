# ADR 009: Java adapter

- Status: proposed (Week 11). The owner's workflow merges each week once its exit check passes, so
  this stands until the owner says otherwise.
- Date: 2026-10-01
- Related: ROADMAP.md Week 11, ADR 001 (parser), ADR 002 (crypto agility), ADR 007 (equivalence)

## Context

Week 11 adds a second language so the `general` market has a mainstream adapter and DORA banks
running COBOL beside Java are covered. The roadmap's exit check is that impact runs on an
open-source Java project with no core schema change. The Week 1 spike parsed the Java sample with
tree-sitter-java at 100%.

## Decision

1. **Parser: tree-sitter with tree-sitter-java** (both MIT, `docs/licenses.md`). It is fast,
   error-tolerant and gives exact rows for every node. A file with any parse error raises
   `JavaSyntaxError` naming its first error line, so a partial tree never produces facts.
2. **IR entities** reuse the core `Entity` and `IRModule`: `class` (classes, interfaces, enums,
   records, annotation types, nested ones too), `method` (constructors are `<init>`, initializer
   blocks `<clinit>` and `<instance-init>`), `field`, `import`, `call`, `field-ref` and
   `crypto-call`. Ids hold names and parameter types, never line numbers
   (`method:com.example.pay.core.PaymentService.pay(Payment)`), so moving code is not a change.
   Calls and field uses are numbered within their method.
3. **What counts as a change.** A method's attributes carry a digest of its body tokens with
   comments removed, its modifiers and annotations as written, and its `throws` list. So a comment,
   Javadoc or member reordering changes nothing, and an added `@Deprecated` or a removed `throws`
   does. The digest goes through the signer interface (CLAUDE.md rule 6).
4. **Call resolution is by declared type, without a compiler.** The receiver's type comes from a
   local, parameter or field declaration, a class name, or the return type of the call before it.
   It is resolved through nested classes, explicit imports, the same package and wildcard imports,
   then up the project's own superclasses. Overloads are told apart by argument count; when several
   fit, each gets an edge marked `target_from: arity`, which the impact walk reports as probable.
   A call whose receiver type is unknown but whose name is a project method is kept as an
   unresolved edge, so the gap shows instead of vanishing.
5. **JCA crypto tagging.** `getInstance` and `getInstanceStrong` on JCA engine classes, `new` on
   them, and method references such as `SecureRandom::new` become `crypto-call` entities with the
   algorithm read from the string literal and the key size from `initialize` or `init` on the same
   declared variable. They feed the same `uses-crypto` edges and policy gate as COBOL.
6. **Same graph, walk and predicate.** `graph/java.py` adds Java nodes and edges through the
   existing `GraphBuilder`. The impact walk gained edge directions for `extends`, `implements` and
   `uses-field` and reads a Java edge's anchor from its scope. No core schema changed; a test pins
   the digests of the core schema files as they were before this week.
7. **Running Java is planned.** `JavaAdapter.run` raises `NotImplementedError` saying so, and
   behavioral equivalence for Java changes is **planned**.

## Consequences

- Name-based resolution misses what only a compiler knows: types inferred by `var` from a
  non-constructor call, generics and lambdas' parameter types. A bare field name is recognised
  only when the field is declared in the same file, so a use of a field inherited from a
  superclass in another file is missed, and a call on such a field is left unresolved. On Commons
  Lang 9,945 of 120,613 call edges (8.2%) stay unresolved and are reported.
- Interface calls land on the interface method; implementations are reached through the
  `implemented-by` edge to the class, not by dispatch analysis.
- A key size given by a constant or passed in from elsewhere is not read.
- The Oracle JCA standard algorithm names the tagger follows are **unverified** against the
  Oracle page (rule 6).
