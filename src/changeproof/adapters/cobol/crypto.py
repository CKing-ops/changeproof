"""Which COBOL calls touch cryptography, for the crypto inventory (ROADMAP Weeks 2 and 16).

Only names are matched here; nothing is hashed, signed or encrypted (CLAUDE.md rule 6). The
algorithm behind a call usually lives in its key or rule array. Week 7 reads it from literals that
reach the data a call is given; the full inventory is Week 16.

The ICSF service names and rule-array keywords below are unverified at source (IBM ICSF
Application Programmer's Guide); they are matched only against literals written in the program.
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
    "CSNDPKB": "key-token-build",
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


# Literal words that name an algorithm, tried in order against each literal a call is given.
ALGORITHM_WORDS = [  # RENAME: LITERAL PATTERN TO ALGORITHM ID
    (re.compile(r"^RSA"), "rsa"),
    (re.compile(r"^(ECC|ECDSA|ECDH|EC-)"), "ecc"),
    (re.compile(r"^DSA$"), "dsa"),
    (re.compile(r"^(DH|DIFFIE)"), "dh"),
    (re.compile(r"^SHA-?(1|224|256|384|512)$"), "sha-{0}"),
    (re.compile(r"^MD5$"), "md5"),
    (re.compile(r"^AES"), "aes"),
    (re.compile(r"^T?DES"), "des"),
]
QUANTUM_VULNERABLE = frozenset({"rsa", "ecc", "dsa", "dh"})  # RENAME: ALGORITHMS SHOR'S ALGORITHM BREAKS
KEY_SIZES = frozenset({1024, 2048, 3072, 4096, 8192})  # RENAME: NUMBERS READ AS AN RSA, DSA OR DH KEY SIZE
PUBLIC_KEY_PREFIX = "CSND"  # RENAME: ICSF PREFIX OF PUBLIC-KEY SERVICES, WHERE AN UNREAD ALGORITHM STAYS UNKNOWN
SQL_ALGORITHMS = {"HASH_MD5": "md5", "HASH_SHA1": "sha-1", "HASH_SHA256": "sha-256", "ENCRYPT_TDES": "des"}


# PURPOSE: ALGORITHM, KEY SIZE AND QUANTUM EXPOSURE OF AN ICSF CALL FROM (VALUE, SOURCE ID) PAIRS IT IS GIVEN
def read_algorithm(service: str, given: list[tuple[str | int, str]]) -> dict:
    algorithm, sources = None, []
    for value, source in given:
        if isinstance(value, str) and algorithm is None:
            word = value.strip().upper()
            for pattern, name in ALGORITHM_WORDS:
                if m := pattern.match(word):
                    algorithm = name.format(*m.groups())
                    sources.append(source)
                    break
    bits = None
    if algorithm in {"rsa", "dsa", "dh"}:
        bits, source = next(((v, s) for v, s in given if isinstance(v, int) and v in KEY_SIZES), (None, None))
        if source:
            sources.append(source)
    if algorithm:
        exposed = algorithm in QUANTUM_VULNERABLE
    else:
        exposed = None if service.startswith(PUBLIC_KEY_PREFIX) else False
    return {"algorithm": algorithm, "key_bits": bits, "quantum_vulnerable": exposed, "algorithm_from": sources}


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
