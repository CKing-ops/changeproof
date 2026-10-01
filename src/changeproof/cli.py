import argparse
import json
import sys
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import ValidationError

from changeproof import __version__
from changeproof.change import change_records
from changeproof.characterize import DockerRunner, LocalRunner, characterize, replay
from changeproof.config import Config, load_config
from changeproof.impact import impact
from changeproof.gate import gate, known_rules
from changeproof.markets import DEFAULT_MARKET, MARKETS
from changeproof.oscal import assessment_results, validate_oscal
from changeproof.predicates import PREDICATE_TYPES, statement
from changeproof.release import check_subjects, release_statement
from changeproof.signer import (ALGORITHMS, Policy, check_crypto, generate_key, load_private, load_public, resign,
                                sign_envelope, verify_envelope)

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
        config = load_config(path)
    except yaml.YAMLError as exc:
        print(f"{path}: not valid YAML: {exc}", file=sys.stderr)
        return 1
    except ValidationError as exc:
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"]) or "(root)"
            print(f"{path}: {where}: {err['msg']}", file=sys.stderr)
        return 1
    known = known_rules()
    problems = check_crypto(config.crypto) + [f"policy: unknown rule '{r.rule}' ({', '.join(sorted(known))})"
                                              for r in config.policy if r.rule not in known]
    for problem in problems:
        print(f"{path}: {problem}", file=sys.stderr)
    if problems:
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


# PURPOSE: PRINTS THE IMPACT PREDICATE FOR A COMMIT OR RANGE AS JSON, OR A SIGNED ENVELOPE WHEN KEYS ARE GIVEN
def cmd_impact(args: argparse.Namespace) -> int:
    predicate = impact(Path(args.repo), args.revisions, copybook_dirs=args.copybooks, config_path=args.config)
    if args.key:
        subject = {"name": predicate["change"]["repository"], "digest": {"gitCommit": predicate["change"]["head"]}}
        predicate = sign_envelope(statement([subject], PREDICATE_TYPES["impact"], predicate),
                                  [load_private(k) for k in args.key], datetime.now(UTC))
    print(json.dumps(predicate, indent=2))
    return 0


# PURPOSE: RUNS THE CONFIGURED POLICY RULES ON A COMMIT OR RANGE; PRINTS THE DECISION; EXIT 1 IF A RULE FAILS
def cmd_gate(args: argparse.Namespace) -> int:
    result = gate(Path(args.repo), args.revisions, copybook_dirs=args.copybooks, config_path=args.config)
    if args.oscal:
        doc = assessment_results(result, datetime.now(UTC))
        validate_oscal(doc)
        Path(args.oscal).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result.decision, indent=2))
    return 0 if result.decision["ok"] else 1


# PURPOSE: WRITES A NEW KEY PAIR; THE PRIVATE FILE IS READABLE BY ITS OWNER ONLY
def cmd_keygen(args: argparse.Namespace) -> int:
    found = generate_key(args.alg, Path(args.out))
    print(f"wrote {found.private_path} and {found.public_path} (key ID {found.keyid})")
    return 0


# PURPOSE: WRITES JSON TO THE OUTPUT FILE, OR STDOUT WITHOUT ONE
def emit(data: dict, out: str | None) -> None:
    text = json.dumps(data, indent=2) + "\n"
    if out:
        Path(out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


# PURPOSE: SIGNS A JSON STATEMENT FILE INTO A DSSE ENVELOPE
def cmd_sign(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.statement).read_text(encoding="utf-8"))
    emit(sign_envelope(payload, [load_private(k) for k in args.key], datetime.now(UTC)), args.out)
    return 0


# PURPOSE: SIGNS RELEASE ARTIFACTS: A STATEMENT OF THEIR DIGESTS IN A DSSE ENVELOPE
def cmd_release(args: argparse.Namespace) -> int:
    found = release_statement([Path(p) for p in args.artifacts], Path(args.root), args.version or __version__)
    emit(sign_envelope(found, [load_private(k) for k in args.key], datetime.now(UTC)), args.out)
    return 0


# PURPOSE: VERIFICATION POLICY FROM --DISTRUST AND --REQUIRE
def policy_of(args: argparse.Namespace) -> Policy:
    return Policy(distrusted=frozenset(args.distrust), required=frozenset(args.require))


# PURPOSE: VERIFIES AN ENVELOPE OFFLINE; PRINTS EACH SIGNATURE'S STATUS; EXIT 1 IF IT DOES NOT HOLD
def cmd_verify(args: argparse.Namespace) -> int:
    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    result = verify_envelope(envelope, [load_public(k) for k in args.trust], policy_of(args))
    subjects = check_subjects(envelope, Path(args.subjects)) if args.subjects else []
    ok = result.ok and not subjects
    print(json.dumps({"ok": ok, "signatures": [vars(r) for r in result.results], "missing": result.missing,
                      "subjects": subjects}, indent=2))
    return 0 if ok else 1


# PURPOSE: COUNTERSIGNS A VERIFIED ENVELOPE WITH NEW KEYS, LEAVING THE ORIGINAL BYTES AND SIGNATURES IN PLACE
def cmd_resign(args: argparse.Namespace) -> int:
    envelope = json.loads(Path(args.envelope).read_text(encoding="utf-8"))
    try:
        found = resign(envelope, [load_private(k) for k in args.key], [load_public(k) for k in args.trust],
                       policy_of(args), datetime.now(UTC), Path(args.log) if args.log else None)
    except ValueError as exc:
        print(f"{args.envelope}: {exc}", file=sys.stderr)
        return 1
    emit(found, args.out)
    return 0


