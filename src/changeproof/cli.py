import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import ValidationError

from changeproof.config import Config, load_config

CONFIG_NAME = "changeproof.yaml"


# PURPOSE: WRITES A STARTER CHANGEPROOF.YAML WITH EGRESS DENIED
def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.dir) / CONFIG_NAME
    if target.exists() and not args.force:
        print(f"{target} exists; use --force to overwrite", file=sys.stderr)
        return 1
    name = args.name or Path(args.dir).resolve().name  # RENAME: SYSTEM NAME WRITTEN INTO THE FILE
    template = files("changeproof").joinpath("templates", CONFIG_NAME).read_text(encoding="utf-8")
    # json.dumps gives a quoted scalar that YAML reads back unchanged
    target.write_text(template.format(name=json.dumps(name), owner=json.dumps(args.owner)), encoding="utf-8")
    load_config(target)
    print(f"wrote {target}")
    return 0


# PURPOSE: CHECKS A CONFIG FILE AND PRINTS EACH PROBLEM WITH ITS FIELD PATH
def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    try:
        load_config(path)
    except yaml.YAMLError as exc:
        print(f"{path}: not valid YAML: {exc}", file=sys.stderr)
        return 1
    except ValidationError as exc:
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"]) or "(root)"
            print(f"{path}: {where}: {err['msg']}", file=sys.stderr)
        return 1
    print(f"{path}: valid")
    return 0


# PURPOSE: PRINTS THE JSON SCHEMA GENERATED FROM THE PYDANTIC MODELS
def cmd_schema(args: argparse.Namespace) -> int:
    print(json.dumps(Config.model_json_schema(), indent=2))
    return 0


# PURPOSE: DEFINES THE INIT, VALIDATE AND SCHEMA SUBCOMMANDS
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="changeproof")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="write a starter changeproof.yaml")
    init.add_argument("--dir", default=".")
    init.add_argument("--name")
    init.add_argument("--owner", default="unassigned")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    validate = sub.add_parser("validate", help="check a changeproof.yaml")
    validate.add_argument("path", nargs="?", default=CONFIG_NAME)
    validate.set_defaults(func=cmd_validate)

    schema = sub.add_parser("schema", help="print the config JSON Schema")
    schema.set_defaults(func=cmd_schema)
    return parser


# PURPOSE: CLI ENTRY POINT; RETURNS THE PROCESS EXIT CODE
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
