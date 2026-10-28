"""Authorized source adaptation: MCP tool loader restricted to offline mock.

This preserves the original Agent's four-tuple tool-grouping contract while
removing its hard-coded production port and remote analysis MCP endpoint.
No Qwen/model initialization occurs here. This is the Agent's MCP loading
boundary, not a complete DeepAgents graph.
"""

from __future__ import annotations

from collections.abc import Mapping

from langchain_mcp_adapters.client import MultiServerMCPClient


_MOCK_MCP_URL = "http://127.0.0.1:18880/mcp"
MCP_SERVER_CONFIG = {
    "erp-api": {"url": _MOCK_MCP_URL, "transport": "streamable_http"},
}
ANALYST_TOOL_PREFIXES = ("supplier_", "part_", "inventory_")
ORDER_TOOL_PREFIXES = ("order_",)
EXPECTED_TOOLS = frozenset({
    "supplier_query", "part_query", "part_search", "part_by_supplier",
    "inventory_warning", "order_search_details", "order_create", "order_update",
})


def validate_portfolio_mcp_config(server_config: object) -> dict:
    """Reject extra servers, public targets and ambiguous transport options."""
    if not isinstance(server_config, Mapping) or set(server_config) != {"erp-api"}:
        raise ValueError("Only the fictional local ERP MCP server is permitted")
    entry = server_config.get("erp-api")
    if (not isinstance(entry, Mapping) or set(entry) != {"url", "transport"}
            or entry["url"] != _MOCK_MCP_URL
            or entry["transport"] != "streamable_http"):
        raise ValueError("Only 127.0.0.1:18880/mcp using streamable_http is permitted")
    return {"erp-api": {"url": _MOCK_MCP_URL, "transport": "streamable_http"}}


async def load_mcp_tools(server_config: dict | None = None) -> tuple[list, list, list, list]:
    """Load eight authentic ERP tools and split them by Agent role.

    Return shape is backward-compatible with original main_agent.py:
    (all_mcp_tools, analyst_mcp_tools, order_mcp_tools, chart_mcp_tools).
    External analysis/chart tools are deliberately unavailable in this demo.
    """
    config = validate_portfolio_mcp_config(
        MCP_SERVER_CONFIG if server_config is None else server_config
    )
    client = MultiServerMCPClient(config)
    tools = list(await client.get_tools(server_name="erp-api"))
    names = [getattr(tool, "name", None) for tool in tools]
    if len(names) != len(set(names)) or set(names) != EXPECTED_TOOLS:
        raise RuntimeError("Unexpected tool catalog at the fictional local MCP")
    analyst_tools = [t for t in tools if t.name.startswith(ANALYST_TOOL_PREFIXES)]
    order_tools = [t for t in tools if t.name.startswith(ORDER_TOOL_PREFIXES)]
    return tools, analyst_tools, order_tools, []
