"""MCP server over stdio (ROADMAP Week 12): an AI agent asks the engine for evidence about a change.

JSON-RPC 2.0, one message per line on stdin and stdout, written with the standard library so the
engine gains no network client. Every tool is read-only and offline: it reads a local git
repository and returns the same predicates the CLI prints. The protocol versions are the ones the
reference Python SDK (modelcontextprotocol/python-sdk 1.30.0, `mcp/shared/version.py`) lists as
supported, read from the installed package; a third-party client has not been tried yet.
"""

import json
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

import jsonschema

from changeproof import __version__
from changeproof.change.git import checkout_tree, commits_in
from changeproof.config import load_config
from changeproof.equivalence import SCOPES, equivalence
from changeproof.graph.lineage import walk
from changeproof.impact import impact
from changeproof.impact.run import CONFIG_NAME, ENGINE, system_graph, system_modules
from changeproof.predicates import PREDICATE_TYPES, validate_predicate

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")  # RENAME: MCP VERSIONS SPOKEN, NEWEST FIRST
PRIMITIVES = {  # RENAME: CRYPTO CALL CATEGORY TO CRYPTO-INVENTORY PRIMITIVE; ANYTHING ELSE IS UNKNOWN
    "hash": "hash", "signature": "signature", "signature-generate": "signature", "signature-verify": "signature",
    "mac": "mac", "mac-generate": "mac", "mac-verify": "mac", "cipher": "cipher", "symmetric-encrypt": "cipher",
    "symmetric-decrypt": "cipher", "random": "rng", "key-agreement": "key-exchange", "kem": "kem",
}
REPO = {"type": "string", "description": "path of a local git repository"}
COPYBOOKS = {"type": "array", "items": {"type": "string"}, "description": "copybook folders, repo-relative"}
TOOL_ERRORS = (ValueError, KeyError, FileNotFoundError, RuntimeError, subprocess.CalledProcessError)


# PURPOSE: THE IMPACT PREDICATE FOR A COMMIT OR RANGE
def impact_tool(args: dict) -> dict:
    return impact(Path(args["repo"]), args["revisions"], args.get("copybooks", []), args.get("config", CONFIG_NAME))


# PURPOSE: FIELDS AND FILES A DATA ITEM FLOWS TO OR FROM AT A REVISION, EACH STEP WITH ITS LINE
def lineage_tool(args: dict) -> dict:
    root, revision = Path(args["repo"]), args.get("revision", "HEAD")
    sha = commits_in(root, revision)[-1]
    with tempfile.TemporaryDirectory() as scratch:
        tree = checkout_tree(root, sha, Path(scratch) / "tree")
        config_file = tree / args.get("config", CONFIG_NAME)
        graph, _ = system_graph(tree, args.get("copybooks", []),
                                load_config(config_file) if config_file.is_file() else None)
    nodes = {n.id: n for n in graph.nodes}
    if args["node"] not in nodes:
        raise KeyError(f"no node {args['node']} at {sha[:12]}; data items are named like data:PROGRAM.FIELD")
    direction = args.get("direction", "downstream")
    reached = walk(graph, args["node"], upstream=direction == "upstream")
    return {"revision": sha, "node": args["node"], "direction": direction, "reached": [
        {"id": node, "kind": nodes[node].kind, "name": nodes[node].name,
         "provenance": nodes[node].provenance.model_dump(mode="json"),
         "via": {"from": e.src, "to": e.dst, "provenance": e.provenance.model_dump(mode="json")}}
        for node, e in sorted(reached.items()) if node in nodes]}


# PURPOSE: THE EQUIVALENCE VERDICT FOR A CHANGE AND THE IMPACT STATEMENT IT RELIED ON
def equivalence_tool(args: dict) -> dict:
    found = equivalence(Path(args["repo"]), args["revisions"], args.get("copybooks", []),
                        args.get("config", CONFIG_NAME), args.get("scope", SCOPES[0]))
    p = found.predicate
    return {"change": p["change"], "verdict": p["verdict"], "scope": p["scope"], "summary": p["summary"],
            "untested": p["untested"], "in_impact_set": found.in_impact_set, "impact_statement": p["impact_statement"]}


# PURPOSE: A CRYPTO-INVENTORY PREDICATE OF EVERY CRYPTO CALL THE ADAPTERS FIND AT A REVISION
def crypto_tool(args: dict) -> dict:
    root = Path(args["repo"])
    sha = commits_in(root, args.get("revision", "HEAD"))[-1]
    with tempfile.TemporaryDirectory() as scratch:
        modules, _ = system_modules(checkout_tree(root, sha, Path(scratch) / "tree"), args.get("copybooks", []))
    findings = []
    for e in (e for m in modules for e in m.entities if e.kind == "crypto-call"):
        a = e.attributes
        findings.append({"id": e.id, "primitive": PRIMITIVES.get(a["category"], "unknown"),
                         "algorithm": a.get("algorithm") or "unknown",
                         "parameters": {"key_bits": a["key_bits"]} if a.get("key_bits") else {},
                         "quantum_vulnerable": a.get("quantum_vulnerable"), "migration_category": None,
                         "migration_deadline": None, "evidence": a["service"],
                         "provenance": e.provenance.model_dump(mode="json")})
    predicate = {"scope": {"revision": sha}, "findings": findings, "engine": ENGINE}
    validate_predicate(PREDICATE_TYPES["crypto-inventory"], predicate)
    return predicate


