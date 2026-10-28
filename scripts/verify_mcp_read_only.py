"""Real MCP adapter -> synthetic ERP, read-only end-to-end smoke test.

Requires existing fastmcp/langchain-mcp-adapters environment and two local
servers from this repo: demo HTTP 127.0.0.1:18881 (writes disabled) and MCP
HTTP 127.0.0.1:18880. It NEVER invokes order_create or order_update.

Run from the repo root: python -B scripts/verify_mcp_read_only.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from urllib.request import urlopen


DEMO_ORIGIN = "http://127.0.0.1:18881"
MCP_URL = "http://127.0.0.1:18880/mcp"
EXPECTED_TOOLS = frozenset({
    "supplier_query", "part_query", "part_search", "part_by_supplier",
    "inventory_warning", "order_search_details", "order_create", "order_update",
})

READ_CASES = (
    ("supplier_query", {"name": "Alpha"}, ("Example Supplier Alpha",)),
    ("part_query", {}, ("1000BASE-T1", "synthetic")),
    ("part_search", {"name": "Spark"}, ("Spark plug", "synthetic")),
    ("part_by_supplier", {"supplier_id": 11}, ("1000BASE-T1", "synthetic")),
    ("inventory_warning", {}, ("101", "synthetic")),
    ("order_search_details", {}, ()),
)


def get_json(path: str) -> dict:
    with urlopen(DEMO_ORIGIN + path, timeout=10) as response:
        return json.load(response)


def assert_demo_safe() -> int:
    health = get_json("/health")
    if (health.get("mode") != "deterministic-offline-demo"
            or health.get("synthetic") is not True
            or health.get("writes_enabled") is not False):
        raise RuntimeError("STOP: Expected write-disabled synthetic demo on 127.0.0.1:18881")
    orders = get_json("/api/demo/orders")
    if orders.get("synthetic") is not True:
        raise RuntimeError("STOP: Unexpected order store identity")
    return len(orders["orders"])


async def verify() -> None:
    before = assert_demo_safe()
    # Optional dependency is deliberately imported only in this manual smoke test.
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient({
        "procureflow-local": {"url": MCP_URL, "transport": "streamable_http"}
    })
    tools = await client.get_tools(server_name="procureflow-local")
    index = {tool.name: tool for tool in tools}
    print(f"MCP_TOOL_COUNT={len(index)}")
    if not EXPECTED_TOOLS.issubset(index):
        raise RuntimeError("STOP: Required MCP tools missing: "
                           + ", ".join(sorted(EXPECTED_TOOLS - set(index))))
    print("MCP_REQUIRED_TOOLS_FOUND=True")

    for name, arguments, expected_markers in READ_CASES:
        # Check the demo before EVERY call; abort if it has been replaced.
        assert_demo_safe()
        result = await index[name].ainvoke(arguments)
        preview = str(result)
        if any(marker.lower() not in preview.lower() for marker in expected_markers):
            raise RuntimeError(f"STOP: {name} did not return expected fictional data")
        if "没有查询到任何信息，而且报错" in preview or "API error" in preview:
            raise RuntimeError(f"STOP: {name} returned an adapter error")
        print(f"READ_{name.upper()}=PASS")

    after = assert_demo_safe()
    print(f"ORDERS_BEFORE={before}")
    print(f"ORDERS_AFTER={after}")
    if before != after:
        raise RuntimeError("STOP: Order count changed during read-only tests")
    print("READ_ONLY_MCP_SMOKE=PASS")


if __name__ == "__main__":
    try:
        asyncio.run(verify())
    except Exception as exc:
        # Keep error messages small and avoid printing raw MCP response bodies.
        print("READ_ONLY_MCP_SMOKE=FAIL", file=sys.stderr)
        print(f"ERROR_TYPE={type(exc).__name__}", file=sys.stderr)
        print(f"DETAIL={str(exc)[:240]}", file=sys.stderr)
        raise SystemExit(1)
