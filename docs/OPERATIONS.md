# Setup and operation

## 1. Local browser application

Requirements: Python 3.10+. From the repository root:

```bash
python -B -m demo.server --port 18881
```

Open http://127.0.0.1:18881. The server binds to the loopback interface and uses synthetic, in-memory data. Order writes are disabled by default. The optional `--allow-in-memory-writes` switch enables disposable fictional orders only; it does not call MCP or the Java ERP.

## 2. Unit tests and static checks

```bash
python -B -m unittest discover -s tests -v
python -B scripts/audit_release.py
```

If Node.js is installed, validate the frontend script with `node --check demo/static/app.js`. GitHub Actions runs these checks on pull requests and pushes.

## 3. MCP read-only integration

This optional path requires the project's external Python integration dependencies (FastMCP, LangChain MCP adapters, httpx and related packages), which are **not** installed by the standard-library quick start. Use a dedicated Python environment.

Start the local browser application on 18881 with writes disabled. In a second shell, from the repository root:

```powershell
$env:PROCUREFLOW_JAVA_API_BASE_URL = 'http://127.0.0.1:18881/api'
$env:PROCUREFLOW_MCP_PORT = '18880'
Set-Location src
python -B -m mcp_server.server_main
```

The adapter is restricted to that exact mock ERP URL, with no real ERP credentials. In a third shell, from the repository root:

```powershell
python -B scripts/verify_mcp_read_only.py
python -B scripts/verify_agent_mcp_boundary.py
python -B scripts/verify_deepagents_graph.py
```

The verification scripts invoke only the six MCP read-only tools; `order_create` and `order_update` are deliberately excluded from the Agent tool set. The DeepAgents graph uses a deterministic local chat model. It does not make live LLM requests.

## 4. HITL test

No server is required. In the same Python environment with DeepAgents/LangGraph installed, run:

```bash
python -B scripts/verify_deepagents_hitl.py
```

This test constructs a separate in-memory checkpoint and synthetic order ledger. It checks pause/resume, rejection, approval and one-use authorization. It has no network or production ERP write target.

## 5. Operational safety

- Keep the local demo and MCP server bound to 127.0.0.1. Do not expose them through a public port, reverse proxy or tunnel.
- Use synthetic data only. Do not copy `.env`, database dumps, private procurement reports or model secrets into this repository.
- Stop only processes you started yourself; never terminate other services merely because they occupy a test port.
- See [Security](../SECURITY.md) for limitations, [Verification](ACCEPTANCE.md) for test coverage and [Source provenance](PROVENANCE.md) for redistribution considerations.
