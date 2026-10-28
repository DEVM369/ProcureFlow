# Security

## Runtime boundaries

ProcureFlow's included HTTP/SSE application is a **localhost development application**, not a public production service. It does not implement user authentication, multi-tenant authorization, persistent data, rate limiting or network-facing hardening. Do not expose it through a proxy, tunnel, port forward or public network interface.

- Default browser server: `127.0.0.1:18881`, synthetic data, writes disabled.
- Optional in-memory orders: `--allow-in-memory-writes`, fictional data only.
- MCP adapter: `127.0.0.1:18880`, hard-restricted to `http://127.0.0.1:18881/api`.
- DeepAgents integration: read-only MCP capabilities with a deterministic test model.
- HITL integration: a separate, one-process synthetic order ledger; no ERP or external model connections.

The server checks the `Host` header, request origin and JSON content type. These controls do not replace authentication or protection against malicious local processes.

## Reporting

Do not paste credentials, supplier records or personal information into GitHub issues. Report suspected security issues privately to the repository maintainer. See [docs/PROVENANCE.md](docs/PROVENANCE.md) for the source/distribution boundary.
