"""Optional add-on: the engine's read-only evidence tools served inside a client's private network (ADR 016).

The same JSON-RPC messages as the stdio MCP server, one per HTTP POST. The core package keeps no
network code (ADR 003); this package is the only one that listens, and only on a Unix socket, loopback
or a private address. Transport security is the TLS library's own defaults: no algorithm is named
here, so the signer interface stays the only place that picks one.
"""

import ipaddress
import json
import socket
import socketserver
import ssl
import sys
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path, PurePosixPath

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from changeproof.config import load_config
from changeproof.mcp import handle

MAX_BODY = 1 << 20  # RENAME: LARGEST REQUEST BODY ACCEPTED, IN BYTES
UNIX = "unix:"
SHORT = {"commonName": "CN", "organizationName": "O", "organizationalUnitName": "OU", "countryName": "C"}  # RENAME: CERTIFICATE NAME PARTS AS WRITTEN IN THE AUDIT LOG
Network = ipaddress.IPv4Network | ipaddress.IPv6Network


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Tls(Strict):
    cert: Path
    key: Path
    client_ca: Path  # RENAME: CA THAT ISSUES THE CERTIFICATES CLIENTS MUST PRESENT


class ServerConfig(Strict):
    listen: str
    allow: list[Network] = []
    repos: list[Path] = Field(min_length=1)
    engine_config: Path
    audit_log: Path
    tls: Tls | None = None

    # PURPOSE: THE HOST AND PORT OF A TCP LISTEN ADDRESS, OR NONE FOR A UNIX SOCKET
    @property
    def address(self) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, int] | None:
        if self.listen.startswith(UNIX):
            return None
        host, _, port = self.listen.rpartition(":")
        return ipaddress.ip_address(host.strip("[]")), int(port)

    # PURPOSE: REFUSES PUBLIC ADDRESSES, AND A PRIVATE ONE WITHOUT MUTUAL TLS OR WHILE POST-QUANTUM TRANSPORT IS REQUIRED
    @model_validator(mode="after")
    def private_only(self) -> "ServerConfig":
        if self.address is None:
            return self
        host = self.address[0]
        if not (host.is_private or host.is_loopback):
            raise ValueError(f"listen address {host} is not private; the server never listens on a public address")
        if public := [str(n) for n in self.allow if not n.is_private]:
            raise ValueError(f"allow lists networks that are not private: {', '.join(public)}")
        if host.is_loopback:
            return self
        if self.tls is None:
            raise ValueError(f"listening on {host} needs mutual TLS: set tls.cert, tls.key and tls.client_ca")
        if load_config(self.engine_config).egress.require_pq_transport:
            # the standard library cannot show which key exchange a TLS session used
            raise ValueError("the engine config requires post-quantum transport, which this server cannot prove; "
                             "listen on a Unix socket or loopback behind a post-quantum TLS proxy")
        return self


# PURPOSE: LOADS AND VALIDATES CHANGEPROOF-SERVER.YAML
def load_server_config(path: Path) -> ServerConfig:
    return ServerConfig.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


# PURPOSE: TRUE WHEN A TCP CLIENT ADDRESS IS LOOPBACK OR IN ONE OF THE ALLOWED NETWORKS
def admits(config: ServerConfig, host: str) -> bool:
    address = ipaddress.ip_address(host)
    return address.is_loopback or any(address in network for network in config.allow)


# PURPOSE: TRUE WHEN A PATH ARGUMENT IS RELATIVE AND STAYS INSIDE THE REPOSITORY
def inside(path: str) -> bool:
    found = PurePosixPath(path)
    return not found.is_absolute() and ".." not in found.parts


# PURPOSE: WHY A MESSAGE MAY NOT RUN ON THIS SERVER, OR NONE
def refusal(config: ServerConfig, message: dict) -> str | None:
    if message.get("method") != "tools/call":
        return None
    args = (message.get("params") or {}).get("arguments") or {}
    served = {p.resolve() for p in config.repos}
    if "repo" in args and Path(str(args["repo"])).resolve() not in served:
        return f"repository {args['repo']} is not served here"
    for key in ("revisions", "revision"):
        if str(args.get(key, "")).startswith("-"):
            return f"{key} may not start with '-'"
    paths = [args.get("config", "")] + list(args.get("copybooks", []))
    if not all(inside(str(p)) for p in paths if p):
        return "config and copybook paths must stay inside the repository"
    return None


