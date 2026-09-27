# Week 0: market validation (no code)

- Market: universal (`general`) is the main path, `eu-dora` the strong second (owner decision,
  2026-09-27, 05:00)
- Branch: `week-00-dora`
- Date: 2026-09-27
- Status: **closed on desk research by owner decision; interviews still open.** Public supervisor
  findings and industry surveys stand in for the interviews (scorecard below), and the proxy does
  not trigger the kill gate. On 2026-09-27 the owner chose to proceed to Week 5 on this evidence.
  The interview rows stay open and are scored when the tracker is filled; they should be done
  before Week 13 (assessor review).

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| Conversations held | 12 (4 bank ICT risk/change, 3 auditors, 3 COBOL engineers, 2 DORA-review veterans) | 0 of 12 | `docs/week-00/tracker.csv` |
| Name change-impact or PQC evidence as a gap | ≥ 4 of 12 | not run | tracker `names_gap`, `pqc_gap` |
| Auditor interest | ≥ 1 | not run | tracker `auditor_interest` |
| Funding or entry route identified | 1-2 | 2 candidates, not yet checked for fit | below |
| Proxy re-check from public research (added, not a roadmap check) | kill gate not triggered | **not triggered**: 3 of 5 criteria supported, 2 partly | proxy scorecard below |

Kill gate: fewer than 4 of 12 name the gap, or no auditor interest → re-scope before Week 5
(fallback `general` or `us-defense`).

## Desk research (2026-09-27)

Public sources read on 2026-09-27. Quotes came through a web-fetch summary and should be checked
against the original before they go into anything external.

### Demand: supervisors are asking for exactly this evidence

