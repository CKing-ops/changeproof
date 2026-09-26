from pathlib import Path

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
