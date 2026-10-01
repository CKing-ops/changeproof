"""The engine makes zero network calls in its default configuration (ROADMAP Week 1)."""

import ast
import json
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "changeproof"
EXAMPLE = ROOT / "docs" / "examples" / "changeproof.yaml"

NETWORK_MODULES = {  # RENAME: STDLIB AND THIRD-PARTY MODULES THAT CAN OPEN CONNECTIONS
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib",
    "xmlrpc", "socketserver", "asyncio", "requests", "httpx", "aiohttp", "urllib3", "websockets", "grpc",
}

AUDITED = """
import sys

BLOCKED = ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname",
           "socket.sendto", "urllib.Request", "http.client.connect")
seen = []

def hook(event, args):
    if event in BLOCKED:
        seen.append(event)
        raise RuntimeError(f"network call attempted: {event}")

sys.addaudithook(hook)

from changeproof.cli import main

codes = [main(argv) for argv in ARGV]
print({"codes": codes, "network_events": seen})
"""


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_engine_package_imports_no_network_modules():
    offenders = {
        str(path.relative_to(ROOT)): sorted(imported_modules(path) & NETWORK_MODULES)
        for path in PACKAGE.rglob("*.py")
        if imported_modules(path) & NETWORK_MODULES
    }
    assert offenders == {}


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_pytest_run_has_sockets_disabled():
    with pytest.raises(Exception, match="(?i)socket"):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_default_cli_flow_makes_no_network_calls(tmp_path):
    argv = [
        ["init", "--dir", str(tmp_path), "--name", "offline-check"],
        ["validate", str(tmp_path / "changeproof.yaml")],
        ["validate", str(EXAMPLE)],
        ["schema"],
    ]
    script = f"ARGV = {argv!r}\n" + textwrap.dedent(AUDITED)
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    result = ast.literal_eval(proc.stdout.strip().splitlines()[-1])
    assert result == {"codes": [0, 0, 0, 0], "network_events": []}


def test_audit_hook_would_catch_a_connection(tmp_path):
    script = textwrap.dedent(AUDITED).replace(
        "from changeproof.cli import main", "import socket\nsocket.getaddrinfo('example.org', 443)\nmain = None"
    )
    proc = subprocess.run([sys.executable, "-c", "ARGV = []\n" + script], capture_output=True, text=True)
    assert proc.returncode != 0
    assert "network call attempted: socket.getaddrinfo" in proc.stderr


def test_predicate_schemas_resolve_without_fetching():
    from changeproof.predicates import schema_registry

    ids = {json.loads(p.read_text())["$id"] for p in (PACKAGE / "predicates" / "schemas").glob("*.json")}
    assert ids <= set(schema_registry())


def test_signing_and_verification_make_no_network_calls(tmp_path):
    statement = tmp_path / "statement.json"
    statement.write_text(json.dumps({"_type": "https://in-toto.io/Statement/v1", "subject": [], "predicate": {}}))
    argv = [["keygen", alg, "--out", str(tmp_path / alg)] for alg in ("ml-dsa-87", "ecdsa-p384", "lms-sha256-192")]
    argv += [
        ["sign", str(statement), "-o", str(tmp_path / "signed.json"),
         *[x for alg in ("ml-dsa-87", "ecdsa-p384", "lms-sha256-192") for x in ("--key", str(tmp_path / f"{alg}.key"))]],
        ["verify", str(tmp_path / "signed.json"),
         *[x for alg in ("ml-dsa-87", "ecdsa-p384", "lms-sha256-192") for x in ("--trust", str(tmp_path / f"{alg}.pub.json"))]],
    ]
    script = f"ARGV = {argv!r}\n" + textwrap.dedent(AUDITED)
    proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    result = ast.literal_eval(proc.stdout.strip().splitlines()[-1])
    assert result == {"codes": [0, 0, 0, 0, 0], "network_events": []}
