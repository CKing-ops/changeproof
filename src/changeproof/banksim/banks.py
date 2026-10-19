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


US_RULES = {"basis": "365", "max_days": "31", "report_threshold": "10000.00"}
EU_RULES = {"basis": "360", "max_days": "31", "report_threshold": "10000.00"}

BANKS = (  # RENAME: THE SIMULATED BANKS
    Bank("prairie-ledger", "Prairie Ledger Bank", "Kansas City, MO", "us", "general", "USD", "-05:00", "DEP",
         (("Dana Whitfield", "dana.whitfield@prairieledger.example"),
          ("Marcus Oyelaran", "marcus.oyelaran@prairieledger.example")),
         ("Elaine Castor", "elaine.castor@prairieledger.example"),
         ("Victor Ames", "victor.ames@prairieledger.example"),
         US_RULES | {"tier": "25000.00", "rate_high": "0.042500", "rate_low": "0.015000", "rate_checking": "0.001000",
                     "retail_minimum": "1500.00", "retail_fee": "12.00", "business_fee": "25.00", "free_txns": "200",
                     "per_txn": "0.30", "online_limit": "5000.00", "branch_limit": "50000.00",
                     "overdraft_fee": "35.00"}),
    Bank("tidewater", "Tidewater Mutual Savings", "Norfolk, VA", "us", "general", "USD", "-05:00", "CORE",
         (("Priya Nandakumar", "priya.nandakumar@tidewatermutual.example"),
          ("Owen Brask", "owen.brask@tidewatermutual.example")),
         ("Rosalind Teague", "rosalind.teague@tidewatermutual.example"),
         ("Harold Kim", "harold.kim@tidewatermutual.example"),
         US_RULES | {"tier": "10000.00", "rate_high": "0.039000", "rate_low": "0.020000", "rate_checking": "0.000500",
                     "retail_minimum": "500.00", "retail_fee": "8.00", "business_fee": "15.00", "free_txns": "150",
                     "per_txn": "0.25", "online_limit": "10000.00", "branch_limit": "75000.00",
                     "overdraft_fee": "29.00"}),
    Bank("copperline", "Copperline Trust Company", "Denver, CO", "us", "general", "USD", "-07:00", "TRUST",
         (("Lucia Fenwick", "lucia.fenwick@copperlinetrust.example"),
          ("Ray Delacroix", "ray.delacroix@copperlinetrust.example")),
         ("Simone Hart", "simone.hart@copperlinetrust.example"),
         ("Gordon Pike", "gordon.pike@copperlinetrust.example"),
         US_RULES | {"tier": "50000.00", "rate_high": "0.045000", "rate_low": "0.017500", "rate_checking": "0.000100",
                     "retail_minimum": "2500.00", "retail_fee": "15.00", "business_fee": "30.00", "free_txns": "250",
                     "per_txn": "0.20", "online_limit": "25000.00", "branch_limit": "250000.00",
                     "overdraft_fee": "32.00"}),
    Bank("aldercove", "Aldercove Bank N.V.", "Utrecht, NL", "eu", "eu-dora", "EUR", "+01:00", "ICT",
         (("Sanne de Wit", "sanne.dewit@aldercove.example"), ("Joris Bakker", "joris.bakker@aldercove.example")),
         ("Femke Visser", "femke.visser@aldercove.example"),
         ("Pieter Jansen", "pieter.jansen@aldercove.example"),
         EU_RULES | {"tier": "20000.00", "rate_high": "0.027500", "rate_low": "0.010000", "rate_checking": "0.000100",
                     "retail_minimum": "1000.00", "retail_fee": "3.50", "business_fee": "12.50", "free_txns": "100",
                     "per_txn": "0.15", "online_limit": "15000.00", "branch_limit": "100000.00",
                     "overdraft_fee": "5.00"}),
    Bank("serravento", "Banca Serravento S.p.A.", "Turin, IT", "eu", "eu-dora", "EUR", "+01:00", "SIB",
         (("Giulia Ferraris", "giulia.ferraris@serravento.example"),
          ("Matteo Lanza", "matteo.lanza@serravento.example")),
         ("Chiara Bellini", "chiara.bellini@serravento.example"),
         ("Stefano Gallo", "stefano.gallo@serravento.example"),
         EU_RULES | {"tier": "30000.00", "rate_high": "0.025000", "rate_low": "0.007500", "rate_checking": "0.000100",
                     "retail_minimum": "2000.00", "retail_fee": "4.00", "business_fee": "18.00", "free_txns": "120",
                     "per_txn": "0.18", "online_limit": "10000.00", "branch_limit": "150000.00",
                     "overdraft_fee": "7.50"}),
    Bank("kestrelmark", "Kestrelmark Sparkasse", "Kassel, DE", "eu", "eu-dora", "EUR", "+01:00", "KMS",
         (("Lena Hoffmann", "lena.hoffmann@kestrelmark.example"),
          ("Tobias Brandt", "tobias.brandt@kestrelmark.example")),
         ("Anja Krüger", "anja.krueger@kestrelmark.example"),
         ("Jens Albrecht", "jens.albrecht@kestrelmark.example"),
         EU_RULES | {"tier": "15000.00", "rate_high": "0.030000", "rate_low": "0.012500", "rate_checking": "0.000100",
                     "retail_minimum": "1200.00", "retail_fee": "6.90", "business_fee": "14.90", "free_txns": "80",
                     "per_txn": "0.12", "online_limit": "20000.00", "branch_limit": "200000.00",
                     "overdraft_fee": "4.50"}),
)
