"""Week 9: behavioral-equivalence evidence. Characterization tests from the base, replayed at the head."""

import base64
import importlib.util
import json
from pathlib import Path

import pytest

from changeproof.adapters.cobol import CobolAdapter
from changeproof.characterize import LocalRunner, characterize, replay
from changeproof.cli import main
from changeproof.equivalence import equivalence, impact_statement_digest
from changeproof.predicates import PREDICATE_TYPES
from changeproof.signer import Policy, generate_key, load_public, verify_envelope

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / "corpus" / "synthetic"


def load(name):
    spec = importlib.util.spec_from_file_location(f"equivalence_{name}", HERE / "fixtures" / "equivalence" / f"{name}.py")
    found = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(found)
    return found


seeds, bugs = load("seed"), load("bugs")


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("equivalence") / "repo"
    return root, seeds.seed(root)


@pytest.fixture(scope="module")
def baselines(tmp_path_factory):
    return tmp_path_factory.mktemp("baselines")


@pytest.fixture(scope="module")
def runs(repo, baselines):
    root, shas = repo
    return {(name, scope): equivalence(root, shas[name], baselines=baselines, runner=LocalRunner(), scope=scope)
            for name in ("refactor", "rate-change") for scope in ("outside-impact-set", "full-suite")}


def targets(predicate, result=None):
    return {t["target"]["name"] for t in predicate["tests"] if result in (None, t["result"])}


def test_a_refactor_leaves_everything_outside_the_impact_set_equivalent(runs):
    found = runs["refactor", "outside-impact-set"]
    p = found.predicate
    assert (p["scope"], p["verdict"]) == ("outside-impact-set", "equivalent")
    assert targets(p) == {"RISKSCR", "INTCALC"}
    assert p["summary"]["total"] == p["summary"]["same"] > 0
    assert p["untested"] == []
    assert found.in_impact_set == ["FEECALC"]


def test_every_test_cites_the_program_it_ran_and_both_outputs(runs):
    for found in runs.values():
        for t in found.predicate["tests"]:
            where = t["target"]["provenance"]
            assert (where["file"], where["line"]) == (f"src/batch/{t['target']['name']}.cbl", 1)
            assert list(t["baseline_output"]) == list(t["candidate_output"]) == ["sha-384"]
            assert (t["result"] == "same") == (t["baseline_output"] == t["candidate_output"])


def test_the_attestation_names_the_impact_statement_it_excludes(runs):
    found = runs["refactor", "outside-impact-set"]
    assert found.predicate["impact_statement"] == impact_statement_digest(found.impact.predicate)
    assert found.predicate["change"] == found.impact.predicate["change"]


def test_an_intended_change_is_inside_the_impact_set_and_does_not_count_against_it(runs):
    assert runs["rate-change", "outside-impact-set"].predicate["verdict"] == "equivalent"
    full = runs["rate-change", "full-suite"].predicate
    assert full["verdict"] == "not-equivalent"
    assert targets(full, "different") == {"FEECALC"}
    assert full["summary"]["different"] > 0


def test_a_refactor_is_equivalent_even_on_the_program_it_changed(runs):
    p = runs["refactor", "full-suite"].predicate
    assert p["verdict"] == "equivalent"
    assert targets(p) == {"FEECALC", "RISKSCR", "INTCALC"}


def test_programs_that_cannot_be_characterized_make_the_verdict_inconclusive(tmp_path):
    shas = seeds.seed(tmp_path / "repo", packed=True)
    p = equivalence(tmp_path / "repo", shas["refactor"], runner=LocalRunner()).predicate
    assert p["verdict"] == "inconclusive"
    assert [(u["program"], u["provenance"]["file"]) for u in p["untested"]] == [("PKDCALC", "src/batch/PKDCALC.cbl")]
    assert "COMP-3" in p["untested"][0]["reason"]
    assert p["summary"]["different"] == 0


