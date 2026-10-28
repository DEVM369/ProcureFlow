# Verification

ProcureFlow tests the browser workflow, MCP adapter, Agent routing, and human approval as separate execution paths. This separation ensures deterministic tests do not depend on a live ERP or external model service.

## Automated checks

| Command | Coverage |
| --- | --- |
| `python -B -m unittest discover -s tests -v` | Workflow state, validation, approval tickets, local HTTP/SSE behavior, routing policy, source-check regression |
| `python -B scripts/audit_release.py` | Selected risky-file and credential patterns; reviewed screenshot checksum |
| `node --check demo/static/app.js` | Frontend JavaScript syntax |

The GitHub Actions workflow runs these checks with Python 3.10 and 3.12. The static scanner does not replace a manual privacy or dependency-license audit.

## Local integration tests

| Module | Entry point | Expected invariant |
| --- | --- | --- |
| FastMCP adapter | `scripts/verify_mcp_read_only.py` | 8 tools discovered; 6 read-only calls; mock orders unchanged |
| Agent routing | `scripts/verify_agent_mcp_boundary.py` | Valid sub-agent partitions, invalid tasks rejected, local read tools only |
| DeepAgents execution | `scripts/verify_deepagents_graph.py` | Actual DeepAgents graph delegates to both sub-agents and reads MCP data |
| LangGraph HITL | `scripts/verify_deepagents_hitl.py` | Interrupt occurs before write; rejection writes nothing; approval writes one in-memory order; replay refused |

These four integration checks were executed on Windows on 2026-10-27 and returned PASS in local verification logs. Their dependencies and mock servers are not included in the default CI job. The deterministic model drives genuine graph nodes but cannot establish online-model performance. No test in this repository writes to a live Java ERP.

## Boundaries

The browser's displayed workflow is a separate deterministic implementation. The reference source directory is not a second runnable application. Production authentication, durable storage, live model calls and production order writes are outside the included runtime's verified scope.

Instructions: [Setup](OPERATIONS.md) · [Architecture](ARCHITECTURE.md).