# PURPOSE: BUILDS GOLDEN SUITES FOR COBOL SUBPROGRAMS, OR REPLAYS SAVED ONES; EXIT 1 ON A GAP OR A DIFFERENCE
def cmd_characterize(args: argparse.Namespace) -> int:
    runner = DockerRunner(args.docker) if args.docker else LocalRunner()
    root = Path(args.root)
    if args.replay:
        found = {s: replay(json.loads(Path(s).read_text(encoding="utf-8")), root, runner, args.copybooks)
                 for s in args.replay}
        print(json.dumps(found, indent=2))
        return 1 if any(found.values()) else 0
    summary = {}  # RENAME: PROGRAM NAME TO ITS COVERAGE SUMMARY
    for program in args.programs:
        suite = characterize(Path(program), root, runner, args.copybooks)
        if args.out:
            Path(args.out).mkdir(parents=True, exist_ok=True)
            (Path(args.out) / f"{suite['program']}.json").write_text(json.dumps(suite, indent=2) + "\n",
                                                                      encoding="utf-8")
        conditions = suite["conditions"]
        summary[suite["program"]] = {"conditions": len(conditions), "tests": len(suite["tests"]), "runs": suite["runs"],
                                     "both_ways": sum(len(c["covered"]) == 2 for c in conditions),
                                     "untested": [c["id"] for c in conditions if not c["tests"]]}
    print(json.dumps(summary, indent=2))
    return 1 if any(s["untested"] for s in summary.values()) else 0


# PURPOSE: ADDS --TRUST, --DISTRUST AND --REQUIRE TO A SUBCOMMAND
def add_policy(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trust", action="append", required=True, help="trusted public key file; repeatable")
    parser.add_argument("--distrust", action="append", default=[], help="algorithm ID that no longer counts")
    parser.add_argument("--require", action="append", default=[], help="algorithm ID that must hold")


# PURPOSE: DEFINES THE SUBCOMMANDS
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
    impacts.add_argument("--key", action="append", default=[], help="private key file to sign with; repeatable")
    impacts.set_defaults(func=cmd_impact)

    gates = sub.add_parser("gate", help="run the policy rules in changeproof.yaml on a commit or range")
    gates.add_argument("revisions", help="a commit, or a range such as main..HEAD")
    gates.add_argument("--repo", default=".")
    gates.add_argument("--config", default=CONFIG_NAME, help="repo-relative path of the config at the head commit")
    gates.add_argument("--copybooks", action="append", default=[], help="copybook folder, repo-relative; repeatable")
    gates.add_argument("--oscal", help="write OSCAL assessment results here, validated against the NIST schema")
    gates.set_defaults(func=cmd_gate)

    chars = sub.add_parser("characterize", help="golden tests for COBOL linkage subprograms, run under GnuCOBOL")
    chars.add_argument("programs", nargs="*", help="program source files")
    chars.add_argument("--root", default=".", help="repo root; suites cite files relative to it")
    chars.add_argument("--copybooks", action="append", default=[], help="copybook folder, root-relative; repeatable")
    chars.add_argument("--out", help="folder for one suite JSON per program; without it only the summary prints")
    chars.add_argument("--replay", action="append", default=[], help="saved suite to re-run on today's source")
    chars.add_argument("--docker", metavar="IMAGE", help="run in this GnuCOBOL image with networking off")
    chars.set_defaults(func=cmd_characterize)

    keygen = sub.add_parser("keygen", help="make a signing key pair")
    keygen.add_argument("alg", choices=sorted(ALGORITHMS))
    keygen.add_argument("--out", required=True, help="path prefix; writes <out>.key and <out>.pub.json")
    keygen.set_defaults(func=cmd_keygen)

    sign = sub.add_parser("sign", help="sign a JSON statement into a DSSE envelope")
    sign.add_argument("statement")
    sign.add_argument("--key", action="append", required=True, help="private key file; repeatable")
    sign.add_argument("-o", "--out")
    sign.set_defaults(func=cmd_sign)

    release = sub.add_parser("release", help="sign release artifacts with the release signing key")
    release.add_argument("artifacts", nargs="+")
    release.add_argument("--root", default=".", help="subjects are named relative to this folder")
    release.add_argument("--version", help="release version; defaults to the engine's")
    release.add_argument("--key", action="append", required=True, help="private key file; repeatable")
    release.add_argument("-o", "--out")
    release.set_defaults(func=cmd_release)

    verify = sub.add_parser("verify", help="verify a signed envelope offline")
    verify.add_argument("envelope")
    add_policy(verify)
    verify.add_argument("--subjects", help="folder holding the subjects; checks their digests")
    verify.set_defaults(func=cmd_verify)

    resigned = sub.add_parser("resign", help="countersign archived evidence with new keys")
    resigned.add_argument("envelope")
    resigned.add_argument("--key", action="append", required=True, help="private key file; repeatable")
    add_policy(resigned)
    resigned.add_argument("--log", help="re-signing log, one JSON line appended per run")
    resigned.add_argument("-o", "--out")
    resigned.set_defaults(func=cmd_resign)
    return parser


# PURPOSE: CLI ENTRY POINT; RETURNS THE PROCESS EXIT CODE
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
