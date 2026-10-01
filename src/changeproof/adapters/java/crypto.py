"""Which Java calls touch cryptography: the JCA engine classes and their standard algorithm names.

Only names are matched here; nothing is hashed, signed or encrypted. The class and algorithm names
follow the Java Security Standard Algorithm Names specification
(https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html), which is
**unverified** at source: the list below has not been checked against that page yet.
"""

import re

JCA_SERVICES = {  # RENAME: JCA ENGINE CLASS TO CRYPTO CATEGORY
    "java.security.MessageDigest": "hash",
    "java.security.Signature": "signature",
    "java.security.KeyPairGenerator": "key-generate",
    "java.security.KeyFactory": "key-factory",
    "java.security.SecureRandom": "random",
    "java.security.KeyStore": "key-store",
    "javax.crypto.Cipher": "cipher",
    "javax.crypto.Mac": "mac",
    "javax.crypto.KeyGenerator": "key-generate",
    "javax.crypto.KeyAgreement": "key-agreement",
    "javax.crypto.SecretKeyFactory": "key-derive",
    "javax.crypto.KEM": "kem",
}
FACTORY_METHODS = frozenset({"getInstance", "getInstanceStrong"})  # RENAME: STATIC METHODS THAT PICK AN ALGORITHM
KEY_SIZE_METHODS = frozenset({"initialize", "init"})  # RENAME: CALLS WHOSE FIRST INTEGER ARGUMENT IS A KEY SIZE
PUBLIC_KEY_CATEGORIES = frozenset({"signature", "key-factory", "key-agreement", "kem"})  # RENAME: CATEGORIES WHERE AN UNREAD ALGORITHM STAYS UNKNOWN

ALGORITHM_WORDS = [  # RENAME: STANDARD-NAME PATTERN TO ALGORITHM ID, TRIED IN ORDER
    (re.compile(r"^ML-?DSA"), "ml-dsa"),
    (re.compile(r"^ML-?KEM"), "ml-kem"),
    (re.compile(r"^RSA"), "rsa"),
    (re.compile(r"^(EC|ECDSA|ECDH|ED25519|ED448|EDDSA|X25519|X448|XDH)$"), "ecc"),
    (re.compile(r"^DSA$"), "dsa"),
    (re.compile(r"^(DH|DIFFIEHELLMAN)$"), "dh"),
    (re.compile(r"^SHA3-(224|256|384|512)$"), "sha3-{0}"),
    (re.compile(r"^SHA-?(1|224|256|384|512)$"), "sha-{0}"),
    (re.compile(r"^MD5$"), "md5"),
    (re.compile(r"^HMAC"), "hmac"),
    (re.compile(r"^AES"), "aes"),
    (re.compile(r"^(DES|DESEDE|TRIPLEDES)$"), "des"),
]
QUANTUM_VULNERABLE = frozenset({"rsa", "ecc", "dsa", "dh"})  # RENAME: ALGORITHMS SHOR'S ALGORITHM BREAKS


# PURPOSE: ALGORITHM ID OF A STANDARD NAME: THE KEY ALGORITHM OF A SIGNATURE, THE FIRST PART OF A TRANSFORMATION
def algorithm_of(name: str) -> str | None:
    word = name.strip().upper().split("/", 1)[0]
    if "WITH" in word:
        word = word.split("WITH", 1)[1].split("AND", 1)[0]
    for pattern, found in ALGORITHM_WORDS:
        if m := pattern.match(word):
            return found.format(*m.groups())
    return None


# PURPOSE: CRYPTO ATTRIBUTES OF A JCA CALL FROM THE ALGORITHM NAME AND KEY SIZE IT IS GIVEN
def crypto_attributes(service: str, literal: str | None, key_bits: int | None) -> dict:
    category = JCA_SERVICES[service]
    algorithm = algorithm_of(literal) if literal else None
    if algorithm:
        exposed = algorithm in QUANTUM_VULNERABLE
    else:
        exposed = None if category in PUBLIC_KEY_CATEGORIES or service.endswith("KeyPairGenerator") else False
    return {"service": service, "category": category, "via": "java", "algorithm": algorithm,
            "key_bits": key_bits if algorithm in {"rsa", "dsa", "dh"} else None, "quantum_vulnerable": exposed,
            "algorithm_from": [literal] if algorithm else []}
