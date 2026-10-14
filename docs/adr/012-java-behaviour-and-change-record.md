# ADR 012: Java behaviour check and one change record per commit

- Status: proposed. Asked for by the owner on 2026-10-14, outside the roadmap's week plan. The same day
  the owner made COBOL at banks the MVP lead, with Java kept and maintained beside it, since bank
  systems mix the two; changes that span a Java service and a COBOL program are the next Java work.
- Date: 2026-10-14
- Related: ADR 006 (characterization), ADR 007 (equivalence), ADR 009 (Java adapter), ADR 010 (evidence pack)

## Context

Equivalence tests ran only for COBOL linkage subprograms. A Java change got impact analysis and the
policy gate, but its behaviour was never run, so the equivalence attestation said nothing about Java.

The pack also wrote four signed attestations per commit (impact, policy decision, equivalence outside
the impact set, full suite). The owner wants one record per change, with the four files kept as an
option.

## Decision

### Java behaviour check

1. **JDK only, no build tool.** The system's main Java sources (any path without a `test` folder)
   are compiled with `javac` together with one bundled probe class, `Probe.java`. Nothing is
   downloaded, so it runs offline. A tree that needs third-party jars does not compile; every class
   in scope is then listed untested with the compiler's first error.
2. **What is probed.** Public static methods, and public instance methods of public classes with a
   public no-argument constructor. After an instance call the probe also calls every other public
   instance method of the class that takes no arguments and returns a value (`count()`, `sum()`,
   getters) on the same object, so a change to state, not only to the return value, is caught. Methods whose parameter types the probe cannot
   build are listed per class with the reason; so are classes it cannot construct.
3. **Inputs.** For each parameter: the type's boundaries (0, -1, 1, MIN, MAX, null, empty, long
   strings and so on) plus the literals the method's own code compares against, and each literal's
   neighbours (49999, 50000, 50001 for `amount > 50000`). Three seed cases, then each parameter
   varied one at a time, capped at 48 cases per method.
4. **Output.** What the call returned (rendered by value, arrays element by element) or the class of
   what it threw. The same call is then made a second time, which shows state the first call left
   behind (on the object or in static fields), then each observer's value is read. The JVM runs with
   every identity hash set to 1, so an object printed as `Name@hash` reads the same on both sides. A case that runs past two seconds is a timeout.
   The code under test cannot write to the probe's output.
5. **Same or different.** Every case runs twice at the base and twice at the head, each in a fresh
   JVM from the same folder and class path. A method with any case whose two runs disagree, on
   either side, is left out entirely and listed untested ("time, randomness or identity"). Only
   methods steady on both sides are compared; a different output is a `different` test.
6. **Into the existing predicate.** Java tests are rows of the behavioral-equivalence predicate:
   the target is the class's IR entity with its `file:line`, and the outputs are digests. Scope works
   as for COBOL: outside the impact set, classes whose file holds a changed or impacted entity are left
   out. Without a JDK every Java class is listed untested and the verdict is inconclusive, never
   equivalent. No schema changed.

### One change record per commit

7. **A new predicate, `change-record` v0.1.** It holds the change and the four predicates as parts
   (`impact`, `policy_decision`, `behavioral_equivalence`, `full_suite`), each validated against its
   own schema. It is additive: no existing schema changed.
8. **Combined is the default; separate stays.** `changeproof record <commit or range> --out <folder>
   --key ...` signs one change record per commit, or with `--layout separate` the four attestations as
   before. `changeproof pack` takes the same `--layout`. A pack's report and OSCAL files are rebuilt
   from either layout and come out the same. The packs kept from Weeks 12 and 13 stay in the
   separate layout and still verify.

## Consequences

- The Java check is evidence from tests, not a proof: it covers what the probe can build and call.
  Coverage gaps are listed per class, so a partly probed change is reported as such.
- A Java system that needs dependency jars on the class path shows as untested until a class path
  option exists (**planned**).
- An assessor who prefers one file per question keeps that with `--layout separate`.

## Evidence

- `tests/test_java_behaviour.py`: targets and skip reasons; inputs from boundaries and literals; a
  refactor is all `same` and a behaviour change is caught in that class only; unstable methods are
  left out; with no JDK the verdict is inconclusive; the pack report lists Java classes inside the
  impact set; exit check: all 10 planted bugs caught, including one (`sum = amount`) that only a
  second call on the same object shows.
- `tests/test_change_record.py`: the combined record holds the four parts in one signed statement;
  the separate layout still writes four files; both layouts give the same report and OSCAL; a combined
  pack verifies offline; the `record` command writes the chosen layout.
- `docs/weekly/java-behaviour-commons-lang.json` (from `scripts/java_behaviour_check.py`): the check
  on Apache Commons Lang commits and three planted bugs.

## Commons Lang result (2026-10-14)

`scripts/java_behaviour_check.py` on the pinned Apache Commons Lang history, scoped to the files each
commit changed: 12 commits, 6,952 cases. Ten commits came out all `same`. Two commits change which
random generator the library uses (`17c3208`, "secure() now uses SecureRandom() instead of
getInstanceStrong()", and `f92016c`, LANG-1750); they show 24 and 1 differences, in the methods
that return or use that generator. The messages say behaviour changed there, so these are taken as
true differences; that the base side blocked or printed another generator is inferred, not traced.
Three bugs planted in the pinned head were all caught (67, 2 and 7 differing cases). A first run
showed 7 false differences from identity hashes and random methods; fixed by the constant identity
hash and by leaving out any method unstable on either side.