1. **The ECB will run a targeted review of ICT change management in 2026-28.** Its supervisory
   priorities say the primary root cause of unplanned downtime in banks often lies in ICT system
   changes, and that operational and ICT risk get the worst average SREP scores.
   Source: [ECB supervisory priorities 2026-28](https://www.bankingsupervision.europa.eu/framework/priorities/html/ssm.supervisory_priorities202511.en.html).
2. **The review covers more than 30 banks** through a questionnaire, supporting evidence and
   follow-up requests. Deficiencies it names include insufficient documentation and audit trails,
   and poor alignment between defined process and practice.
   Source: [KPMG ECB Office, ICT change management](https://kpmg.com/xx/en/our-insights/ecb-office/kpmg-european-central-bank-office-fs/ict-change-management.html).
3. **The ECB's 2026 IT Risk Questionnaire asks every significant bank** how many changes to
   critical systems caused issues, and for their top three root causes. The listed options
   include unexpected interdependencies between applications and inadequate test coverage. It
   also asks for the number of critical legacy systems and their migration plans.
   Source: [ECB ITRQ 2026](https://www.bankingsupervision.europa.eu/activities/srep/2026/html/ssm.srep_ITRQ2026.en.pdf).
4. **First-cycle DORA audits moved from checking policies to testing whether controls work in
   practice**, with findings on incomplete CMDBs (critical functions not mapped to assets) and
   testing programmes that omit critical systems.
   Source: [EY, lessons from the first DORA audits](https://www.ey.com/en_ch/insights/cybersecurity/lessons-learned-from-the-first-cycle-of-dora-audits).

How this maps to changeproof: "unexpected interdependencies" is the impact evidence (Weeks 3-5),
"inadequate test coverage" is the behavioural-equivalence evidence (Weeks 8-9), and "insufficient
audit trails" is the signed, file:line-provenanced record (Weeks 2-6). All of it is **planned**
except IR provenance (Week 2, PR #4).

### Competition: process evidence and code analysis exist, but not joined

- **Kosli** records SDLC process evidence (approvals, pipeline runs, what was deployed where) and
  lists banks as customers. Its page does not claim code-level impact or equivalence analysis.
  Source: [Kosli change management](https://www.kosli.com/release-change-management-automation/).
  This matches the roadmap's "complement, don't compete" position: changeproof attestations can
  feed Kosli.
- **IBM ADDI** does COBOL impact analysis and cross-reference reports and can run in CI/CD. The
  integration guide read here does not describe signed or audit-ready evidence.
  Source: [IBM, ADDI in CI/CD pipelines](https://www.ibm.com/support/pages/system/files/inline-files/Integrating%20IBM%20Application%20Discovery%20and%20Delivery%20Intelligence%20in%20CICD%20pipelines%20-%20v1.1_2.pdf).
  This is the closest competitor for COBOL impact. Banks on IBM Z may already own it, so a
  question for the interviews is whether its output is used as audit evidence today.

Gap, inferred from these two: nobody found here produces a per-change, signed record joining
code-level impact to proof that behaviour outside the change was preserved. The re-check below
adds CAST, OpenText and ServiceNow.

### Proxy scorecard (re-check, 2026-09-27)

Each interview criterion is matched to the closest public evidence. "Supported" means a
supervisor, auditor or survey of the same buyers states it; it does not mean a buyer said it to
us. The interviews confirm or overturn these.

| Interview criterion | Closest public evidence | Proxy result | Interviews must still confirm |
|---|---|---|---|
| Change-impact evidence is a real gap (`names_gap`) | ECB names ICT changes as the main cause of unplanned downtime and runs a targeted change-management review (demand 1-2); ITRQ 2026 lists "unexpected interdependencies" as a change-failure cause (demand 3) | **Supported** (supervisor side) | that banks feel it as their gap, not only the supervisor's |
| Behaviour outside the change is not proven (`names_gap`, equivalence half) | ITRQ 2026 lists "inadequate test coverage" and "misalignment between test and production" (demand 3); first DORA audits found testing programmes omitting critical systems (demand 4) | **Supported** | whether they would accept a tool's equivalence proof |
| Auditors care about evidence quality (`auditor_interest`) | EY: audits shifted from policies to whether controls work in practice (demand 4); KPMG: insufficient documentation and audit trails (demand 2) | **Supported** (need), not interest in us | that an auditor would rely on a signed artifact |
| PQC-migration evidence (`pqc_gap`) | EU roadmap: start by end of 2026, critical infrastructure by end of 2030; absent from the ECB's 2026-28 priorities read here | **Partly** | whether any bank has budget for it before 2028 |
| Legacy COBOL and AI-written changes raise the need | Kyndryl 2025 (500 leaders): 94% say regulation strongly influences modernisation, 70% struggle to find talent, 88% deploying or planning GenAI on the mainframe. BMC 2025 financial services: 81% already use GenAI, 47% for automated testing | **Partly**: surveys are global and vendor-run | whether AI-written COBOL changes need separate evidence |

Proxy kill gate: the roadmap's gate fails on fewer than 4 of 12 naming the gap or zero auditor
interest. The public evidence names the gap from both the supervisor and auditor sides, so the
proxy does not fail. The weak spots are PQC (partly) and auditor willingness to rely on a tool
(unknown). Both are why the interviews still matter before Week 13 (assessor review).

Survey sources: [Kyndryl 2025 State of Mainframe Modernization](https://www.kyndryl.com/us/en/campaign/state-of-mainframe-modernization),
[BMC 2025 Mainframe Survey, financial services](https://www.bmc.com/blogs/mainframe-survey-financial-services-key-takeaways/).
Both are vendor surveys, so treat the percentages as indicative.

### Competitors re-checked: CAST, OpenText, ServiceNow

| Tool | What it does (per the source read) | Signed per-change evidence | Behavioural equivalence | Source |
|---|---|---|---|---|
| CAST Imaging for Mainframe | maps dependencies between programs, transactions, data stores and batch jobs; positioned for modernisation planning | not mentioned | not mentioned | [product page](https://mainframemodernization.org/products/cast-imaging-mainframe/) |
| OpenText Enterprise Analyzer | parses COBOL, PL/I, Natural, JCL, CICS BMS; call graphs, data flow and impact analysis reports; positioned for modernisation planning | not mentioned | not mentioned | [product page](https://mainframemodernization.org/products/opentext-enterprise-analyzer/) |
| ServiceNow Change Management | computes change risk from conditions on change-record fields (Risk Calculator) or an optional risk assessment; widely used for DORA workflows | process record, not code evidence | no | [ServiceNow docs](https://www.servicenow.com/docs/bundle/zurich-it-service-management/page/product/change-management/concept/change-risk-conflict-analysis.html), [community guide](https://www.servicenow.com/community/developer-articles/getting-started-with-servicenow-change-request-risk-calculation/ta-p/2362172) |
| IBM ADDI (from the first pass) | COBOL impact analysis, can run in CI/CD | not described | not described | above |
| Kosli (from the first pass) | SDLC process evidence, bank customers | process, not code | no | above |

Reading across (inferred): CAST, OpenText and IBM are code-analysis tools sold for modernisation.
ServiceNow and Kosli hold the process record auditors see. None of the sources read shows a
per-change, signed record that joins code-level impact to proof of preserved behaviour, and none
ties its output to DORA Art. 17 or the ITRQ root causes. That join is changeproof's position,
and it fits the roadmap's "complement, don't compete" strategy: impact and equivalence
attestations that a ServiceNow change request or Kosli can reference. Product pages summarise;
none of these vendors' full documentation was read.

Implication for the build: code-analysis rivals already map programs, transactions, data stores,
batch jobs, JCL and CICS. Matching that graph is table stakes for Week 3, not a differentiator.

### What this means for Week 5 (planned)

- Framework mapping leads with the `general` profile (SOC 2 CC8.1, ISO/IEC 27001 A.8.25/8.28/
  8.29/8.32), per the owner's 05:00 decision to keep universal as the main path.
- The `eu-dora` section follows in the same document: DORA RTS Art. 16 and 17, plus the ECB ITRQ
  2026 change root causes (interdependencies, test coverage).
- Week 5 builds on Weeks 3 (dependency graphs) and 4 (diff to entities).

### What this adds to Weeks 3 and 4 (approved by the owner 2026-09-27, now in ROADMAP.md)

- **Week 3:** the graph should cover what CAST and OpenText already show (programs, CICS
  transactions, Db2 tables, files, batch jobs), and mark edges that cross from one configured
  component to another. "Unexpected interdependencies between applications" is the ITRQ root
  cause the impact evidence answers.
- **Week 4:** the change record should keep requester, implementer and approver as separate
  identities (Art. 17(1)(b) independence), carry an emergency-change flag (ITRQ counts emergency
  changes), and link the change-request ID from a ServiceNow-style ticket in the commit trailer
  for the *why* (purpose, scope, expected outcome, Art. 17(1)(d)). The engine links these fields
  and never invents them.

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
- ROADMAP.md and CLAUDE.md now make DORA the first market (owner approval, 2026-09-27), including
  the DORA version of these Week 0 interviews.

## Next steps for the owner

1. Send the outreach message to your first 12 contacts and hold the calls.
2. Fill `docs/week-00/tracker.csv` after each call.
3. Tell Claude when the tracker is filled, and the exit check and kill gate will be scored here.
4. Add to the interviews: ask banks whether they received the ECB change-management questionnaire,
   and whether they use IBM ADDI or a similar tool's output as audit evidence.