def test_baselines_are_kept_by_source_digest_and_reused(repo, baselines, runs):
    root, shas = repo
    kept = sorted(p.name.split("-")[0] for p in baselines.glob("*.json"))
    assert kept == ["FEECALC", "FEECALC", "INTCALC", "RISKSCR"]  # FEECALC before and after the refactor
    planted = next(baselines.glob("RISKSCR-*.json"))
    suite = json.loads(planted.read_text())
    suite["tests"][0]["output"]["LK-GRADE"] = "Z"
    planted.write_text(json.dumps(suite))
    p = equivalence(root, shas["refactor"], baselines=baselines, runner=LocalRunner()).predicate
    assert p["verdict"] == "not-equivalent"
    assert targets(p, "different") == {"RISKSCR"}


def test_cli_signs_the_attestation(repo, tmp_path, capsys):
    root, shas = repo
    key = generate_key("ecdsa-p384", tmp_path / "evidence")
    capsys.readouterr()
    assert main(["equivalence", shas["refactor"], "--repo", str(root), "--key", str(key.private_path)]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert verify_envelope(envelope, [load_public(key.public_path)], Policy()).ok
    signed = json.loads(base64.b64decode(envelope["payload"]))
    assert signed["predicateType"] == PREDICATE_TYPES["behavioral-equivalence"]
    assert signed["subject"][0]["digest"] == {"gitCommit": shas["refactor"]}
    assert main(["equivalence", shas["rate-change"], "--repo", str(root), "--scope", "full-suite"]) == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "not-equivalent"


@pytest.fixture(scope="module")
def originals():
    return {name: characterize(CORPUS / "batch" / f"{name}.cbl", CORPUS, LocalRunner())
            for name in ("FEECALC", "RISKSCR", "INTCALC")}


def mutant_root(tmp_path, bug):
    (tmp_path / "batch").mkdir(parents=True)
    source = (CORPUS / "batch" / f"{bug.program}.cbl").read_text()
    (tmp_path / "batch" / f"{bug.program}.cbl").write_text(bugs.apply(source, bug))
    return tmp_path


def test_every_seeded_bug_changes_behaviour_on_its_witness(tmp_path):
    for bug in bugs.BUGS:
        root = mutant_root(tmp_path / bug.id, bug)
        path = Path("batch") / f"{bug.program}.cbl"
        before = CobolAdapter([], root=CORPUS).run(CobolAdapter([]).parse(CORPUS / path, CORPUS), bug.witness)
        after = CobolAdapter([], root=root).run(CobolAdapter([]).parse(root / path, root), bug.witness)
        assert before[0].outputs != after[0].outputs, bug.id


def test_exit_check_the_tests_catch_at_least_85_percent_of_seeded_bugs(tmp_path, originals):
    caught = [bug.id for bug in bugs.BUGS if replay(originals[bug.program], mutant_root(tmp_path / bug.id, bug),
                                                     LocalRunner())]
    assert len(bugs.BUGS) == 20
    assert len(caught) / len(bugs.BUGS) >= 0.85, sorted({b.id for b in bugs.BUGS} - set(caught))


def test_held_out_bugs_written_before_the_boundary_runs_were_added(tmp_path, originals):
    for bug in bugs.HELD_OUT:
        root = mutant_root(tmp_path / "witness" / bug.id, bug)
        path = Path("batch") / f"{bug.program}.cbl"
        before = CobolAdapter([], root=CORPUS).run(CobolAdapter([]).parse(CORPUS / path, CORPUS), bug.witness)
        after = CobolAdapter([], root=root).run(CobolAdapter([]).parse(root / path, root), bug.witness)
        assert before[0].outputs != after[0].outputs, bug.id
    caught = {bug.id for bug in bugs.HELD_OUT if replay(originals[bug.program], mutant_root(tmp_path / bug.id, bug),
                                                       LocalRunner())}
    # the two misses compare a computed field (LK-FEE after COMPUTE, WS-SCORE) on its boundary
    assert {b.id for b in bugs.HELD_OUT} - caught == {"H3", "H6"}
