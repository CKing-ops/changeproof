"""Change-risk ranking (ROADMAP Week 10, problem 2): graph features per program and a classical ML baseline.

No real defect history exists yet, so the model is trained on a seeded synthetic history whose rule
is written below. It shows the pipeline and fixes the baseline later models are compared with; it
says nothing about how well the features predict real incidents.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from changeproof.change.git import checkout_tree, git, object_line
from changeproof.config import Criticality, load_config
from changeproof.impact.run import CONFIG_NAME, component_lines, system_graph
from changeproof.solver import TopK

FEATURES = ("fan_in", "criticality", "churn", "crypto_touch")
LEVELS = {None: 0, **{c.value: n for n, c in enumerate(Criticality, 1)}}  # RENAME: CRITICALITY TO ITS ORDINAL
TRAIN_SHARE = 0.7  # RENAME: SHARE OF THE HISTORY USED FOR TRAINING; THE REST IS HELD OUT
HISTORY_ROWS = 2000  # RENAME: SYNTHETIC CHANGES GENERATED FOR EVALUATION


@dataclass(frozen=True)
class History:
    x: np.ndarray
    y: np.ndarray
    source: str


# PURPOSE: COMMITS UP TO A REVISION THAT TOUCHED A FILE, EACH CITED BY ITS COMMIT OBJECT
def churn(root: Path, revision: str, path: str) -> list[dict]:
    shas = git(root, "log", "--format=%H", revision, "--", path).decode().split()
    return [object_line(sha, 1).model_dump(exclude_none=True) for sha in shas]


# PURPOSE: FAN-IN, CRITICALITY, CHURN AND CRYPTO-TOUCH FOR EVERY PROGRAM AT A REVISION, EACH VALUE WITH ITS SOURCES
def risk_features(root: Path, revision: str, copybook_dirs: list[str] = (), config_path: str = CONFIG_NAME) -> list[dict]:
    root = Path(root)
    with tempfile.TemporaryDirectory() as scratch:
        tree = checkout_tree(root, revision, Path(scratch) / "tree")
        config_file = tree / config_path
        config = load_config(config_file) if config_file.is_file() else None
        component_at = component_lines(config_file.read_text(encoding="utf-8"))[0] if config else {}
        graph, _ = system_graph(tree, list(copybook_dirs), config)
    found = []
    for node in (n for n in graph.nodes if n.kind == "program"):
        home = node.provenance.file
        evidence = {
            "fan_in": [e.provenance.model_dump(exclude_none=True) for e in graph.edges
                       if e.dst == node.id and e.provenance.file != home],
            "criticality": [{"file": config_path, "line": component_at[c["id"]]}]
            if (c := node.attributes.get("component")) else [],
            "churn": churn(root, revision, home),
            "crypto_touch": [e.provenance.model_dump(exclude_none=True) for e in graph.edges
                             if e.kind == "uses-crypto" and e.provenance.file == home],
        }
        features = {name: len(evidence[name]) for name in FEATURES}
        features["criticality"] = LEVELS[c["criticality"] if c else None]
        found.append({"program": node.name, "provenance": node.provenance.model_dump(exclude_none=True),
                      "features": features, "evidence": evidence})
    return sorted(found, key=lambda p: p["program"])


# PURPOSE: SEEDED SYNTHETIC CHANGE HISTORY: FEATURE ROWS AND WHETHER EACH CHANGE CAUSED A DEFECT
def synthetic_history(rows: int, seed: int) -> History:
    rng = np.random.default_rng(seed)
    x = np.column_stack([rng.poisson(2, rows), rng.integers(0, 4, rows), rng.poisson(3, rows),
                         rng.binomial(1, 0.15, rows)])
    fan_in, criticality, churned, crypto = x.T
    # the hidden rule; crypto changes that are also churned are riskier than either alone
    logit = -4 + 0.35 * fan_in + 0.5 * criticality + 0.3 * churned + 1.2 * crypto + 0.3 * churned * crypto
    y = rng.random(rows) < 1 / (1 + np.exp(-logit))
    return History(x, y.astype(int), f"synthetic: seed {seed}, logit -4 + 0.35 fan_in + 0.5 criticality "
                                     f"+ 0.3 churn + 1.2 crypto_touch + 0.3 churn*crypto_touch")


# PURPOSE: FITS THE GRADIENT-BOOSTED BASELINE
def train(history: History, seed: int = 0) -> GradientBoostingClassifier:
    return GradientBoostingClassifier(random_state=seed).fit(history.x, history.y)


# PURPOSE: HELD-OUT AUC OF THE BASELINE AND OF RANKING BY FAN-IN ALONE, ON THE SAME SPLIT
def evaluate(seed: int = 0) -> dict:
    history = synthetic_history(HISTORY_ROWS, seed)
    cut = int(HISTORY_ROWS * TRAIN_SHARE)
    model = train(History(history.x[:cut], history.y[:cut], history.source), seed)
    held_x, held_y = history.x[cut:], history.y[cut:]
    return {"labels": history.source, "seed": seed, "rows": {"train": cut, "held_out": HISTORY_ROWS - cut},
            "features": list(FEATURES),
            "auc": {"gradient-boosted": round(float(roc_auc_score(held_y, model.predict_proba(held_x)[:, 1])), 4),
                    "fan-in": round(float(roc_auc_score(held_y, held_x[:, FEATURES.index("fan_in")])), 4)}}


# PURPOSE: PROGRAMS ORDERED BY PREDICTED RISK, HIGHEST FIRST, KEEPING THEIR FEATURES AND EVIDENCE
def rank(model: GradientBoostingClassifier, programs: list[dict]) -> list[dict]:
    x = np.array([[p["features"][name] for name in FEATURES] for p in programs])
    scores = model.predict_proba(x)[:, 1]
    scored = [p | {"score": round(float(s), 6)} for p, s in zip(programs, scores)]
    return sorted(scored, key=lambda p: (-p["score"], p["program"]))


# PURPOSE: THE K RISKIEST PROGRAMS TO REVIEW, AS A TOP-K PROBLEM FOR ANY SOLVER BACKEND
def review_problem(ranked: list[dict], k: int) -> TopK:
    return TopK(scores={p["program"]: p["score"] for p in ranked}, k=k)
