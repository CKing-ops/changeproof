"""The optional changeproof-server add-on: the engine served inside a client's private network (ADR 016)."""

import http.client
import importlib.util
import json
import socket
import ssl
import threading
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from pydantic import ValidationError

from changeproof_server import ServerConfig, admits, make_server

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLE = ROOT / "docs" / "examples" / "changeproof.yaml"


def load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_server_seed", FIXTURES / name / "seed.py")
    found = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(found)
    return found


@pytest.fixture(scope="module")
def cobol(tmp_path_factory):
    root = tmp_path_factory.mktemp("server") / "cobol"
    return root, load("pack").seed(root)


# PURPOSE: AN ENGINE CONFIG FILE, HYBRID AS IN THE EXAMPLE OR CLASSICAL WITH PLAIN TLS ALLOWED
def engine_config(folder: Path, classical: bool = False) -> Path:
    text = EXAMPLE.read_text()
    if classical:
        text = text.replace("profile: hybrid", "profile: classical-legacy").replace(
            "require_pq_transport: true", "require_pq_transport: false")
    path = folder / ("classical.yaml" if classical else "hybrid.yaml")
    path.write_text(text)
    return path


# PURPOSE: A SERVER CONFIG FROM KEYWORDS, WITH A HYBRID ENGINE CONFIG UNLESS ONE IS GIVEN
def settings(tmp_path: Path, **fields) -> ServerConfig:
    base = {"listen": f"unix:{tmp_path / 'cp.sock'}", "repos": [str(tmp_path)],
            "engine_config": str(engine_config(tmp_path)), "audit_log": str(tmp_path / "audit.jsonl")}
    return ServerConfig.model_validate(base | fields)


class UnixConnection(http.client.HTTPConnection):
    # PURPOSE: AN HTTP CONNECTION OVER A UNIX SOCKET, OPTIONALLY WRAPPED IN TLS
    def __init__(self, path: str, context: ssl.SSLContext | None = None):
        super().__init__("localhost")
        self.path, self.context = path, context

    # PURPOSE: CONNECTS TO THE SOCKET FILE
    def connect(self) -> None:
        raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        raw.connect(self.path)
        self.sock = self.context.wrap_socket(raw, server_hostname="localhost") if self.context else raw


@pytest.fixture
def running():
    started = []

    # PURPOSE: STARTS A SERVER IN A THREAD AND RETURNS IT; EVERY ONE IS STOPPED AFTER THE TEST
    def start(config: ServerConfig):
        server = make_server(config)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        started.append(server)
        return server

    yield start
    for server in started:
        server.shutdown()
        server.server_close()


# PURPOSE: SENDS ONE JSON-RPC MESSAGE AND RETURNS THE HTTP STATUS AND THE REPLY
def rpc(config: ServerConfig, message: dict, context: ssl.SSLContext | None = None) -> tuple[int, dict]:
    connection = UnixConnection(config.listen.removeprefix("unix:"), context)
    connection.request("POST", "/", json.dumps(message), {"Content-Type": "application/json"})
    response = connection.getresponse()
    return response.status, json.loads(response.read())


