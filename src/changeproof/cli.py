import argparse
import json
import sys
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import ValidationError

from changeproof.change import change_records
from changeproof.config import Config, load_config
from changeproof.impact import impact
from changeproof.markets import DEFAULT_MARKET, MARKETS

CONFIG_NAME = "changeproof.yaml"


# PURPOSE: WRITES A STARTER CHANGEPROOF.YAML WITH EGRESS DENIED
def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.dir) / CONFIG_NAME
    if target.exists() and not args.force:
        print(f"{target} exists; use --force to overwrite", file=sys.stderr)
        return 1
    name = args.name or Path(args.dir).resolve().name  # RENAME: SYSTEM NAME WRITTEN INTO THE FILE
    template = files("changeproof").joinpath("templates", CONFIG_NAME).read_text(encoding="utf-8")
    profile = MARKETS[args.market]  # RENAME: MARKET PROFILE THE STARTER FILE IS WRITTEN FOR
    # json.dumps gives a quoted scalar that YAML reads back unchanged
    text = template.format(  # RENAME: FILLED-IN STARTER CONFIG
        name=json.dumps(name),
        owner=json.dumps(args.owner),
        market=profile.name,
        classification=profile.default_classification,
        classifications=" | ".join(profile.classifications),
        frameworks=json.dumps(list(profile.frameworks)),
    )
    target.write_text(text, encoding="utf-8")
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


# PURPOSE: PRINTS CHANGE RECORDS FOR A COMMIT OR RANGE AS JSON; EXIT 1 IF ANY RECORD HAS A GAP
def cmd_change(args: argparse.Namespace) -> int:
    repo = Path(args.repo)
    config_path = Path(args.config) if args.config else repo / CONFIG_NAME
    config = load_config(config_path) if config_path.is_file() else None  # RENAME: CONFIG GIVING SYSTEM AND COMPONENTS
    records = change_records(repo, args.revisions, copybook_dirs=args.copybooks, config=config)
    print(json.dumps([r.model_dump(mode="json") | {"gaps": r.gaps(), "open_items": r.open_items()} for r in records],
                     indent=2))
    return 1 if any(r.gaps() for r in records) else 0


# PURPOSE: PRINTS THE IMPACT PREDICATE FOR A COMMIT OR RANGE AS JSON
def cmd_impact(args: argparse.Namespace) -> int:
    print(json.dumps(impact(Path(args.repo), args.revisions, copybook_dirs=args.copybooks, config_path=args.config),
                     indent=2))
    return 0


# PURPOSE: DEFINES THE INIT, VALIDATE, SCHEMA, CHANGE AND IMPACT SUBCOMMANDS
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="changeproof")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="write a starter changeproof.yaml")
    init.add_argument("--dir", default=".")
    init.add_argument("--name")
    init.add_argument("--owner", default="unassigned")
    init.add_argument("--market", choices=sorted(MARKETS), default=DEFAULT_MARKET)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    validate = sub.add_parser("validate", help="check a changeproof.yaml")
    validate.add_argument("path", nargs="?", default=CONFIG_NAME)
    validate.set_defaults(func=cmd_validate)

    schema = sub.add_parser("schema", help="print the config JSON Schema")
    schema.set_defaults(func=cmd_schema)

    change = sub.add_parser("change", help="print who/what/when/where/how/why records for commits")
    change.add_argument("revisions", help="a commit, or a range such as main..HEAD")
    change.add_argument("--repo", default=".")
    change.add_argument("--config", help=f"defaults to {CONFIG_NAME} in the repository")
    change.add_argument("--copybooks", action="append", default=[], help="copybook folder, repo-relative; repeatable")
    change.set_defaults(func=cmd_change)

    impacts = sub.add_parser("impact", help="print what a commit or range impacts, with confidence and paths")
    impacts.add_argument("revisions", help="a commit, or a range such as main..HEAD")
    impacts.add_argument("--repo", default=".")
    impacts.add_argument("--config", default=CONFIG_NAME, help="repo-relative path of the config at the head commit")
    impacts.add_argument("--copybooks", action="append", default=[], help="copybook folder, repo-relative; repeatable")
    impacts.set_defaults(func=cmd_impact)
    return parser


# PURPOSE: CLI ENTRY POINT; RETURNS THE PROCESS EXIT CODE
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
