"""Every cryptographic algorithm the engine knows, keyed by its opaque ID (ADR 002).

This package is the only place a crypto library is imported or an algorithm is named in code.
Adding an algorithm means adding a class here and registering it; no schema changes.
"""

import hashlib
from abc import ABC, abstractmethod
from importlib.metadata import version

import pyhsslms
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, mldsa

CLASSICAL = "classical"
POST_QUANTUM = "post-quantum"
# sha-256 is here only to check upstream download pins, which are published as SHA-256
HASHES = {"sha-384": hashlib.sha384, "sha-256": hashlib.sha256}  # RENAME: HASH ALGORITHM ID TO CONSTRUCTOR


class Algorithm(ABC):
    id: str
    family: str
    package: str  # distribution whose version is recorded with every signature
    stateful = False

    # PURPOSE: LIBRARY NAME AND INSTALLED VERSION, AS RECORDED IN EACH SIGNATURE
    @property
    def library(self) -> str:
        return f"{self.package} {version(self.package)}"

    # PURPOSE: NEW PRIVATE KEY BYTES
    @abstractmethod
    def generate(self) -> bytes: ...

    # PURPOSE: PUBLIC KEY BYTES FOR A PRIVATE KEY
    @abstractmethod
    def public_of(self, secret: bytes) -> bytes: ...

    # PURPOSE: SIGNS A MESSAGE; RETURNS THE SIGNATURE AND THE PRIVATE KEY BYTES TO KEEP AFTERWARDS
    @abstractmethod
    def sign(self, secret: bytes, message: bytes) -> tuple[bytes, bytes]: ...

    # PURPOSE: TRUE WHEN THE SIGNATURE OVER THE MESSAGE IS VALID FOR THE PUBLIC KEY
    @abstractmethod
    def verify(self, public: bytes, message: bytes, signature: bytes) -> bool: ...

    # PURPOSE: SIGNATURES LEFT ON A STATEFUL KEY; NONE FOR STATELESS ALGORITHMS
    def remaining(self, secret: bytes) -> int | None:
        return None


class EcdsaP384(Algorithm):
    id = "ecdsa-p384"
    family = CLASSICAL
    package = "cryptography"

    # PURPOSE: NEW P-384 KEY AS PKCS#8 DER
    def generate(self) -> bytes:
        return ec.generate_private_key(ec.SECP384R1()).private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())

    # PURPOSE: SUBJECTPUBLICKEYINFO DER FOR A PKCS#8 KEY
    def public_of(self, secret: bytes) -> bytes:
        return serialization.load_der_private_key(secret, None).public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)

    # PURPOSE: ECDSA OVER SHA-384
    def sign(self, secret: bytes, message: bytes) -> tuple[bytes, bytes]:
        return serialization.load_der_private_key(secret, None).sign(message, ec.ECDSA(hashes.SHA384())), secret

    # PURPOSE: CHECKS AN ECDSA SHA-384 SIGNATURE
    def verify(self, public: bytes, message: bytes, signature: bytes) -> bool:
        try:
            serialization.load_der_public_key(public).verify(signature, message, ec.ECDSA(hashes.SHA384()))
        except InvalidSignature:
            return False
        return True


class MlDsa87(Algorithm):
    id = "ml-dsa-87"
    family = POST_QUANTUM
    package = "cryptography"

    # PURPOSE: NEW ML-DSA-87 KEY AS ITS 32-BYTE SEED
    def generate(self) -> bytes:
        return mldsa.MLDSA87PrivateKey.generate().private_bytes_raw()

    # PURPOSE: RAW ML-DSA-87 PUBLIC KEY FOR A SEED
    def public_of(self, secret: bytes) -> bytes:
        return mldsa.MLDSA87PrivateKey.from_seed_bytes(secret).public_key().public_bytes_raw()

    # PURPOSE: PURE ML-DSA-87 SIGNATURE (FIPS 204), EMPTY CONTEXT
    def sign(self, secret: bytes, message: bytes) -> tuple[bytes, bytes]:
        return mldsa.MLDSA87PrivateKey.from_seed_bytes(secret).sign(message), secret

    # PURPOSE: CHECKS AN ML-DSA-87 SIGNATURE
    def verify(self, public: bytes, message: bytes, signature: bytes) -> bool:
        try:
            mldsa.MLDSA87PublicKey.from_public_bytes(public).verify(signature, message)
        except (InvalidSignature, ValueError):
            return False
        return True


# LMS (RFC 8554, SP 800-208) with SHA-256/192, tree height 10 (1,024 signatures), Winternitz 4
class LmsSha256M24(Algorithm):
    id = "lms-sha256-192"
    family = POST_QUANTUM
    package = "pyhsslms"
    stateful = True
    lms_type = pyhsslms.lms_sha256_m24_h10  # RENAME: LMS TREE PARAMETER SET
    lmots_type = pyhsslms.lmots_sha256_n24_w4  # RENAME: LM-OTS PARAMETER SET

    # PURPOSE: NEW LMS KEY, SERIALIZED WITH ITS NEXT-LEAF COUNTER
    def generate(self) -> bytes:
        return pyhsslms.LmsPrivateKey(self.lms_type, self.lmots_type).serialize()

    # PURPOSE: SERIALIZED LMS PUBLIC KEY
    def public_of(self, secret: bytes) -> bytes:
        return pyhsslms.LmsPrivateKey.deserialize(secret).publicKey().serialize()

    # PURPOSE: SIGNS WITH THE NEXT UNUSED LEAF; THE RETURNED KEY BYTES CARRY THE ADVANCED COUNTER
    def sign(self, secret: bytes, message: bytes) -> tuple[bytes, bytes]:
        key = pyhsslms.LmsPrivateKey.deserialize(secret)
        signature = key.sign(message)
        return signature, key.serialize()

    # PURPOSE: CHECKS AN LMS SIGNATURE
    def verify(self, public: bytes, message: bytes, signature: bytes) -> bool:
        try:
            return pyhsslms.LmsPublicKey.deserialize(public).verify(message, signature)
        except (ValueError, IndexError):
            return False

    # PURPOSE: LEAVES NOT YET USED, READ FROM THE COUNTER AT THE END OF THE KEY BYTES
    def remaining(self, secret: bytes) -> int:
        height = pyhsslms.pyhsslms.lms_params[self.lms_type][2]
        return 2 ** height - int.from_bytes(secret[-4:], "big")


ALGORITHMS = {a.id: a for a in (EcdsaP384(), MlDsa87(), LmsSha256M24())}  # RENAME: SIGNATURE ALGORITHM REGISTRY


# PURPOSE: IN-TOTO DIGESTSET OF THE BYTES UNDER A REGISTERED HASH
def digest(data: bytes, alg: str = "sha-384") -> dict[str, str]:
    return {alg: HASHES[alg](data).hexdigest()}
