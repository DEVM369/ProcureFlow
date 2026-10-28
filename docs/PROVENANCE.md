# Source provenance and dependencies

ProcureFlow includes a local application, adapted Agent/MCP integration code, and implementation references from the original ERP integration project. These components have different runtime and distribution requirements.

| Directory | Contents | Notes |
| --- | --- | --- |
| `demo/` | Local UI, synthetic data and HTTP/SSE workflow | Standard-library application; no production data |
| `src/mcp_server/` | Adapted FastMCP adapter | Restricted to local mock ERP; review original third-party notices before redistribution |
| `src/agent/` | Agent routing, tool access and sub-agent loading | Adapted original implementation; requires optional integration dependencies |
| `scripts/` | Integration checks and source scanner | The DeepAgents and MCP checks need a separately provisioned Python environment |
| Original ERP implementation excerpts | Excluded from current source tree | Older Git commits may retain copies; redistribution requires separate authorization |

The Java ERP service, production configuration, model credentials, private procurement reports, database dumps and supplier histories are not included. The project currently has no declared open-source license. Ownership, dependency-license and third-party attribution checks remain necessary before public redistribution. An automated source scan is not legal clearance.
