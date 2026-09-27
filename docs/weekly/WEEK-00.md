# Week 0: validate DORA as the first market (no code)

- Market: `eu-dora` first (owner decision, 2026-09-27)
- Branch: `week-00-dora`
- Date: 2026-09-27
- Status: **kit ready, conversations not started.** Week 0 is interviews, and the owner runs
  them. The exit check cannot be run until the tracker is filled.

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| Conversations held | 12 (4 bank ICT risk/change, 3 auditors, 3 COBOL engineers, 2 DORA-review veterans) | 0 of 12 | `docs/week-00/tracker.csv` |
| Name change-impact or PQC evidence as a gap | ≥ 4 of 12 | not run | tracker `names_gap`, `pqc_gap` |
| Auditor interest | ≥ 1 | not run | tracker `auditor_interest` |
| Funding or entry route identified | 1-2 | 2 candidates, not yet checked for fit | below |

Kill gate: fewer than 4 of 12 name the gap, or no auditor interest → re-scope before Week 5
(fallback `general` or `us-defense`).

## What is in the kit

- `docs/week-00/interview-guide.md`: who to talk to, ten questions tied to the DORA articles,
  a variant for auditors, and how to score each call.
- `docs/week-00/tracker.csv`: one row per planned conversation with the scoring columns.
- `docs/week-00/outreach.md`: a short first message (draft, not sent).

## Regulatory hooks the questions rely on

Checked against the published texts on 2026-09-27:

- **DORA ICT risk management RTS, Delegated Regulation (EU) 2024/1774.** Art. 16 requires testing
  and approval of ICT systems before use and after maintenance, and source code review with static
  and dynamic testing. Art. 17 (ICT change management) requires verification that ICT security
  requirements were met, independence between approving and implementing a change, and
  documentation of each change's purpose, scope, timeline and expected outcomes, plus fall-back
  procedures. Source: [EUR-Lex, OJ L 2024/1774](https://eur-lex.europa.eu/eli/reg_del/2024/1774/oj/eng).
- **EU PQC roadmap** (NIS Cooperation Group, published 23 June 2025): Member States start the
  transition by the end of 2026, and critical infrastructure should be on PQC no later than the
  end of 2030. Source: [European Commission](https://digital-strategy.ec.europa.eu/en/news/eu-reinforces-its-cybersecurity-post-quantum-cryptography).

What changeproof would answer is Art. 17(1)(a) and (d) and the Art. 16 testing evidence at code
depth. That it does so is **planned** (Weeks 4, 5 and 9); nothing is proven yet.

## Funding and entry routes (EU equivalents of SBIR/DIU)

Dates from a third-party calendar dated 27 August 2026; confirm on the EU Funding & Tenders
portal before planning around them.

1. **EIC Accelerator**, `HORIZON-EIC-2026-ACCELERATOR-01`, next short-proposal batch date
   17 December 2026. Needs an EU-established company. Source:
   [GrantsFinder calendar](https://www.grantsfinder.eu/blog/eu-funding-deadlines-2026).
2. **Design-partner pilot with one bank or core-banking vendor**, found through the interviews.
   No grant needed; this is the route the Week 13 assessor review depends on.

Horizon Europe Cluster 3 (`HORIZON-CL3-2026-01-SSRI-01`, 5 November 2026) is civil security
research and a weak fit.

## Open issues

- Eligibility: EU grants need an EU legal entity. Whether the owner has or wants one is a
  business decision for the owner.
- The ROADMAP.md and CLAUDE.md changes for DORA first are drafted but not approved, so ROADMAP.md
  Week 0 still describes the US interviews. This report follows the owner's instruction to run
  the DORA version.

## Next steps for the owner

1. Send the outreach message to your first 12 contacts and hold the calls.
2. Fill `docs/week-00/tracker.csv` after each call.
3. Tell Claude when the tracker is filled, and the exit check and kill gate will be scored here.
