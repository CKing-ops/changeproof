"""Week 12: the MCP server, so an AI agent can ask the engine for evidence over stdio, offline."""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from changeproof.mcp import PROTOCOL_VERSIONS, serve
from changeproof.predicates import PREDICATE_TYPES, validate_predicate

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    spec = importlib.util.spec_from_file_location(f"{name.replace('/', '_')}_seed", FIXTURES / name / "seed.py")
    found = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(found)
    return found


@pytest.fixture(scope="module")
def cobol(tmp_path_factory):
    root = tmp_path_factory.mktemp("mcp") / "cobol"
    return root, load("pack").seed(root)


@pytest.fixture(scope="module")
def java(tmp_path_factory):
    root = tmp_path_factory.mktemp("mcp") / "java"
    return root, dict(load("java").seed(root))


def session(*messages: dict) -> list[dict]:
    out = io.StringIO()
    serve(io.StringIO("".join(json.dumps(m) + "\n" for m in messages)), out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


def call(tool: str, **arguments) -> dict:
    [reply] = session({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": tool, "arguments": arguments}})
    assert reply["id"] == 7
    return reply["result"]


def test_a_client_starts_a_session_over_stdio_and_lists_four_read_only_tools():
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
    ]
    proc = subprocess.run([sys.executable, "-m", "changeproof", "mcp"], input="".join(json.dumps(m) + "\n" for m in messages),
                          capture_output=True, text=True, timeout=60, check=True)
    init, tools, ping = [json.loads(line) for line in proc.stdout.splitlines()]
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert init["result"]["serverInfo"]["name"] == "changeproof"
    assert init["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert [t["name"] for t in tools["result"]["tools"]] == ["impact", "lineage", "equivalence_status", "crypto_inventory"]
    for tool in tools["result"]["tools"]:
        assert tool["inputSchema"]["type"] == "object" and "repo" in tool["inputSchema"]["required"]
        assert tool["annotations"] == {"readOnlyHint": True, "openWorldHint": False}
    assert ping == {"jsonrpc": "2.0", "id": 3, "result": {}}


def test_an_unknown_protocol_version_gets_the_newest_one_the_server_speaks():
    [reply] = session({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
    assert reply["result"]["protocolVersion"] == PROTOCOL_VERSIONS[0]


def test_impact_returns_the_impact_predicate_with_the_agent_named(cobol):
    root, shas = cobol
    result = call("impact", repo=str(root), revisions=shas["assisted"])
    assert result["isError"] is False
    found = result["structuredContent"]
    validate_predicate(PREDICATE_TYPES["impact"], found)
    assert json.loads(result["content"][0]["text"]) == found
    assert {"role": "agent", "id": "feebot@tools.example",
            "source": f"Assisted-by trailer, git-commit/{shas['assisted']}:8"} in found["who"]


def test_lineage_follows_a_field_downstream_with_the_line_of_each_step(cobol):
    root, shas = cobol
    found = call("lineage", repo=str(root), revision=shas["base"], node="data:FEECALC.LK-AMOUNT")["structuredContent"]
    assert found["revision"] == shas["base"] and found["direction"] == "downstream"
    reached = {r["id"]: r for r in found["reached"]}
    assert "data:FEECALC.LK-FEE" in reached
    step = reached["data:FEECALC.LK-FEE"]["via"]
    assert step["provenance"]["file"] == "src/batch/FEECALC.cbl" and step["provenance"]["line"] >= 1


def test_lineage_of_an_unknown_node_is_an_error_the_agent_can_read(cobol):
    root, shas = cobol
    result = call("lineage", repo=str(root), node="data:NOPE.X")
    assert result["isError"] is True
    assert "data:NOPE.X" in result["content"][0]["text"]


def test_equivalence_status_reports_the_verdict_and_the_impact_statement_it_relied_on(cobol):
    root, shas = cobol
    found = call("equivalence_status", repo=str(root), revisions=shas["co-authored"])["structuredContent"]
    assert found["verdict"] == "equivalent"
    assert found["in_impact_set"] == ["FEECALC"]
    assert found["summary"]["different"] == 0 and found["summary"]["total"] > 0
    assert set(found["impact_statement"]) == {"sha-384"}


def test_crypto_inventory_lists_each_crypto_use_with_its_line(java):
    root, shas = java
    found = call("crypto_inventory", repo=str(root), revision=shas["rsa-receipts"])["structuredContent"]
    validate_predicate(PREDICATE_TYPES["crypto-inventory"], found)
    assert found["scope"]["revision"] == shas["rsa-receipts"]
    by_service = {f["evidence"]: f for f in found["findings"]}
    rsa = by_service["java.security.KeyPairGenerator"]
    assert (rsa["primitive"], rsa["algorithm"], rsa["parameters"], rsa["quantum_vulnerable"]) == (
        "unknown", "rsa", {"key_bits": 2048}, True)
    assert by_service["java.security.MessageDigest"]["primitive"] == "hash"
    assert all(f["provenance"]["file"].endswith(".java") for f in found["findings"])


def test_bad_arguments_and_unknown_tools_are_reported_not_raised():
    assert call("impact", revisions="HEAD")["isError"] is True
    [reply] = session({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "deploy", "arguments": {}}})
    assert reply["error"]["code"] == -32602
    [reply] = session({"jsonrpc": "2.0", "id": 2, "method": "resources/list"})
    assert reply["error"]["code"] == -32601
    out = io.StringIO()
    serve(io.StringIO("not json\n"), out)
    assert json.loads(out.getvalue())["error"]["code"] == -32700