class Handler(BaseHTTPRequestHandler):
    server: "socketserver.BaseServer"

    # PURPOSE: ANSWERS ONE JSON-RPC MESSAGE, REFUSING WHAT THE CONFIG DOES NOT SERVE, AND AUDITS IT
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self.reply(413, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "too large"}}, {})
        try:
            message = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            return self.reply(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}, {})
        if not isinstance(message, dict):
            return self.reply(400, {"jsonrpc": "2.0", "id": None,
                                    "error": {"code": -32600, "message": "not a JSON-RPC request"}}, {})
        if reason := refusal(self.server.config, message):
            body = {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32602, "message": reason}}
            return self.reply(403, body, message)
        self.reply(200, handle(message) or {}, message)

    # PURPOSE: WRITES ONE AUDIT LINE, THEN THE REPLY
    def reply(self, status: int, body: dict, message: dict) -> None:
        params = message.get("params") or {}
        self.server.audit({"method": message.get("method"), "tool": params.get("name"),
                           "repo": (params.get("arguments") or {}).get("repo"), "status": status},
                          self.connection, self.client_address)
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # PURPOSE: KEEPS REQUEST LINES OFF STDERR; THE AUDIT LOG RECORDS THEM
    def log_message(self, format: str, *args) -> None:
        pass


class Serving:
    config: ServerConfig
    context: ssl.SSLContext | None
    lock: threading.Lock

    # PURPOSE: WRAPS EACH ACCEPTED CONNECTION IN TLS WHEN CONFIGURED; THE HANDSHAKE RUNS IN THE HANDLER THREAD
    def get_request(self):
        connection, address = super().get_request()
        if self.context:
            connection = self.context.wrap_socket(connection, server_side=True, do_handshake_on_connect=False)
        return connection, address

    # PURPOSE: TCP CLIENTS OUTSIDE THE ALLOWED NETWORKS ARE DROPPED AND AUDITED
    def verify_request(self, request, client_address) -> bool:
        if isinstance(client_address, tuple) and not admits(self.config, client_address[0]):
            self.audit({"method": None, "tool": None, "repo": None, "status": "network-refused"}, request, client_address)
            return False
        return True

    # PURPOSE: A FAILED TLS HANDSHAKE IS AUDITED, NOT PRINTED
    def handle_error(self, request, client_address) -> None:
        error = sys.exc_info()[1]
        if isinstance(error, (ssl.SSLError, ConnectionError)):
            self.audit({"method": None, "tool": None, "repo": None, "status": "tls-refused"}, None, client_address)
        else:
            super().handle_error(request, client_address)

    # PURPOSE: APPENDS ONE JSON LINE TO THE AUDIT LOG
    def audit(self, entry: dict, connection, client_address) -> None:
        line = {"time": datetime.now(UTC).isoformat(), "client": client_name(connection, client_address)} | entry
        with self.lock, self.config.audit_log.open("a", encoding="utf-8") as log:
            log.write(json.dumps(line) + "\n")


class UnixServer(Serving, socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


class TcpServer(Serving, socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class Tcp6Server(TcpServer):
    address_family = socket.AF_INET6


# PURPOSE: WHO A CLIENT IS: ITS CERTIFICATE SUBJECT UNDER TLS, ELSE ITS ADDRESS, ELSE LOCAL
def client_name(connection, client_address) -> str:
    if isinstance(connection, ssl.SSLSocket) and (cert := connection.getpeercert()):
        return ",".join(f"{SHORT.get(k, k)}={v}" for rdn in cert["subject"] for k, v in rdn)
    return client_address[0] if isinstance(client_address, tuple) else "local"


# PURPOSE: THE TLS CONTEXT THAT DEMANDS A CLIENT CERTIFICATE FROM THE CLIENT CA, WITH THE LIBRARY'S DEFAULTS
def tls_context(tls: Tls) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH, cafile=tls.client_ca)
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(tls.cert, tls.key)
    return context


# PURPOSE: A BOUND SERVER FOR THE CONFIG, READY FOR SERVE_FOREVER
def make_server(config: ServerConfig) -> socketserver.BaseServer:
    if config.address is None:
        path = Path(config.listen.removeprefix(UNIX))
        if path.is_socket():
            path.unlink()  # a socket left by an earlier run; any other file there stops the bind
        server = UnixServer(str(path), Handler)
    else:
        host, port = config.address
        server = (Tcp6Server if host.version == 6 else TcpServer)((str(host), port), Handler)
    server.config, server.lock = config, threading.Lock()
    server.context = tls_context(config.tls) if config.tls else None
    return server


# PURPOSE: COMMAND LINE: CHANGEPROOF-SERVER <CONFIG>
def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: changeproof-server <changeproof-server.yaml>", file=sys.stderr)
        return 2
    server = make_server(load_server_config(Path(args[0])))
    print(f"changeproof-server listening on {server.config.listen}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