TOOLS: dict[str, tuple[str, dict, Callable[[dict], dict]]] = {  # RENAME: TOOL NAME TO (DESCRIPTION, INPUT SCHEMA, HANDLER)
    "impact": ("What a commit or range changes and what depends on it, with confidence and the source line of "
               "every step. Returns the impact predicate.",
               {"type": "object", "required": ["repo", "revisions"], "additionalProperties": False,
                "properties": {"repo": REPO, "revisions": {"type": "string", "description": "a commit or a range a..b"},
                               "config": {"type": "string"}, "copybooks": COPYBOOKS}}, impact_tool),
    "lineage": ("Fields and files whose data a COBOL data item may flow into (downstream) or come from (upstream) "
                "at a revision, each step citing its line.",
                {"type": "object", "required": ["repo", "node"], "additionalProperties": False,
                 "properties": {"repo": REPO, "node": {"type": "string", "description": "e.g. data:PROGRAM.FIELD"},
                                "revision": {"type": "string"}, "direction": {"enum": ["downstream", "upstream"]},
                                "config": {"type": "string"}, "copybooks": COPYBOOKS}}, lineage_tool),
    "equivalence_status": ("Whether behaviour outside a change's impact set stayed the same: characterization "
                           "tests from the base replayed at the head under GnuCOBOL. Untested programs are listed.",
                           {"type": "object", "required": ["repo", "revisions"], "additionalProperties": False,
                            "properties": {"repo": REPO, "revisions": {"type": "string"}, "config": {"type": "string"},
                                           "copybooks": COPYBOOKS, "scope": {"enum": list(SCOPES)}}}, equivalence_tool),
    "crypto_inventory": ("Every cryptographic call the adapters find at a revision, with algorithm, key size where "
                         "written, quantum vulnerability and line. Returns a crypto-inventory predicate.",
                         {"type": "object", "required": ["repo"], "additionalProperties": False,
                          "properties": {"repo": REPO, "revision": {"type": "string"}, "copybooks": COPYBOOKS}},
                         crypto_tool),
}


# PURPOSE: A JSON-RPC ERROR REPLY
def error(message_id, code: int, text: str) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": text}}


# PURPOSE: RUNS ONE TOOL; BAD ARGUMENTS AND FAILED ANALYSES COME BACK AS TOOL ERRORS THE AGENT CAN READ
def call_tool(params: dict) -> dict:
    _, schema, handler = TOOLS[params["name"]]
    args = params.get("arguments") or {}
    try:
        jsonschema.validate(args, schema)
        data = handler(args)
    except jsonschema.ValidationError as exc:
        return {"content": [{"type": "text", "text": f"bad arguments: {exc.message}"}], "isError": True}
    except TOOL_ERRORS as exc:
        return {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps(data, indent=2)}], "structuredContent": data, "isError": False}


# PURPOSE: THE REPLY TO ONE MESSAGE, OR NONE FOR A NOTIFICATION
def handle(message: dict) -> dict | None:
    if "id" not in message:
        return None
    message_id, method, params = message["id"], message.get("method"), message.get("params") or {}
    match method:
        case "initialize":
            asked = params.get("protocolVersion")
            result = {"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "changeproof", "version": __version__},
                      "instructions": "Evidence about code changes in local git repositories. Every fact cites "
                                      "file:line. Nothing leaves the machine."}
        case "ping":
            result = {}
        case "tools/list":
            result = {"tools": [{"name": name, "description": d, "inputSchema": schema,
                                 "annotations": {"readOnlyHint": True, "openWorldHint": False}}
                                for name, (d, schema, _) in TOOLS.items()]}
        case "tools/call":
            if params.get("name") not in TOOLS:
                return error(message_id, -32602, f"unknown tool {params.get('name')!r}")
            result = call_tool(params)
        case _:
            return error(message_id, -32601, f"method not found: {method}")
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


# PURPOSE: READS MESSAGES LINE BY LINE AND WRITES EACH REPLY AS ONE LINE, UNTIL INPUT ENDS
def serve(stdin: TextIO, stdout: TextIO) -> None:
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            reply = error(None, -32700, f"parse error: {exc}")
        else:
            reply = handle(message) if isinstance(message, dict) else error(None, -32600, "not a JSON-RPC request")
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
