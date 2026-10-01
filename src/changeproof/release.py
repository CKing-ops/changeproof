"""The engine's own release artifacts as an in-toto statement, for signing with `crypto.release_signing`."""

import base64
import json
from pathlib import Path

from changeproof.predicates import PREDICATE_TYPES, statement
from changeproof.signer import HASHES, digest


# PURPOSE: STATEMENT WHOSE SUBJECTS ARE THE ARTIFACTS, NAMED RELATIVE TO ROOT, WITH THEIR DIGESTS
def release_statement(paths: list[Path], root: Path, version: str) -> dict:
    subjects = [{"name": Path(p).resolve().relative_to(Path(root).resolve()).as_posix(),
                 "digest": digest(Path(p).read_bytes())} for p in paths]
    return statement(subjects, PREDICATE_TYPES["release"], {"product": {"name": "changeproof", "version": version}})


# PURPOSE: SUBJECTS OF A SIGNED STATEMENT WHOSE FILE UNDER ROOT IS MISSING OR NO LONGER MATCHES
def check_subjects(envelope: dict, root: Path) -> list[str]:
    problems = []
    for subject in json.loads(base64.b64decode(envelope["payload"]))["subject"]:
        path = Path(root) / subject["name"]
        if not path.is_file():
            problems.append(f"{subject['name']}: missing")
            continue
        alg, expected = next(iter(subject["digest"].items()))
        if alg not in HASHES:
            problems.append(f"{subject['name']}: unknown hash '{alg}'")
        elif digest(path.read_bytes(), alg)[alg] != expected:
            problems.append(f"{subject['name']}: digest differs")
    return problems
