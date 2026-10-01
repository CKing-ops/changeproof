"""Crypto profiles: the named rule sets `crypto.profile` picks (ADR 002 decision 7).

The config stores only the profile name and algorithm IDs; these rules decide whether they fit.
"""

from dataclasses import dataclass

from changeproof.config import Crypto
from changeproof.signer.algorithms import ALGORITHMS, CLASSICAL, HASHES, POST_QUANTUM


@dataclass(frozen=True)
class Profile:
    signing_needs: frozenset[str]  # families evidence signing must include
    signing_allows: frozenset[str]  # families evidence signing may use
    release_allows: frozenset[str]  # families release signing may use
    hashes: frozenset[str] = frozenset({"sha-384"})  # hash IDs evidence may use; SHA-384 per CNSA 2.0 (unverified)


BOTH = frozenset({CLASSICAL, POST_QUANTUM})
PQ = frozenset({POST_QUANTUM})
PROFILES = {  # RENAME: CRYPTO PROFILE NAME TO ITS RULES
    "hybrid": Profile(BOTH, BOTH, BOTH),
    "nist-pqc": Profile(PQ, PQ, PQ),
    # classical signatures may sit beside post-quantum ones during the CNSA 2.0 transition (unverified)
    "cnsa2": Profile(PQ, BOTH, PQ),
    "classical-legacy": Profile(frozenset({CLASSICAL}), BOTH, BOTH, frozenset({"sha-384", "sha-256"})),
}


# PURPOSE: PROBLEMS WITH A CONFIG'S CRYPTO SECTION UNDER THE SIGNER REGISTRY AND ITS PROFILE
def check_crypto(crypto: Crypto) -> list[str]:
    problems = [f"crypto.signing: unknown algorithm '{a}'" for a in crypto.signing if a not in ALGORITHMS]
    if crypto.release_signing not in ALGORITHMS:
        problems.append(f"crypto.release_signing: unknown algorithm '{crypto.release_signing}'")
    if crypto.hash not in HASHES:
        problems.append(f"crypto.hash: unknown hash '{crypto.hash}'")
    profile = PROFILES.get(crypto.profile)
    if profile is None:
        return problems + [f"crypto.profile: unknown profile '{crypto.profile}' ({' | '.join(PROFILES)})"]
    families = {ALGORITHMS[a].family for a in crypto.signing if a in ALGORITHMS}
    problems += [f"crypto.signing: profile '{crypto.profile}' needs a {f} algorithm"
                 for f in sorted(profile.signing_needs - families)]
    problems += [f"crypto.signing: profile '{crypto.profile}' does not allow '{a}'"
                 for a in crypto.signing if a in ALGORITHMS and ALGORITHMS[a].family not in profile.signing_allows]
    if crypto.hash in HASHES and crypto.hash not in profile.hashes:
        problems.append(f"crypto.hash: profile '{crypto.profile}' does not allow '{crypto.hash}'")
    release = ALGORITHMS.get(crypto.release_signing)
    if release and release.family not in profile.release_allows:
        problems.append(f"crypto.release_signing: profile '{crypto.profile}' does not allow '{release.id}'")
    return problems