# PURPOSE: A TOOLS/CALL MESSAGE
def tool(name: str, **arguments) -> dict:
    return {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def test_a_public_listen_address_is_refused(tmp_path):
    with pytest.raises(ValidationError, match="private"):
        settings(tmp_path, listen="8.8.8.8:8730")


def test_a_public_client_network_is_refused(tmp_path):
    with pytest.raises(ValidationError, match="private"):
        settings(tmp_path, listen="127.0.0.1:8730", allow=["10.20.0.0/16", "8.8.8.0/24"])


def test_a_private_address_needs_mutual_tls(tmp_path):
    with pytest.raises(ValidationError, match="mutual TLS"):
        settings(tmp_path, listen="10.20.0.5:8730", engine_config=str(engine_config(tmp_path, classical=True)))


def test_a_private_address_is_refused_while_the_profile_needs_post_quantum_transport(tmp_path):
    tls = {"cert": "server.pem", "key": "server.key", "client_ca": "ca.pem"}
    with pytest.raises(ValidationError, match="post-quantum"):
        settings(tmp_path, listen="10.20.0.5:8730", tls=tls)
    found = settings(tmp_path, listen="10.20.0.5:8730", tls=tls, allow=["10.20.0.0/16"],
                     engine_config=str(engine_config(tmp_path, classical=True)))
    assert found.listen == "10.20.0.5:8730"


def test_loopback_and_unix_sockets_need_no_tls_so_a_client_tls_proxy_can_sit_in_front(tmp_path):
    assert settings(tmp_path, listen="127.0.0.1:8730").tls is None
    assert settings(tmp_path).tls is None


def test_a_client_on_an_allowed_repository_gets_the_same_evidence_as_the_stdio_server(tmp_path, cobol, running):
    root, shas = cobol
    config = running(settings(tmp_path, repos=[str(root)])).config
    status, reply = rpc(config, tool("impact", repo=str(root), revisions=shas["assisted"]))
    assert status == 200 and reply["result"]["isError"] is False
    assert reply["result"]["structuredContent"]["changed"]


@pytest.mark.parametrize("arguments, reason", [
    ({"repo": "/etc", "revisions": "HEAD"}, "not served"),
    ({"revisions": "--output=/tmp/x"}, "revisions"),
    ({"revisions": "HEAD", "config": "../../changeproof.yaml"}, "inside the repository"),
    ({"revisions": "HEAD", "copybooks": ["/etc"]}, "inside the repository"),
])
def test_requests_outside_the_served_repositories_are_refused(tmp_path, cobol, running, arguments, reason):
    root, _ = cobol
    config = running(settings(tmp_path, repos=[str(root)])).config
    status, reply = rpc(config, tool("impact", **({"repo": str(root)} | arguments)))
    assert status == 403 and reason in reply["error"]["message"]


def test_every_request_is_written_to_the_audit_log(tmp_path, cobol, running):
    root, shas = cobol
    config = running(settings(tmp_path, repos=[str(root)])).config
    rpc(config, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    rpc(config, tool("impact", repo="/etc", revisions="HEAD"))
    entries = [json.loads(line) for line in Path(config.audit_log).read_text().splitlines()]
    assert [(e["method"], e["tool"], e["status"]) for e in entries] == [
        ("tools/list", None, 200), ("tools/call", "impact", 403)]
    assert all(e["time"] and "client" in e for e in entries)


# PURPOSE: A CERTIFICATE FOR A NAME, SELF-SIGNED OR SIGNED BY AN ISSUER; WRITES CERT AND KEY AND RETURNS BOTH PATHS
def certificate(folder: Path, name: str, issuer=None) -> tuple[Path, Path, tuple]:
    key = ec.generate_private_key(ec.SECP384R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    signer_name, signer_key = (issuer[0].subject, issuer[1]) if issuer else (subject, key)
    now = datetime.now(UTC)
    builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(signer_name).public_key(key.public_key())
               .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=1))
               .not_valid_after(now + timedelta(days=1))
               .add_extension(x509.BasicConstraints(ca=issuer is None, path_length=None), critical=True)
               .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False))
    cert = builder.sign(signer_key, hashes.SHA384())
    cert_path, key_path = folder / f"{name}.pem", folder / f"{name}.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return cert_path, key_path, (cert, key)


def test_with_tls_only_a_client_holding_a_certificate_from_the_client_ca_is_served(tmp_path, running):
    ca, _, ca_pair = certificate(tmp_path, "clients-ca")
    server_ca, _, server_pair = certificate(tmp_path, "server-ca")
    server_cert, server_key, _ = certificate(tmp_path, "server", server_pair)
    client_cert, client_key, _ = certificate(tmp_path, "ci-runner", ca_pair)
    config = running(settings(tmp_path, tls={"cert": str(server_cert), "key": str(server_key),
                                             "client_ca": str(ca)})).config
    trusting = ssl.create_default_context(cafile=server_ca)
    with pytest.raises((ssl.SSLError, ConnectionError)):
        rpc(config, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, trusting)
    trusting.load_cert_chain(client_cert, client_key)
    status, reply = rpc(config, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, trusting)
    assert status == 200 and reply["result"] == {}
    served = [json.loads(line) for line in Path(config.audit_log).read_text().splitlines()]
    assert [e["client"] for e in served if e["status"] == 200] == ["CN=ci-runner"]


def test_the_add_on_is_its_own_package_and_the_core_engine_never_imports_it():
    project = tomllib.loads((ROOT / "packages" / "changeproof-server" / "pyproject.toml").read_text())["project"]
    assert project["name"] == "changeproof-server"
    assert any(d.startswith("changeproof") for d in project["dependencies"])
    core = ROOT / "src" / "changeproof"
    assert not [p for p in core.rglob("*.py") if "changeproof_server" in p.read_text()]
    wheel = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert wheel["packages"] == ["src/changeproof"]


def test_tcp_clients_outside_the_allowed_networks_are_not_admitted(tmp_path):
    config = settings(tmp_path, listen="127.0.0.1:8730", allow=["10.20.0.0/16"])
    assert admits(config, "127.0.0.1") and admits(config, "10.20.4.9")
    assert not admits(config, "10.30.0.1") and not admits(config, "192.168.1.10")
