import base64
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from changeproof.cli import main
from changeproof.config import load_config

EXAMPLE = Path(__file__).resolve().parent.parent / "docs" / "examples" / "changeproof.yaml"


def test_init_writes_a_config_that_validates(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path), "--name", "pay-system"]) == 0
    config = load_config(tmp_path / "changeproof.yaml")
    assert config.system.name == "pay-system"
    assert config.egress.allowed is False
    assert config.optimization.backend == "classical"
    assert "changeproof.yaml" in capsys.readouterr().out


def test_init_refuses_to_overwrite_without_force(tmp_path, capsys):
    target = tmp_path / "changeproof.yaml"
    target.write_text("keep me\n")
    assert main(["init", "--dir", str(tmp_path)]) == 1
    assert target.read_text() == "keep me\n"
    assert "exists" in capsys.readouterr().err
    assert main(["init", "--dir", str(tmp_path), "--force"]) == 0
    load_config(target)


def test_init_defaults_system_name_to_directory_name(tmp_path):
    project = tmp_path / "logistics-core"
    project.mkdir()
    main(["init", "--dir", str(project)])
    assert load_config(project / "changeproof.yaml").system.name == "logistics-core"


def test_validate_accepts_the_example(capsys):
    assert main(["validate", str(EXAMPLE)]) == 0
    assert "valid" in capsys.readouterr().out


def test_validate_reports_errors_with_field_paths(tmp_path, capsys):
    data = yaml.safe_load(EXAMPLE.read_text())
    data["optimization"]["backend"] = "qpu"
    bad = tmp_path / "changeproof.yaml"
    bad.write_text(yaml.safe_dump(data))
    assert main(["validate", str(bad)]) == 1
    assert "egress.allowed" in capsys.readouterr().err


def test_validate_reports_yaml_syntax_errors(tmp_path, capsys):
    bad = tmp_path / "changeproof.yaml"
    bad.write_text("system: [unclosed\n")
    assert main(["validate", str(bad)]) == 1
    assert "changeproof.yaml" in capsys.readouterr().err


def test_schema_command_prints_json_schema(capsys):
    assert main(["schema"]) == 0
    assert '"title": "Config"' in capsys.readouterr().out


def test_init_quotes_names_that_look_like_yaml(tmp_path):
    main(["init", "--dir", str(tmp_path), "--name", "pay: {batch}", "--owner", "#office"])
    config = load_config(tmp_path / "changeproof.yaml")
    assert (config.system.name, config.system.owner) == ("pay: {batch}", "#office")


@pytest.mark.parametrize(("market", "classification"), [("general", "internal"), ("us-defense", "unclassified"), ("eu-dora", "internal")])
def test_init_writes_the_chosen_market(tmp_path, market, classification):
    assert main(["init", "--dir", str(tmp_path), "--market", market]) == 0
    config = load_config(tmp_path / "changeproof.yaml")
    assert (config.market, config.system.classification) == (market, classification)


def test_init_rejects_an_unknown_market(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["init", "--dir", str(tmp_path), "--market", "mars"])


