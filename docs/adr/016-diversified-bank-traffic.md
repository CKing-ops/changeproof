# ADR 016: Diversified bank traffic aimed at the engine's weak spots

- Status: proposed. Asked for by the owner on 2026-11-24 ("lets add to all banks more traffic and a
  diversified traffic to best mimic real like transactions, policies, laws ect... Look for the strongest
  form our engine proves being a viable product").
- Date: 2026-11-24
- Related: ADR 014 (bank simulation), ADR 015 (boundary and joint search)

## Context

After about simulated day 50 the stream taught little. Intended changes and refactors merge, so the text
they replace is gone and they can never be drawn again; rejected defects stay open and are drawn forever.
Days 51 to 1279 were 7,296 defects, 45 intended changes and 33 refactors (counted from `sim/ledger.jsonl`).
The weak spots it had found (intended-change confirmation at 47 of 72, the half-cent rounding miss,
limits reached only through two fields) were not being tested again. Every bank also ran the same four
small programs.

## Decision

1. **Three more programs per bank** (`banksim/estate/`), each with business rules that differ by bank:
   `LOANPMT` (monthly loan interest with ROUNDED, late fee with a floor and a cap, grace and delinquency
   day counts, negative amortisation), `FXCONV` (conversion at a six-decimal rate, a spread fee with a
   minimum, a review threshold, unquoted currencies) and `CASHAGG` (a customer's cash in or out totalled
   over the business day against a reporting threshold, plus a structuring alert for deposits just under
   it). US banks use the reporting rule "more than $10,000" with same-day aggregation
   (31 CFR 1010.311 and 1010.313, checked 2026-11-24 at
   https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1010/subpart-C/section-1010.311 and
   https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1010/subpart-C/section-1010.313).
   EU banks use EUR 15,000 or more, after Directive (EU) 2015/849 Art. 11(b)(i)
   (https://eur-lex.europa.eu/eli/dir/2015/849/oj): **unverified**, the article text was not read.
   The operator itself is a bank rule (`cash_op`), so code never branches on a market.
2. **A wider catalogue, 72 changes per bank, aimed at the weak spots.** Rounding removed from three
   computations; a data-division slip that shortens a rate field or a total field (precision loss,
   high-order truncation); boundary flips on day counts and money thresholds; a swapped rate table; a fee
   charged on the wrong amount; a condition rewritten as "not a cheque" that differs only on invalid
   codes; and refactors that look risky (late-fee cap and floor applied in the other order, `> 15` as
   `>= 16` on an integer field). Intended changes move a rule up or down from its **current** value, read
   back from the tree (`current`), and every refactor has a `-back` twin, so neither kind runs out.
3. **A draw that stops repeating.** A kind is drawn first (defect 5, intended 3, refactor 2), then a
   change of that kind weighted by 1 / (1 + times this bank has drawn it) (`run.draw`).
4. **Every label is proven by running it.** `banksim/audit.py` runs the base and changed program on the
   same probes (rule boundaries plus seeded draws). A defect or intended change must change at least one
   output and a refactor none. A refactor's "same" is a sampled check, not a proof.
   `scripts/bank_audit.py` writes `docs/weekly/bank-change-audit.json`.
5. **More traffic.** Weekday postings 40 to 80 (was 25 to 45), payments 25 to 50 (was 15 to 30), plus
   12 to 30 loan installments, 8 to 20 conversions and 20 to 40 cash transactions, some split just under
   the reporting threshold and some exactly on it. Fewer at weekends.
6. **Existing banks onboard the new programs** with one governed commit on the day they first run
   (`repository(bank, state, day)`), so the stream carries on without a restart.

## Consequences

- Scans take about three times longer (seven programs, larger suites after ADR 015).
- Still the same tidy COBOL 85 house style at every bank: no CICS, Db2, IMS, copybooks shared across
  programs, REDEFINES-heavy records, GO TO or ALTER, and no multi-file changes. Those remain untested
  here (see the public-code graft in its own ADR).
- No core schema changed; nothing leaves the machine.
