# changeproof-server

Optional add-on, shipped only when a client asks for it. It serves the engine's read-only evidence tools
(`impact`, `lineage`, `equivalence_status`, `crypto_inventory`) to other machines inside the client's own
private network, such as CI runners or an internal audit portal. The messages are the same JSON-RPC the
stdio MCP server speaks (`changeproof mcp`), one per HTTP POST.

The core `changeproof` package stays free of network code (ADR 003); this package is the only one
that listens. Rules, checked when the config loads (ADR 016, `tests/test_server.py`):

- It listens on a Unix socket, a loopback address or a private address. A public address is refused.
- Client networks in `allow` must be private; requests from anywhere else get 403.
- On a private address it needs mutual TLS: a server certificate and a CA for client certificates.
- While the engine config needs post-quantum transport (`egress.require_pq_transport`, on under the
  `hybrid`, `nist-pqc` and `cnsa2` profiles), it listens only on a Unix socket or loopback. Put the
  client's own TLS proxy in front for the network side.
- It answers only about the repositories listed in `repos`; config and copybook paths must stay inside
  the repository, and revisions may not start with `-`.
- Every request goes to the audit log as one JSON line: time, client, method, tool, repository, status.

```yaml
# changeproof-server.yaml
listen: unix:/run/changeproof/cp.sock   # or 127.0.0.1:8730, or a private address with tls
allow: [10.20.0.0/16]                   # client networks on a private address
repos: [/srv/repos/core-banking]
engine_config: /srv/repos/core-banking/changeproof.yaml
audit_log: /var/log/changeproof/server.jsonl
tls:                                     # needed on a private address
  cert: /etc/changeproof/server.pem
  key: /etc/changeproof/server.key
  client_ca: /etc/changeproof/clients-ca.pem
```

```sh
changeproof-server changeproof-server.yaml
```
