"""Week 6 exit check: signature size and speed for each algorithm and for the hybrid envelope.

    uv run python scripts/signer_benchmark.py

Times are medians over ROUNDS runs on the machine that ran the script. Writes
docs/weekly/week06-signer-benchmark.json.
"""

import json
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from changeproof.signer import ALGORITHMS, Policy, generate_key, load_private, load_public, sign_envelope, verify_envelope

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "docs" / "weekly" / "week06-signer-benchmark.json"
ROUNDS = 20  # RENAME: TIMED RUNS PER MEASUREMENT
PAYLOAD = json.dumps({"_type": "https://in-toto.io/Statement/v1", "subject": [], "predicate": {"x": "y" * 4000}})
SETUPS = {"classical": ["ecdsa-p384"], "ml-dsa-87": ["ml-dsa-87"], "hybrid": ["ml-dsa-87", "ecdsa-p384"],
          "lms": ["lms-sha256-192"]}  # RENAME: ROADMAP SIGNER SETUPS


# PURPOSE: MEDIAN MILLISECONDS FOR A CALL OVER ROUNDS RUNS
def median_ms(call, rounds: int = ROUNDS) -> float:
    times = []
    for _ in range(rounds):
        start = time.perf_counter()
        call()
        times.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(times), 3)


# PURPOSE: MEASURES EACH ALGORITHM AND EACH SETUP'S ENVELOPE, WRITES THE REPORT
def main() -> int:
    payload = json.loads(PAYLOAD)
    rows, setups = {}, {}
    with tempfile.TemporaryDirectory() as scratch:
        files = {}
        for alg, algorithm in ALGORITHMS.items():
            keygen_ms = median_ms(lambda: generate_key(alg, Path(scratch) / f"{alg}-timing"), 3)
            files[alg] = generate_key(alg, Path(scratch) / alg)
            key, public = load_private(files[alg].private_path), load_public(files[alg].public_path)
            message = PAYLOAD.encode()
            signature = key.sign(message)
            rows[alg] = {
                "family": algorithm.family, "library": algorithm.library, "stateful": algorithm.stateful,
                "public_key_bytes": len(public.public), "signature_bytes": len(signature),
                "keygen_ms": keygen_ms, "sign_ms": median_ms(lambda: key.sign(message)),
                "verify_ms": median_ms(lambda: algorithm.verify(public.public, message, signature)),
            }
        trusted = [load_public(f.public_path) for f in files.values()]
        for name, algs in SETUPS.items():
            keys = [load_private(files[a].private_path) for a in algs]
            envelope = sign_envelope(payload, keys, datetime.now(UTC))
            setups[name] = {"algorithms": algs, "envelope_bytes": len(json.dumps(envelope)),
                            "verify_ms": median_ms(lambda: verify_envelope(envelope, trusted, Policy()))}
    report = {"rounds": ROUNDS, "payload_bytes": len(PAYLOAD), "python": platform.python_version(),
              "machine": f"{platform.machine()}, {os.cpu_count()} CPUs", "algorithms": rows, "envelopes": setups}
    REPORT.write_text(json.dumps(report, indent=1) + "\n")
    for alg, row in rows.items():
        print(f"{alg:16} sig {row['signature_bytes']:6} B  sign {row['sign_ms']:8.3f} ms  verify {row['verify_ms']:8.3f} ms"
              f"  keygen {row['keygen_ms']:9.3f} ms")
    for name, row in setups.items():
        print(f"{name:16} envelope {row['envelope_bytes']:6} B  verify {row['verify_ms']:8.3f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
