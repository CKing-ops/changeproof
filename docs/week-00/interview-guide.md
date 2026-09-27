# Week 0 interview guide (DORA first)

Goal: find out whether EU banks, payment firms and their auditors see code-level change evidence
as a real gap, and recruit one auditor or bank as a design partner. No product demo and no
customer code. 30 minutes per conversation.

## Who (12 conversations)

| Group | Count | Role examples |
|---|---|---|
| A. ICT risk or change management at an EU bank or payment firm | 4 | head of ICT change management, ICT risk officer (second line), release manager for a core banking platform |
| B. Auditors | 3 | internal IT audit (third line), Big 4 or mid-tier IT-audit manager covering DORA engagements |
| C. Engineers who maintain COBOL at a bank or core-banking vendor | 3 | mainframe team lead, application owner for a batch payments system |
| D. People who went through a DORA supervisory review or register-of-information submission | 2 | compliance lead, CISO office staff |

Where to find them (all public, no scraping): LinkedIn searches on the role titles above plus
"DORA"; speakers and attendees at mainframe user groups and DORA compliance events; alumni and
personal network first. Record only role, organisation type and country in the tracker, not names.

## Questions

Ask open questions first. Do not name changeproof until question 8.

1. Walk me through the last significant change to a core system. What evidence did you produce,
   and who asked for it?
2. DORA's ICT risk management RTS (Delegated Regulation (EU) 2024/1774) asks for verification
   that security requirements were met (Art. 17(1)(a)), documented purpose and scope of each change
   (Art. 17(1)(d)), and testing and source code review before use (Art. 16). How do you meet
   those today? Which part costs the most time?
3. When you say a change's scope is X, how do you know it touched nothing else? What would an
   auditor accept as proof?
4. Has an auditor or supervisor ever rejected or questioned your change evidence? What was missing?
5. How much of the code behind your critical functions is COBOL? Who understands its dependencies
   when a change lands?
6. Are AI coding tools used on these systems, or planned? How do you evidence what they changed?
7. Has post-quantum migration come up (the EU roadmap asks critical infrastructure to finish by
   the end of 2030)? Who will prove a crypto swap did not change behaviour?
8. If a tool produced, per change, a signed record of what the change touches (programs, fields,
   files, jobs) with file:line references, and proof that behaviour outside that scope was
   preserved, would it replace or reduce any work you do now? What would make an auditor trust it?
9. Would it have to run inside your environment with no network? Who would have to approve it?
10. Who else should I talk to?

For group B (auditors), replace 1, 5 and 6 with: "What change-management evidence do you sample in
a DORA engagement, and what do you reject?" and "Would you rely on a signed, reproducible artifact
from a tool, and what would you need to see first?"

## Scoring (fill the tracker after each call)

- `names_gap`: yes if the person names change-impact or behavioural-equivalence evidence as a real
  gap without being led (before question 8).
- `pqc_gap`: yes if they name PQC-migration evidence as a gap.
- `auditor_interest`: yes if an auditor (group B) asks to see a sample pack or offers a follow-up.
- `design_partner`: yes if they would pilot on public or synthetic code, or introduce someone who would.
- `quote`: one short sentence in their words, with their permission.

## Kill gate (from the roadmap)

Fewer than 4 of 12 score `names_gap` or `pqc_gap` yes, or zero `auditor_interest` → re-scope
before Week 5. Fallback: the `general` market (SOC 2 / ISO 27001) or reopening `us-defense`.
