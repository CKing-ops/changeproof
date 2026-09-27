"""Which COBOL calls touch cryptography, for the crypto inventory (ROADMAP Weeks 2 and 16).

Only names are matched here; nothing is hashed, signed or encrypted (CLAUDE.md rule 6). The
algorithm behind a call usually lives in its key or rule array, so Week 16 resolves that.
"""

import re

# IBM ICSF callable services, by base name. 64-bit callers use CSNE/CSNF for CSNB/CSND, and a
# trailing 1 marks the ALET variant; both map back to the base name.
ICSF_SERVICES = {  # RENAME: ICSF SERVICE NAME TO CRYPTO CATEGORY
    "CSNBOWH": "hash",
    "CSNBHMG": "mac-generate",
    "CSNBHMV": "mac-verify",
    "CSNBMGN": "mac-generate",
    "CSNBMVR": "mac-verify",
    "CSNBENC": "symmetric-encrypt",
    "CSNBDEC": "symmetric-decrypt",
    "CSNBSYE": "symmetric-encrypt",
    "CSNBSYD": "symmetric-decrypt",
    "CSNBKGN": "key-generate",
    "CSNBCKM": "key-import",
    "CSNBRNG": "random",
    "CSNBRNGL": "random",
    "CSNBPGN": "pin-generate",
    "CSNBPVR": "pin-verify",
    "CSNDDSG": "signature-generate",
    "CSNDDSV": "signature-verify",
    "CSNDPKG": "key-generate",
    "CSNDPKE": "asymmetric-encrypt",
    "CSNDPKD": "asymmetric-decrypt",
    "CSNDEDH": "key-agreement",
}
ICSF_PREFIXES = ("CSNB", "CSND", "CSNE", "CSNF", "CSFP")  # RENAME: NAME PREFIXES RESERVED FOR ICSF SERVICES

# Db2 built-in functions that hash or encrypt column data.
SQL_FUNCTIONS = {  # RENAME: SQL FUNCTION NAME TO CRYPTO CATEGORY
    "ENCRYPT_TDES": "symmetric-encrypt",
    "ENCRYPT": "symmetric-encrypt",
    "DECRYPT_BIT": "symmetric-decrypt",
    "DECRYPT_CHAR": "symmetric-decrypt",
    "DECRYPT_DB": "symmetric-decrypt",
    "DECRYPT_BINARY": "symmetric-decrypt",
    "HASH_MD5": "hash",
    "HASH_SHA1": "hash",
    "HASH_SHA256": "hash",
    "HASH": "hash",
}
SQL_FUNCTION_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted(SQL_FUNCTIONS, key=len, reverse=True)) + r")\s*\(",
                             re.IGNORECASE)


# PURPOSE: RETURNS (BASE SERVICE, CATEGORY) IF A CALL TARGET IS AN ICSF SERVICE, ELSE NONE
def classify_call(target: str) -> tuple[str, str] | None:
    name = target.upper()
    if not name.startswith(ICSF_PREFIXES):
        return None
    base = name[:-1] if name.endswith("1") and name[:-1] in ICSF_SERVICES else name
    base = {"CSNE": "CSNB", "CSNF": "CSND"}.get(base[:4], base[:4]) + base[4:]
    return base, ICSF_SERVICES.get(base, "unclassified")


# PURPOSE: LISTS (FUNCTION, CATEGORY) FOR EVERY CRYPTO FUNCTION USED IN AN SQL STATEMENT
def classify_sql(text: str) -> list[tuple[str, str]]:
    return [(m.group(1).upper(), SQL_FUNCTIONS[m.group(1).upper()]) for m in SQL_FUNCTION_RE.finditer(text)]
