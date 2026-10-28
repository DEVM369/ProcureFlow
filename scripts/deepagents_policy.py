"""Pure-stdlib, fail-closed capability policy for the optional DeepAgents runtime test.

The runtime harness uses this policy *before* building any DeepAgents graph.
It never provisions or proxies write-capable ERP tools.
"""
from __future__ import annotations

READ_ONLY_CHILD_TOOLS = {
    "procurement-analyst": frozenset({
        "supplier_query", "part_query", "part_search", "part_by_supplier",
        "inventory_warning",
    }),
    "procurement-order": frozenset({"order_search_details"}),
}
FORBIDDEN_WRITES = frozenset({"order_create", "order_update"})
EXPECTED_CATALOG = frozenset().union(*READ_ONLY_CHILD_TOOLS.values(), FORBIDDEN_WRITES)


def enforce_safe_catalog(all_tools: list) -> list:
    """Require the exact already-verified eight MCP operations; allow six reads only."""
    names = [getattr(t, "name", None) for t in all_tools]
    if (len(names) != 8 or len(set(names)) != 8
            or set(names) != EXPECTED_CATALOG):
        raise ValueError("STOP: unexpected or duplicate MCP tool catalog")
    result = [t for t in all_tools if t.name not in FORBIDDEN_WRITES]
    if len(result) != 6:
        raise ValueError("STOP: invalid read-only MCP selection")
    return result


def enforce_subagent_capabilities(subagents: list) -> None:
    """Reject extra agents, any missing/extra tool, or empty role definitions."""
    if len(subagents) != len(READ_ONLY_CHILD_TOOLS):
        raise ValueError("STOP: unexpected sub-agent count")
    roles = [s.get("name") for s in subagents]
    if len(set(roles)) != len(roles) or set(roles) != set(READ_ONLY_CHILD_TOOLS):
        raise ValueError("STOP: unexpected or duplicate sub-agent role")
    for entry in subagents:
        tools = entry.get("tools", [])
        names = [getattr(t, "name", None) for t in tools]
        if len(names) != len(set(names)) or set(names) != READ_ONLY_CHILD_TOOLS[entry["name"]]:
            raise ValueError("STOP: sub-agent MCP capability mismatch")
        if set(names) & FORBIDDEN_WRITES:
            raise ValueError("STOP: write tool exposed to sub-agent")
