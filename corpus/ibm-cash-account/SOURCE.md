# IBM Stock Trader Cash Account (COBOL) corpus

- Upstream: https://github.com/IBMStockTrader/cash-account-cobol
- Commit: `c35db0d1f283367109bcd5dfadd76560cf53b2dc` (2025-10-07)
- License: Apache-2.0 (`LICENSE` kept alongside; upstream has no NOTICE file)
- Subset: `README.md`, `COBOL/`, `DB2-DDL/`, `VSAM/`. The architecture diagram (PNG) is left out.
  Paths below this directory match upstream. Files are unmodified.
- What it is: one CICS program (`CASH00`) that adds, reads, updates, deletes, credits and debits
  cash accounts in Db2, converts with a rate table, and writes a VSAM history record; DCLGEN
  copybooks for its two tables; JCL that creates the tables and indexes, binds the plan and
  defines the VSAM file.
- Used by: `src/changeproof/banksim/public.py` (ADR 017), which gives it to one simulated bank.