def test_change_prints_a_record_per_commit(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("seed", Path(__file__).parent / "fixtures" / "change" / "seed.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    shas = seed.seed(tmp_path)
    assert main(["change", f"{shas[6]}..{shas[8]}", "--repo", str(tmp_path), "--copybooks", "copy"]) == 0
    records = json.loads(capsys.readouterr().out)
    assert [r["where"]["commit"] for r in records] == shas[7:9]
    assert records[1]["why"]["emergency"] is True
    assert records[1]["gaps"] == [] and "an approver is also the implementer" in records[1]["open_items"]


def test_impact_prints_the_predicate_for_a_commit(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("impact_seed", Path(__file__).parent / "fixtures" / "impact" / "seed.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    shas = dict(seed.seed(tmp_path / "repo"))
    assert main(["impact", shas["hmac-instead-of-signature"], "--repo", str(tmp_path / "repo"),
                 "--copybooks", "copy"]) == 0
    predicate = json.loads(capsys.readouterr().out)
    assert predicate["touches_crypto"] is True
    assert {"program:INVSIGN", "job:INVJOB"} <= {i["id"] for i in predicate["impacted"]}


def test_validate_checks_algorithms_against_the_signer_registry(tmp_path, capsys):
    data = yaml.safe_load(EXAMPLE.read_text())
    data["crypto"]["signing"] = ["ml-dsa-78", "ecdsa-p384"]
    bad = tmp_path / "changeproof.yaml"
    bad.write_text(yaml.safe_dump(data))
    assert main(["validate", str(bad)]) == 1
    assert "crypto.signing: unknown algorithm 'ml-dsa-78'" in capsys.readouterr().err


def test_keygen_sign_verify_and_resign(tmp_path, capsys):
    for alg in ("ml-dsa-87", "ecdsa-p384"):
        assert main(["keygen", alg, "--out", str(tmp_path / alg)]) == 0
    payload = tmp_path / "statement.json"
    payload.write_text(json.dumps({"_type": "https://in-toto.io/Statement/v1", "subject": [], "predicate": {}}))
    signed, resigned, log = tmp_path / "signed.json", tmp_path / "resigned.json", tmp_path / "resign.log"
    trust = ["--trust", str(tmp_path / "ml-dsa-87.pub.json"), "--trust", str(tmp_path / "ecdsa-p384.pub.json")]
    assert main(["sign", str(payload), "--key", str(tmp_path / "ecdsa-p384.key"), "-o", str(signed)]) == 0
    assert main(["verify", str(signed), *trust]) == 0
    assert main(["verify", str(signed), *trust, "--distrust", "ecdsa-p384"]) == 1
    assert main(["resign", str(signed), "--key", str(tmp_path / "ml-dsa-87.key"), *trust, "--log", str(log),
                 "-o", str(resigned)]) == 0
    capsys.readouterr()
    assert main(["verify", str(resigned), *trust, "--distrust", "ecdsa-p384"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert [s["status"] for s in report["signatures"]] == ["distrusted", "valid"]
    assert json.loads(signed.read_text())["payload"] == json.loads(resigned.read_text())["payload"]
    assert len(log.read_text().splitlines()) == 1


def test_release_signs_artifacts_and_verify_checks_them(tmp_path, capsys):
    assert main(["keygen", "lms-sha256-192", "--out", str(tmp_path / "release")]) == 0
    wheel = tmp_path / "changeproof-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    envelope = tmp_path / "release.dsse.json"
    assert main(["release", str(wheel), "--root", str(tmp_path), "--key", str(tmp_path / "release.key"),
                 "-o", str(envelope)]) == 0
    trust = ["--trust", str(tmp_path / "release.pub.json"), "--subjects", str(tmp_path)]
    assert main(["verify", str(envelope), *trust]) == 0
    wheel.write_bytes(b"wheel, swapped")
    capsys.readouterr()
    assert main(["verify", str(envelope), *trust]) == 1
    assert json.loads(capsys.readouterr().out)["subjects"] == ["changeproof-0.1.0-py3-none-any.whl: digest differs"]


def test_impact_signs_its_statement_with_the_given_keys(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("impact_seed", Path(__file__).parent / "fixtures" / "impact" / "seed.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    shas = dict(seed.seed(tmp_path / "repo"))
    for alg in ("ml-dsa-87", "ecdsa-p384"):
        main(["keygen", alg, "--out", str(tmp_path / alg)])
    capsys.readouterr()
    head = shas["hmac-instead-of-signature"]
    assert main(["impact", head, "--repo", str(tmp_path / "repo"), "--copybooks", "copy",
                 "--key", str(tmp_path / "ml-dsa-87.key"), "--key", str(tmp_path / "ecdsa-p384.key")]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert [s["alg"] for s in envelope["signatures"]] == ["ml-dsa-87", "ecdsa-p384"]
    stmt = json.loads(base64.b64decode(envelope["payload"]))
    assert stmt["predicateType"] == "urn:changeproof:predicate:impact:v0.1"
    assert stmt["subject"][0]["digest"] == {"gitCommit": head}
    path = tmp_path / "impact.json"
    path.write_text(json.dumps(envelope))
    assert main(["verify", str(path), "--trust", str(tmp_path / "ml-dsa-87.pub.json"),
                 "--trust", str(tmp_path / "ecdsa-p384.pub.json")]) == 0
