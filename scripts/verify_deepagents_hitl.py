"""Local test: real DeepAgents graph + real LangChain HITL approval/rejection.

The ONLY write tool is a local Python function backed by RAM. It is not the
MCP order_create adapter, never imports the production ERP, and never opens
network sockets. A deterministic BaseChatModel replaces all cloud LLM calls.

No local MCP/ERP processes are required. When run, it verifies:
- real LangGraph HITL interrupt before a write,
- rejection leaves fake ledger empty and write tool uncalled,
- approval for exactly the inspected request causes one RAM-only fake write,
- action mismatch/replay and unauthorised execution are rejected.

If the owner's installed LangChain/DeepAgents runtime changes shape, FAIL
rather than silently claiming a simulated test passed.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from synthetic_hitl import (ACTION_NAME, ACTION_ARGS,
                            SyntheticApprovalLedger, validate_synthetic_action)


def _tool_name(value):
    if isinstance(value, dict):
        return value.get("name") or value.get("function", {}).get("name")
    return getattr(value, "name", None)


def _model_factory():
    from pydantic import PrivateAttr
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class FakeOrderIntentModel(BaseChatModel):
        _calls: int = PrivateAttr(default=0)
        _bound_names: list = PrivateAttr(default_factory=list)

        @property
        def _llm_type(self) -> str:
            return "procureflow-in-process-hitl-fixture"

        def bind_tools(self, tools, *, tool_choice=None, **kwargs):
            names = [_tool_name(t) for t in tools]
            if names.count(ACTION_NAME) != 1 or "order_update" in names:
                raise RuntimeError("STOP: unexpected fake write capability")
            self._bound_names.append(names)
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            self._calls += 1
            if self._calls == 1:
                return ChatResult(generations=[ChatGeneration(message=AIMessage(
                    content="", tool_calls=[{
                        "id": "v4_fake_create", "name": ACTION_NAME,
                        "args": dict(ACTION_ARGS),
                    }],
                ))])
            if self._calls != 2:
                raise RuntimeError("STOP: unexpected model rounds")
            if not any(isinstance(m, ToolMessage) and (
                getattr(m, "name", None) == ACTION_NAME
                or getattr(m, "tool_call_id", None) == "v4_fake_create")
                       for m in messages):
                raise RuntimeError("STOP: tool response missing after HITL resume")
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="SYNTHETIC_HITL_WORKFLOW_COMPLETE"
            ))])

    return FakeOrderIntentModel


def _extract_exact_interrupt(result) -> dict:
    """Require exactly one action matching the approved static dummy payload."""
    interrupts = result.get("__interrupt__") if isinstance(result, dict) else None
    if not isinstance(interrupts, (list, tuple)) or len(interrupts) != 1:
        raise RuntimeError("STOP: expected one real LangGraph HITL interrupt")
    event = getattr(interrupts[0], "value", None)
    if not isinstance(event, dict):
        raise RuntimeError("STOP: interrupt payload not inspectable")
    actions = event.get("action_requests")
    if not isinstance(actions, list) or len(actions) != 1 or not isinstance(actions[0], dict):
        raise RuntimeError("STOP: expected exactly one action request")
    action = actions[0]
    validate_synthetic_action(action.get("name"), action.get("args"))
    configs = event.get("review_configs")
    if not isinstance(configs, list) or len(configs) != 1:
        raise RuntimeError("STOP: review configuration missing or ambiguous")
    config = configs[0]
    if not isinstance(config, dict) or config.get("action_name") != ACTION_NAME:
        raise RuntimeError("STOP: approval configuration targets wrong action")
    if set(config.get("allowed_decisions", [])) != {"approve", "reject"}:
        raise RuntimeError("STOP: approval configuration permits an unexpected decision")
    return action


async def _scenario(decision: str):
    from deepagents import create_deep_agent
    from langchain.agents.middleware import HumanInTheLoopMiddleware
    from langchain_core.messages import HumanMessage
    from langchain_core.tools import tool
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.types import Command

    # Absolutely no network or global server state. Each run has a separate
    # checkpoint, fake chat model, ephemeral store and synthetic thread id.
    ledger = SyntheticApprovalLedger()
    thread_id = "v4-fake-" + uuid4().hex

    @tool("order_create")
    def fake_order_create(order_detail: list[dict], remark: str) -> dict:
        """Create one disposable FAKE in-process order after trusted approval."""
        return ledger.execute_fake_order(thread_id, ACTION_NAME, {
            "order_detail": order_detail, "remark": remark,
        })

    model = _model_factory()()
    graph = create_deep_agent(
        model=model,
        tools=[fake_order_create],
        middleware=[HumanInTheLoopMiddleware(interrupt_on={
            ACTION_NAME: {"allowed_decisions": ["approve", "reject"]},
        })],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 32}

    # First execution MUST interrupt and leave the real tool uncalled.
    before = await graph.ainvoke(
        {"messages": [HumanMessage(content="Create one FICTIONAL test order; wait for approval.")]},
        config=config,
    )
    action = _extract_exact_interrupt(before)
    if ledger.orders() or ledger.call_attempts:
        raise RuntimeError("STOP: order tool was executed before approval")
    print("REAL_HITL_INTERRUPT_BEFORE_WRITE=PASS")

    if decision == "approve":
        # Trust boundary: real checkpoint action has been reviewed and is an
        # EXACT match for the hard-coded fictional-only order fixture.
        ledger.grant_after_human_approval(thread_id, action["name"], action["args"])
    else:
        # For rejection there is never any grant.
        if ledger.orders():
            raise RuntimeError("STOP: mutation before reject")

    finished = await graph.ainvoke(
        Command(resume={"decisions": [{"type": decision}]}), config=config,
    )
    if "__interrupt__" in finished:
        raise RuntimeError("STOP: unexpected second interrupt")
    if model._calls != 2:
        raise RuntimeError("STOP: graph did not process tool result on resume")

    orders = ledger.orders()
    if decision == "reject":
        if orders or ledger.call_attempts != 0:
            raise RuntimeError("STOP: rejected order reached write boundary")
        print("REAL_HITL_REJECT_NO_WRITE=PASS")
    else:
        if len(orders) != 1 or ledger.call_attempts != 1 or not orders[0]["synthetic"]:
            raise RuntimeError("STOP: exactly one fake order expected after approval")
        if orders[0]["orderDetail"] != ACTION_ARGS["order_detail"]:
            raise RuntimeError("STOP: approved arguments were modified")
        print("REAL_HITL_APPROVE_FAKE_ONLY=PASS")
        # Simulates malicious direct retry: the trusted grant is consumed.
        try:
            ledger.execute_fake_order(thread_id, ACTION_NAME, dict(ACTION_ARGS))
        except PermissionError:
            pass
        else:
            raise RuntimeError("STOP: replay was incorrectly accepted")
        if len(ledger.orders()) != 1:
            raise RuntimeError("STOP: fake replay mutated store")
        print("FAKE_APPROVAL_REPLAY_BLOCKED=PASS")
    return decision


async def verify():
    # Fail-closed missing approval independent of the LangGraph execution path.
    ledger = SyntheticApprovalLedger()
    try:
        ledger.execute_fake_order("v4-fake-no-grant", ACTION_NAME, dict(ACTION_ARGS))
    except PermissionError:
        print("FAKE_WRITE_DEFAULT_DENY=PASS")
    else:
        raise RuntimeError("STOP: fake write without grant succeeded")

    await _scenario("reject")
    await _scenario("approve")
    print("REAL_DEEPAGENTS_HITL_FAKE_WRITE=PASS")
    print("REAL_ERP_CONNECTIONS=NONE")


if __name__ == "__main__":
    try:
        asyncio.run(verify())
    except Exception as exc:
        print("REAL_DEEPAGENTS_HITL_FAKE_WRITE=FAIL", file=sys.stderr)
        print("ERROR_TYPE=" + type(exc).__name__, file=sys.stderr)
        print("DETAIL=" + str(exc)[:240], file=sys.stderr)
        sys.exit(1)
