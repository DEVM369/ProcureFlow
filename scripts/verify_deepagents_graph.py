"""OPTIONAL owner-side REAL DeepAgents graph smoke, deterministic model.

Runs the *installed* DeepAgents `create_deep_agent` and the original Agent
`OrderTaskRoutingMiddleware`, resolved safe sub-agent configs and six real
read-only MCP tools against a strictly fictional, write-disabled local ERP.

No Qwen/OpenAI service, model API key, database or real ERP is used. The chat
model is a deterministic `BaseChatModel` solely to drive real graph nodes.
If a runtime API changes, FAIL rather than silently passing a simulation.

Prerequisites: owner's existing DeepAgents/LangChain/PyYAML/MCP environment;
127.0.0.1:18881 demo server and 127.0.0.1:18880 MCP from this repository.
Run: python -B scripts/verify_deepagents_graph.py
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from deepagents_policy import (
    FORBIDDEN_WRITES, READ_ONLY_CHILD_TOOLS,
    enforce_safe_catalog, enforce_subagent_capabilities,
)


def _read_synthetic_json(path: str) -> dict:
    with urlopen("http://127.0.0.1:18881" + path, timeout=10) as response:
        return json.load(response)


def _preflight() -> int:
    health = _read_synthetic_json("/health")
    if (health.get("mode") != "deterministic-offline-demo"
            or health.get("synthetic") is not True
            or health.get("writes_enabled") is not False):
        raise RuntimeError("STOP: expected write-disabled fictional ERP")
    data = _read_synthetic_json("/api/demo/orders")
    if data.get("synthetic") is not True or not isinstance(data.get("orders"), list):
        raise RuntimeError("STOP: expected synthetic order storage")
    return len(data["orders"])


def _name(obj):
    if isinstance(obj, dict):
        return obj.get("name") or obj.get("function", {}).get("name")
    return getattr(obj, "name", None)


def _model_factory():
    """Import dependencies on owner side only; never call an external model."""
    from pydantic import PrivateAttr
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class DeterministicGraphModel(BaseChatModel):
        role: str
        _calls: int = PrivateAttr(default=0)
        _bound: list = PrivateAttr(default_factory=list)
        _tool_receipts: list = PrivateAttr(default_factory=list)

        @property
        def _llm_type(self) -> str:
            return "procureflow-deterministic-graph-smoke"

        def bind_tools(self, tools, *, tool_choice=None, **kwargs):
            names = [_name(t) for t in tools]
            if set(names) & FORBIDDEN_WRITES:
                raise RuntimeError("STOP: write-capable tool bound to offline model")
            self._bound.append((names, tool_choice))
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self._calls += 1
            if self._calls > 4:
                raise RuntimeError("STOP: unexpected extra model round trips")
            if self.role.startswith("root-"):
                target = ("procurement-order" if self.role == "root-order"
                          else "procurement-analyst")
                if self._calls == 1:
                    if not any("task" in names for names, _ in self._bound):
                        raise RuntimeError("STOP: DeepAgents task tool unavailable")
                    result = AIMessage(content="", tool_calls=[{
                        "id": "call_demo_task", "name": "task",
                        "args": {"description": "Review only synthetic ERP data; never write.",
                                 "subagent_type": target},
                    }])
                else:
                    has_task_reply = any(
                        isinstance(m, ToolMessage) and m.name == "task"
                        for m in messages
                    )
                    if not has_task_reply:
                        raise RuntimeError("STOP: DeepAgents task did not return")
                    result = AIMessage(content="SYNTHETIC_DELEGATION_COMPLETE")
            else:
                read_tool = ("order_search_details" if self.role == "procurement-order"
                             else "inventory_warning")
                if self._calls == 1:
                    if not any(read_tool in names for names, _ in self._bound):
                        raise RuntimeError("STOP: expected read-only child tool missing")
                    result = AIMessage(content="", tool_calls=[{
                        "id": "call_demo_read", "name": read_tool, "args": {},
                    }])
                else:
                    receipts = [m for m in messages
                                if isinstance(m, ToolMessage) and m.name == read_tool]
                    if not receipts:
                        raise RuntimeError("STOP: MCP tool reply missing from child graph")
                    reply = str(receipts[-1].content)
                    if (not reply or "API error" in reply
                            or "没有查询到任何信息，而且报错" in reply
                            or getattr(receipts[-1], "status", "success") == "error"):
                        raise RuntimeError("STOP: MCP read returned an error")
                    if read_tool == "inventory_warning":
                        if "101" not in reply or "synthetic" not in reply.lower():
                            raise RuntimeError("STOP: MCP inventory response is not the fictional fixture")
                    elif reply.strip() not in ("[]", "[\"\"]"):
                        # Zero fake orders were observed in the preflight; a
                        # nonempty response could indicate an unexpected ERP.
                        raise RuntimeError("STOP: order read is not the empty mock result")
                    self._tool_receipts.append(read_tool)
                    result = AIMessage(content="SYNTHETIC_READ_COMPLETE")
            return ChatResult(generations=[ChatGeneration(message=result)])

    return DeterministicGraphModel


async def _run_one(label: str, all_tools, safe_configs, model_class) -> None:
    from deepagents import create_deep_agent
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    from agent.middlewares.order_task_routing import OrderTaskRoutingMiddleware
    from agent.subagents.loader import resolve_subagent_tools

    models = {
        role: model_class(role=role) for role in READ_ONLY_CHILD_TOOLS
    }
    root = model_class(role="root-" + label)
    subagents = resolve_subagent_tools(safe_configs, all_tools)
    enforce_subagent_capabilities(subagents)
    for s in subagents:
        # Explicit local model means no remote API key or inference is possible.
        s["model"] = models[s["name"]]

    graph = create_deep_agent(
        model=root,
        tools=[],
        subagents=subagents,
        middleware=[OrderTaskRoutingMiddleware()],
        checkpointer=InMemorySaver(),
    )
    print("DEEPAGENTS_REAL_GRAPH_BUILD=PASS")
    prompt = ("请查询采购订单，仅读取虚构数据，禁止写入。" if label == "order"
              else "分析虚构库存预警信息，仅读取数据，禁止写入。")
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config={"configurable": {"thread_id": "v3-synthetic-" + label},
                "recursion_limit": 30},
    )
    messages = result.get("messages", [])
    if "__interrupt__" in result:
        raise RuntimeError("STOP: unexpected HITL interrupt in read-only graph")
    if not any(any(c.get("name") == "task" for c in
                   getattr(m, "tool_calls", []) or []) for m in messages):
        raise RuntimeError("STOP: actual graph did not emit task delegation")
    if root._calls < 2:
        raise RuntimeError("STOP: main graph never resumed after delegation")
    role = "procurement-order" if label == "order" else "procurement-analyst"
    read_tool = "order_search_details" if label == "order" else "inventory_warning"
    child = models[role]
    if child._calls < 2 or child._tool_receipts != [read_tool]:
        raise RuntimeError("STOP: child graph did not execute real MCP read")
    if label == "order":
        if not any(choice == "required" and names == ["task"]
                   for names, choice in root._bound):
            raise RuntimeError("STOP: original routing middleware did not force task")
        print("ORIGINAL_ROUTING_IN_REAL_GRAPH=PASS")
    print(f"REAL_SUBAGENT_{role.replace('-', '_').upper()}=PASS")
    print(f"DEEPAGENTS_{label.upper()}_READ_ONLY=PASS")


async def verify():
    before = _preflight()
    from agent.tools.mcp_client import load_mcp_tools
    from agent.subagents.loader import load_subagent_configs

    all_tools, *_ = await load_mcp_tools()
    read_tools = enforce_safe_catalog(all_tools)
    safe_configs = load_subagent_configs(ROOT / "demo" / "safe_subagents")
    # Check safe configuration/tool associations *before* graph creation.
    from agent.subagents.loader import resolve_subagent_tools
    resolved = resolve_subagent_tools(safe_configs, read_tools)
    enforce_subagent_capabilities(resolved)
    print("DEEPAGENTS_READ_ONLY_CAPABILITIES=PASS")

    model_class = _model_factory()
    await _run_one("order", read_tools, safe_configs, model_class)
    await _run_one("analyst", read_tools, safe_configs, model_class)
    after = _preflight()
    print("ORDERS_BEFORE=" + str(before))
    print("ORDERS_AFTER=" + str(after))
    if before != after:
        raise RuntimeError("STOP: orders changed during real DeepAgents graph test")
    print("REAL_DEEPAGENTS_GRAPH_READ_ONLY=PASS")


if __name__ == "__main__":
    try:
        asyncio.run(verify())
    except Exception as exc:
        print("REAL_DEEPAGENTS_GRAPH_READ_ONLY=FAIL", file=sys.stderr)
        print("ERROR_TYPE=" + type(exc).__name__, file=sys.stderr)
        print("DETAIL=" + str(exc)[:260], file=sys.stderr)
        raise SystemExit(1)
