# ADR 010: Evidence pack, MCP server and AI attribution

- Status: proposed (Week 12). The owner's workflow merges each week once its exit check passes, so
  this stands until the owner says otherwise.
- Date: 2026-10-01
- Related: ROADMAP.md Week 12 (and Week 13, where an assessor reviews packs), ADR 002 (crypto
  agility), ADR 005 (policy gate and OSCAL), ADR 007 (equivalence)

## Context

An assessor needs one bundle per release that they can check without our help, without the
customer's repository and without a network. AI agents now write and review code, so the evidence
must say when one took part, and agents should be able to ask the engine for evidence directly.

## Decision

1. **The pack is attestations first.** `changeproof pack <range>` signs three attestations per
   commit: impact, policy decision and behavioral equivalence. The PDF report and one OSCAL
   assessment-results file per commit are then built from those attestations only. A signed pack
   statement (`pack.dsse.json`, predicate `evidence-pack` v0.1) lists every attestation by payload
   digest, states the crypto profile and the algorithms that signed the pack, and carries the
   digest of every file as a subject.
2. **A new policy-decision predicate (v0.1)** holds the facts the rules saw, each rule's outcome,
   the OPA version, the frameworks in scope and the time of evaluation. OSCAL used to be built from
   the live gate run; it is now built from the impact and policy-decision predicates, so the same
   document comes from the attestations alone. The existing predicate schemas are unchanged; the
   two new ones are added beside them.
3. **`changeproof pack-verify`** verifies every signature under the given trust policy, checks each
   attestation's payload against the pack statement, rebuilds the report and OSCAL files, and
   compares each with its signed digest. It can write the rebuilt files out, so a pack that ships
   only its attestations is enough.
4. **The PDF is written by the engine** (`pack/pdf.py`, PDF 1.4, standard Courier font, no dates
   or random IDs). A PDF library would add a dependency and, in most cases, timestamps that break
   byte-for-byte rebuilds. Text outside Latin-1 prints as `?` in the PDF; the attestations keep it.
5. **The report joins the two halves of each change**: what it touches (impact) beside whether
   behaviour outside that set stayed the same (equivalence), and it checks and says that the
   equivalence attestation names that impact attestation by digest.
6. **AI attribution comes from the commit only.** An agent is named by an `Assisted-by`,
   `Generated-by` or `AI-agent` trailer, or as a `Co-authored-by` at an address in
   `AGENT_ADDRESSES` (`change/message.py`; the owner adds the agents the team uses). It appears in
   the impact predicate's `who` with role `agent`, which v0.1 already allowed, and in the policy
   input with the trailer's line. A new rule, `agent-changes-need-independent-approval`, fails a
   change an agent took part in when no approver other than the implementer is recorded. The
   engine never guesses that code was AI-written from the code itself.
7. **The MCP server is hand-written JSON-RPC over stdio** (`changeproof mcp`), with four read-only
   tools: `impact`, `lineage`, `equivalence_status` and `crypto_inventory`. The reference MCP SDK
   was not used, because it pulls in network clients (which the Week 14 bundle must not contain)
   and a dependency licensed MPL-2.0. The protocol versions offered are the ones the reference
   Python SDK 1.30.0 lists as supported, read from the installed package.
8. **The crypto inventory tool** returns the existing crypto-inventory predicate from the crypto
   calls the COBOL and Java adapters find. Migration categories and deadlines are left null, and
   the CycloneDX CBOM is not produced; both are **planned** for Week 16.

## Consequences

- A rebuild must use an engine whose report and OSCAL code are the same as the one that built the
  pack. The pack statement records the engine version; a later engine that changes the report
  layout will fail an older pack's byte comparison. The attestations themselves still verify.
- The MCP server has been tested with a scripted client, not with a third-party MCP client.
- Agents are found only when a commit names them. An agent that commits under a person's name with
  no trailer is not detected.
