# ADR 016: An optional server add-on for a client's private network

- Status: proposed. The owner asked for it on 2026-11-24 ("a component ... to run ... for private
  network if needed ... only as a separate capability that could be packaged with engine if requested
  by client").
- Date: 2026-11-24
- Related: ADR 002 (crypto agility), ADR 003 (data egress), ADR 010 (MCP server)

## Context

The engine is a command-line tool and an MCP server over stdio. Each machine that wants evidence has to
run the engine itself. Some clients will want one engine host that their CI runners or an internal audit
portal can ask over their own network. ADR 003 keeps all network code out of the engine package, and
CLAUDE.md rule 6 keeps every cryptographic algorithm choice inside the signer interface.

## Decision

1. **A separate package.** `packages/changeproof-server` builds its own wheel, `changeproof-server`,
   which depends on `changeproof`. The core wheel still holds only `src/changeproof`, and nothing there
   imports the add-on (`tests/test_server.py::test_the_add_on_is_its_own_package_and_the_core_engine_never_imports_it`).
   The core's no-network test is unchanged (`tests/test_offline.py`). It ships only to a client who asks.
2. **The same messages as the stdio MCP server.** One JSON-RPC message per HTTP POST, answered by
   `changeproof.mcp.handle`, so the four read-only tools and their results are the same
   (`::test_a_client_on_an_allowed_repository_gets_the_same_evidence_as_the_stdio_server`).
3. **Private only.** It listens on a Unix socket, loopback, or a private address; a public address
   is refused when the config loads, as is a public network in `allow`. TCP clients outside `allow`
   are dropped (`::test_a_public_listen_address_is_refused`, `::test_a_public_client_network_is_refused`,
   `::test_tcp_clients_outside_the_allowed_networks_are_not_admitted`). "Private" is Python's
   `ipaddress` `is_private`.
4. **Mutual TLS on a private address, with no algorithm named.** The context comes from
   `ssl.create_default_context` with a required client certificate from `tls.client_ca`; the server
   names no cipher, curve or version (`::test_a_private_address_needs_mutual_tls`,
   `::test_with_tls_only_a_client_holding_a_certificate_from_the_client_ca_is_served`).
5. **Post-quantum transport is not claimed.** The standard library does not report which key exchange
   a TLS session used. So while the engine config keeps `egress.require_pq_transport` on (it must under
   `hybrid`, `nist-pqc` and `cnsa2`), the server refuses a private address and listens only on a Unix
   socket or loopback, where the client's own post-quantum TLS proxy can sit in front
   (`::test_a_private_address_is_refused_while_the_profile_needs_post_quantum_transport`,
   `::test_loopback_and_unix_sockets_need_no_tls_so_a_client_tls_proxy_can_sit_in_front`).
6. **Only the served repositories.** A tool call must name a repository listed in `repos`; config and
   copybook paths must be relative and stay inside it; revisions may not start with `-`, so they cannot
   become git options (`::test_requests_outside_the_served_repositories_are_refused`).
7. **Audit log.** Every request, refusal and failed TLS handshake is one JSON line: time, client
   (certificate subject under TLS), method, tool, repository and status
   (`::test_every_request_is_written_to_the_audit_log`).

## Consequences

- ADR 003 gains a section: evidence may cross the client's own private network through this add-on,
  never beyond it. Nothing here sends anything to a vendor, so the egress gate does not apply.
- Under the default `hybrid` profile the network side needs the client's TLS proxy. A direct
  post-quantum listener is **planned**, for when the TLS library can show the key exchange it used.
- No new third-party dependency: the add-on uses the standard library and the engine's own
  dependencies (`docs/licenses.md`).
- The Week 14 offline bundle must keep this package out unless the client asked for it, the same way it
  keeps out `changeproof-qpu` (**planned**, with the bundle).
- The server has not been tried with a third-party MCP client over HTTP; it speaks one JSON-RPC
  message per POST, not a streaming transport.
