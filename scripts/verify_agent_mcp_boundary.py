"""Real Agent routing and YAML loader -> real MCP -> fake ERP, no model/writes.

This is a contract harness, NOT a fully running DeepAgents graph. The model
handler is deliberately simulated; the OrderTaskRoutingMiddleware and
sub-agent YAML loader are the actual authorized Agent modules. All MCP calls
are read-only and target the synthetic 127.0.0.1:18881 ERP through 18880.

Requires owner's compatible LangChain/PyYAML/MCP Python environment.
Run from extracted root: python -B scripts/verify_agent_mcp_boundary.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _get_json(path):
    with urlopen("http://127.0.0.1:18881" + path, timeout=10) as response:
        return json.load(response)


def _preflight():
    health = _get_json("/health")
    if (health.get("mode") != "deterministic-offline-demo"
            or health.get("synthetic") is not True
            or health.get("writes_enabled") is not False):
        raise RuntimeError("STOP: Write-disabled local synthetic ERP required")
    record = _get_json("/api/demo/orders")
    if record.get("synthetic") is not True:
        raise RuntimeError("STOP: Unexpected order store identity")
    return len(record["orders"])


class SimulatedModelRequest:
    """Only the ModelRequest fields the real middleware needs, no inference."""

    def __init__(self, messages, tools, tool_choice=None):
        self.messages = messages
        self.tools = tools
        self.tool_choice = tool_choice

    def override(self, **kwargs):
        return SimulatedModelRequest(
            self.messages, kwargs.get("tools", self.tools),
            kwargs.get("tool_choice", self.tool_choice),
        )


async def _verify_routing(actual_tools):
    from agent.middlewares.order_task_routing import OrderTaskRoutingMiddleware

    middleware = OrderTaskRoutingMiddleware()
    model_request = SimulatedModelRequest(
        [{"type": "human", "content": "创建采购订单"}],
        [SimpleNamespace(name="task")] + list(actual_tools),
    )

    async def simulated_valid_model(req):
        names = [getattr(tool, "name", None) for tool in req.tools]
        if req.tool_choice != "required" or names != ["task"]:
            raise AssertionError("Routing did not narrow model tool choice to task")
        return SimpleNamespace(result=[{"tool_calls": [{
            "name": "task", "args": {"subagent_type": "procurement-order",
                                     "description": "Inspect synthetic order request"},
        }]}])

    response = await middleware.awrap_model_call(model_request, simulated_valid_model)
    if not getattr(response, "result", None):
        raise RuntimeError("STOP: Real routing guard rejected valid simulated delegation")
    print("ORIGINAL_ORDER_ROUTING_GATE=PASS")

    async def simulated_invalid_model(req):
        return SimpleNamespace(result=[{"tool_calls": [{
            "name": "order_create", "args": {"order_detail": []},
        }]}])

    refused = await middleware.awrap_model_call(model_request, simulated_invalid_model)
    if "未执行任何 ERP 订单写操作" not in str(getattr(refused, "content", "")):
        raise RuntimeError("STOP: Invalid direct write request did not fail closed")
    print("INVALID_TASK_FAIL_CLOSED=PASS")


async def verify():
    before = _preflight()
    from agent.tools.mcp_client import load_mcp_tools
    from agent.subagents.loader import load_subagent_configs, resolve_subagent_tools

    all_tools, analyst_tools, order_tools, chart_tools = await load_mcp_tools()
    if (len(all_tools), len(analyst_tools), len(order_tools), len(chart_tools)) != (8, 5, 3, 0):
        raise RuntimeError("STOP: Unexpected original Agent MCP tool grouping")
    print("AGENT_MCP_TOOL_GROUPING=PASS")

    configs = load_subagent_configs(ROOT / "demo" / "safe_subagents")
    read_only_names = {"supplier_query", "part_query", "part_search",
                       "part_by_supplier", "inventory_warning", "order_search_details"}
    allowed_tools = [t for t in all_tools if t.name in read_only_names]
    subagents = resolve_subagent_tools(configs, allowed_tools)
    index = {subagent["name"]: subagent for subagent in subagents}
    if set(index) != {"procurement-analyst", "procurement-order"}:
        raise RuntimeError("STOP: Unexpected safe demo sub-agent set")
    analyst_names = {t.name for t in index["procurement-analyst"]["tools"]}
    order_names = {t.name for t in index["procurement-order"]["tools"]}
    if analyst_names != read_only_names - {"order_search_details"}:
        raise RuntimeError("STOP: Analyst tool list mismatch")
    if order_names != {"order_search_details"}:
        raise RuntimeError("STOP: Order agent accidentally acquired write capabilities")
    print("SUBAGENT_READ_ONLY_TOOL_ISOLATION=PASS")

    await _verify_routing(all_tools)

    # Two genuine remote MCP tool invocations; no synthetic in-process tool stub.
    _preflight()
    inventory_tool = next(t for t in index["procurement-analyst"]["tools"]
                          if t.name == "inventory_warning")
    inventory = str(await inventory_tool.ainvoke({}))
    if "101" not in inventory or "synthetic" not in inventory.lower():
        raise RuntimeError("STOP: MCP inventory did not return fictional data")
    order_tool = index["procurement-order"]["tools"][0]
    order_result = str(await order_tool.ainvoke({}))
    if "API error" in order_result or "没有查询到任何信息，而且报错" in order_result:
        raise RuntimeError("STOP: MCP order read failed")
    print("REAL_MCP_READ_ONLY_EXECUTION=PASS")

    after = _preflight()
    print(f"ORDERS_BEFORE={before}")
    print(f"ORDERS_AFTER={after}")
    if before != after:
        raise RuntimeError("STOP: Order count changed during safe Agent boundary test")
    print("AGENT_MCP_BOUNDARY=PASS")


if __name__ == "__main__":
    try:
        asyncio.run(verify())
    except Exception as exc:
        print("AGENT_MCP_BOUNDARY=FAIL", file=sys.stderr)
        print(f"ERROR_TYPE={type(exc).__name__}", file=sys.stderr)
        print(f"DETAIL={str(exc)[:240]}", file=sys.stderr)
        raise SystemExit(1)
