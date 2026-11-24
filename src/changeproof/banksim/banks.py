"""Six invented banks, three in the US and three in the EU (ADR 014).

Every bank runs the same four programs; only the business rules in them differ. The names, places,
people and numbers are made up for the simulation and stand for no real institution or person.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Bank:
    id: str
    name: str
    city: str
    region: str  # us or eu
    market: str  # the changeproof.yaml market profile the bank is set up with
    currency: str
    utc_offset: str  # commit times are 09:30 local
    ticket_project: str  # Jira project key in commit subjects
    developers: tuple[tuple[str, str], ...]
    requester: tuple[str, str]
    approver: tuple[str, str]
    rules: dict[str, str]  # template value to COBOL literal


# Cash reporting: US banks report cash in or out of more than 10,000 a business day, aggregated per
# customer (31 CFR 1010.311 and 1010.313, checked 2026-11-24 at
# https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1010/subpart-C/section-1010.311 and
# .../section-1010.313). The EU banks use EUR 15,000 or more, the occasional-transaction threshold of
# Directive (EU) 2015/849 Art. 11(b)(i) (https://eur-lex.europa.eu/eli/dir/2015/849/oj): unverified,
# the article text was not read. Rates, fees and limits are invented.
US_RULES = {"basis": "365", "max_days": "31", "report_threshold": "10000.00", "delinquent_days": "30",
            "fx1": "EUR", "fx2": "GBP", "fx3": "CAD", "cash_op": ">", "cash_threshold": "10000.00",
            "structuring_floor": "8000.00"}
EU_RULES = {"basis": "360", "max_days": "31", "report_threshold": "10000.00", "delinquent_days": "30",
            "fx1": "USD", "fx2": "GBP", "fx3": "CHF", "cash_op": ">=", "cash_threshold": "15000.00",
            "structuring_floor": "12000.00"}

BANKS = (  # RENAME: THE SIMULATED BANKS
    Bank("prairie-ledger", "Prairie Ledger Bank", "Kansas City, MO", "us", "general", "USD", "-05:00", "DEP",
         (("Dana Whitfield", "dana.whitfield@prairieledger.example"),
          ("Marcus Oyelaran", "marcus.oyelaran@prairieledger.example")),
         ("Elaine Castor", "elaine.castor@prairieledger.example"),
         ("Victor Ames", "victor.ames@prairieledger.example"),
         US_RULES | {"tier": "25000.00", "rate_high": "0.042500", "rate_low": "0.015000", "rate_checking": "0.001000",
                     "retail_minimum": "1500.00", "retail_fee": "12.00", "business_fee": "25.00", "free_txns": "200",
                     "per_txn": "0.30", "online_limit": "5000.00", "branch_limit": "50000.00",
                     "overdraft_fee": "35.00",
                     "apr_mortgage": "0.067125", "apr_auto": "0.074900", "apr_personal": "0.119900",
                     "grace_days": "15", "late_pct": "0.0500", "late_min": "15.00", "late_cap": "40.00",
                     "fx1_rate": "1.084500", "fx2_rate": "1.267300", "fx3_rate": "0.731800", "fx_spread": "0.0150",
                     "fx_min_fee": "5.00", "fx_review": "50000.00"}),
    Bank("tidewater", "Tidewater Mutual Savings", "Norfolk, VA", "us", "general", "USD", "-05:00", "CORE",
         (("Priya Nandakumar", "priya.nandakumar@tidewatermutual.example"),
          ("Owen Brask", "owen.brask@tidewatermutual.example")),
         ("Rosalind Teague", "rosalind.teague@tidewatermutual.example"),
         ("Harold Kim", "harold.kim@tidewatermutual.example"),
         US_RULES | {"tier": "10000.00", "rate_high": "0.039000", "rate_low": "0.020000", "rate_checking": "0.000500",
                     "retail_minimum": "500.00", "retail_fee": "8.00", "business_fee": "15.00", "free_txns": "150",
                     "per_txn": "0.25", "online_limit": "10000.00", "branch_limit": "75000.00",
                     "overdraft_fee": "29.00",
                     "apr_mortgage": "0.064375", "apr_auto": "0.069900", "apr_personal": "0.109500",
                     "grace_days": "10", "late_pct": "0.0400", "late_min": "10.00", "late_cap": "35.00",
                     "fx1_rate": "1.083900", "fx2_rate": "1.266100", "fx3_rate": "0.732400", "fx_spread": "0.0175",
                     "fx_min_fee": "7.50", "fx_review": "25000.00"}),
    Bank("copperline", "Copperline Trust Company", "Denver, CO", "us", "general", "USD", "-07:00", "TRUST",
         (("Lucia Fenwick", "lucia.fenwick@copperlinetrust.example"),
          ("Ray Delacroix", "ray.delacroix@copperlinetrust.example")),
         ("Simone Hart", "simone.hart@copperlinetrust.example"),
         ("Gordon Pike", "gordon.pike@copperlinetrust.example"),
         US_RULES | {"tier": "50000.00", "rate_high": "0.045000", "rate_low": "0.017500", "rate_checking": "0.000100",
                     "retail_minimum": "2500.00", "retail_fee": "15.00", "business_fee": "30.00", "free_txns": "250",
                     "per_txn": "0.20", "online_limit": "25000.00", "branch_limit": "250000.00",
                     "overdraft_fee": "32.00",
                     "apr_mortgage": "0.071125", "apr_auto": "0.081250", "apr_personal": "0.134900",
                     "grace_days": "15", "late_pct": "0.0600", "late_min": "20.00", "late_cap": "75.00",
                     "fx1_rate": "1.085100", "fx2_rate": "1.268800", "fx3_rate": "0.731200", "fx_spread": "0.0125",
                     "fx_min_fee": "10.00", "fx_review": "100000.00"}),
    Bank("aldercove", "Aldercove Bank N.V.", "Utrecht, NL", "eu", "eu-dora", "EUR", "+01:00", "ICT",
         (("Sanne de Wit", "sanne.dewit@aldercove.example"), ("Joris Bakker", "joris.bakker@aldercove.example")),
         ("Femke Visser", "femke.visser@aldercove.example"),
         ("Pieter Jansen", "pieter.jansen@aldercove.example"),
         EU_RULES | {"tier": "20000.00", "rate_high": "0.027500", "rate_low": "0.010000", "rate_checking": "0.000100",
                     "retail_minimum": "1000.00", "retail_fee": "3.50", "business_fee": "12.50", "free_txns": "100",
                     "per_txn": "0.15", "online_limit": "15000.00", "branch_limit": "100000.00",
                     "overdraft_fee": "5.00",
                     "apr_mortgage": "0.038625", "apr_auto": "0.054900", "apr_personal": "0.079900",
                     "grace_days": "14", "late_pct": "0.0200", "late_min": "2.50", "late_cap": "25.00",
                     "fx1_rate": "0.921700", "fx2_rate": "1.168400", "fx3_rate": "1.041200", "fx_spread": "0.0100",
                     "fx_min_fee": "2.50", "fx_review": "40000.00"}),
    Bank("serravento", "Banca Serravento S.p.A.", "Turin, IT", "eu", "eu-dora", "EUR", "+01:00", "SIB",
         (("Giulia Ferraris", "giulia.ferraris@serravento.example"),
          ("Matteo Lanza", "matteo.lanza@serravento.example")),
         ("Chiara Bellini", "chiara.bellini@serravento.example"),
         ("Stefano Gallo", "stefano.gallo@serravento.example"),
         EU_RULES | {"tier": "30000.00", "rate_high": "0.025000", "rate_low": "0.007500", "rate_checking": "0.000100",
                     "retail_minimum": "2000.00", "retail_fee": "4.00", "business_fee": "18.00", "free_txns": "120",
                     "per_txn": "0.18", "online_limit": "10000.00", "branch_limit": "150000.00",
                     "overdraft_fee": "7.50",
                     "apr_mortgage": "0.041375", "apr_auto": "0.062500", "apr_personal": "0.089500",
                     "grace_days": "10", "late_pct": "0.0150", "late_min": "3.00", "late_cap": "20.00",
                     "fx1_rate": "0.922300", "fx2_rate": "1.167900", "fx3_rate": "1.040800", "fx_spread": "0.0120",
                     "fx_min_fee": "3.00", "fx_review": "30000.00"}),
    Bank("kestrelmark", "Kestrelmark Sparkasse", "Kassel, DE", "eu", "eu-dora", "EUR", "+01:00", "KMS",
         (("Lena Hoffmann", "lena.hoffmann@kestrelmark.example"),
          ("Tobias Brandt", "tobias.brandt@kestrelmark.example")),
         ("Anja Krüger", "anja.krueger@kestrelmark.example"),
         ("Jens Albrecht", "jens.albrecht@kestrelmark.example"),
         EU_RULES | {"tier": "15000.00", "rate_high": "0.030000", "rate_low": "0.012500", "rate_checking": "0.000100",
                     "retail_minimum": "1200.00", "retail_fee": "6.90", "business_fee": "14.90", "free_txns": "80",
                     "per_txn": "0.12", "online_limit": "20000.00", "branch_limit": "200000.00",
                     "overdraft_fee": "4.50",
                     "apr_mortgage": "0.036875", "apr_auto": "0.049900", "apr_personal": "0.074500",
                     "grace_days": "14", "late_pct": "0.0250", "late_min": "2.00", "late_cap": "30.00",
                     "fx1_rate": "0.921900", "fx2_rate": "1.169100", "fx3_rate": "1.041500", "fx_spread": "0.0090",
                     "fx_min_fee": "2.00", "fx_review": "50000.00"}),
)
