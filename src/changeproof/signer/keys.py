"""Key files. A private key file holds its algorithm ID, so a signature always knows what made it."""

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path

from changeproof.signer.algorithms import ALGORITHMS, Algorithm, digest

PRIVATE_SUFFIX = ".key"
PUBLIC_SUFFIX = ".pub.json"


@dataclass(frozen=True)
class PublicKey:
    alg: str
    keyid: str
    public: bytes


@dataclass
class PrivateKey:
    alg: str
    keyid: str
    secret: bytes
    path: Path

    # PURPOSE: THE REGISTERED ALGORITHM THIS KEY BELONGS TO
    @property
    def algorithm(self) -> Algorithm:
        return ALGORITHMS[self.alg]

    # PURPOSE: SIGNATURES LEFT ON A STATEFUL KEY; NONE FOR STATELESS ONES
    @property
    def remaining(self) -> int | None:
        return self.algorithm.remaining(self.secret)

    # PURPOSE: SIGNS A MESSAGE; A STATEFUL KEY IS SAVED WITH ITS ADVANCED STATE BEFORE THE SIGNATURE IS RETURNED
    def sign(self, message: bytes) -> bytes:
        signature, self.secret = self.algorithm.sign(self.secret, message)
        if self.algorithm.stateful:
            write_private(self)
        return signature


@dataclass(frozen=True)
class KeyFiles:
    keyid: str
    private_path: Path
    public_path: Path


# PURPOSE: KEY ID: SHA-384 OF THE ALGORITHM ID AND THE PUBLIC KEY BYTES
def key_id(alg: str, public: bytes) -> str:
    return digest(alg.encode() + b"\0" + public)["sha-384"]


# PURPOSE: WRITES A FILE READABLE BY ITS OWNER ONLY, REPLACING ANY OLD ONE IN ONE STEP
def write_secret(path: Path, text: str) -> None:
    scratch = path.with_name(path.name + ".tmp")
    fd = os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(text)
        out.flush()
        os.fsync(out.fileno())
    os.replace(scratch, path)


# PURPOSE: SAVES A PRIVATE KEY TO ITS PATH
def write_private(key: PrivateKey) -> None:
    write_secret(key.path, json.dumps({"alg": key.alg, "keyid": key.keyid,
                                       "private": base64.b64encode(key.secret).decode()}) + "\n")


# PURPOSE: MAKES A KEY PAIR AND WRITES <PREFIX>.KEY (OWNER ONLY) AND <PREFIX>.PUB.JSON
def generate_key(alg: str, prefix: Path) -> KeyFiles:
    if alg not in ALGORITHMS:
        raise ValueError(f"unknown algorithm '{alg}' ({', '.join(ALGORITHMS)})")
    algorithm = ALGORITHMS[alg]
    secret = algorithm.generate()
    public = algorithm.public_of(secret)
    keyid = key_id(alg, public)
    prefix = Path(prefix)
    private_path = prefix.with_name(prefix.name + PRIVATE_SUFFIX)
    public_path = prefix.with_name(prefix.name + PUBLIC_SUFFIX)
    write_private(PrivateKey(alg, keyid, secret, private_path))
    public_path.write_text(json.dumps({"alg": alg, "keyid": keyid, "public": base64.b64encode(public).decode()},
                                      indent=1) + "\n", encoding="utf-8")
    return KeyFiles(keyid, private_path, public_path)


# PURPOSE: READS A PRIVATE KEY FILE
def load_private(path: Path) -> PrivateKey:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return PrivateKey(data["alg"], data["keyid"], base64.b64decode(data["private"]), Path(path))


# PURPOSE: READS A PUBLIC KEY FILE AND CHECKS ITS KEY ID MATCHES ITS CONTENT
def load_public(path: Path) -> PublicKey:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    public = base64.b64decode(data["public"])
    if key_id(data["alg"], public) != data["keyid"]:
        raise ValueError(f"{path}: key ID does not match the key")
    return PublicKey(data["alg"], data["keyid"], public)
