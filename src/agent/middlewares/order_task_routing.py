"""Force one safe task delegation for explicit procurement-order requests.

The main agent already has DeepAgents' task tool. For an explicitly actionable
order request, narrow the first model call to that delegation tool, without
directly exposing ERP write tools or bypassing child HITL.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

_ORDER_ACTION_RE = re.compile(
    r"(?:创建|新建|建立|录入|提交|准备|生成|发起|起草|下达|填写|做|下|"
    r"修改|更新|调整|取消|撤销|作废|查询|查找|查看|检索|补充|完善|收集)"
    r"[^\n。！？!?]{0,20}?"
    r"(?:采购订单|采购单|订单|下单)",
    re.IGNORECASE,
)
_ORDER_ACTION_REVERSE_RE = re.compile(
    r"(?:采购订单|采购单|订单)"
    r"[^\n。！？!?]{0,8}?"
    r"(?:创建|新建|录入|提交|修改|更新|调整|取消|撤销|作废|"
    r"查询|查找|检索|补充|完善)",
    re.IGNORECASE,
)
_ENGLISH_ORDER_RE = re.compile(
    r"\b(?:create|place|prepare|submit|update|modify|cancel|"
    r"search|find|check|complete)\b.{0,40}"
    r"\b(?:purchase\s+order|procurement\s+order|order)\b",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(
    r"(?:不要|请勿|禁止|不用|暂不|别|无需)"
    r"[^。！？!?]{0,12}"
    r"(?:创建|新建|提交|下单|修改|更新|取消|作废|查询)",
)
_EDUCATIONAL_RE = re.compile(
    r"^(?:什么是|如何|怎么|怎样|解释一下|介绍一下|科普|教程|"
    r"如何理解|如何学习|为什么|举例说明)",
)

_UNAVAILABLE = (
    "采购订单委派暂不可用，请稍后重试。"
    "本次请求未执行任何 ERP 订单写操作。"
)


def _message_value(message: Any, key: str, default: Any = None) -> Any:
    if isinstance(message, Mapping):
        return message.get(key, default)
    return getattr(message, key, default)


def _to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(part.get("text", "")) if isinstance(part, Mapping) else str(part)
            for part in content
        )
    return ""


def _is_explicit_order_request(text: str) -> bool:
    text = text.strip()
    if not text:
        return False
    if _EDUCATIONAL_RE.search(text) or _NEGATION_RE.search(text):
        return False
    return bool(
        _ORDER_ACTION_RE.search(text)
        or _ORDER_ACTION_REVERSE_RE.search(text)
        or _ENGLISH_ORDER_RE.search(text)
        or any(
            phrase in text.lower()
            for phrase in ("下单", "补单", "order_create", "order_update")
        )
    )


def _has_task_call(message: Any) -> bool:
    calls = _message_value(message, "tool_calls", []) or []
    return any(
        _message_value(call, "name") == "task"
        for call in calls
    )


def _needs_first_order_delegation(messages: Sequence[Any]) -> bool:
    """Force at most once per user turn, including HITL resume."""
    last_human = -1
    for index in range(len(messages) - 1, -1, -1):
        role = _message_value(
            messages[index],
            "type",
            _message_value(messages[index], "role"),
        )
        if role in ("human", "user"):
            last_human = index
            break

    if last_human < 0:
        return False
    if not _is_explicit_order_request(
        _to_text(_message_value(messages[last_human], "content"))
    ):
        return False
    return not any(_has_task_call(msg) for msg in messages[last_human + 1:])


def _current_request_messages(request: Any) -> Sequence[Any]:
    """Prefer the model's actual input, not an optional/stale state snapshot.

    LangChain ModelRequest exposes both ``messages`` (the input being sent to
    the model) and ``state`` (graph state).  The latter may be empty in a
    middleware wrapper, even when the former contains the current user turn.
    """
    messages = getattr(request, "messages", None)
    if isinstance(messages, Sequence) and not isinstance(messages, (str, bytes)):
        return messages

    state = getattr(request, "state", None)
    if isinstance(state, Mapping):
        fallback = state.get("messages", [])
        if isinstance(fallback, Sequence) and not isinstance(fallback, (str, bytes)):
            return fallback
    return []


def _valid_order_delegation(response: Any) -> bool:
    """Only permit one task call addressed to procurement-order."""
    if isinstance(response, AIMessage):
        messages = [response]
    else:
        messages = getattr(response, "result", None)

    if not isinstance(messages, (list, tuple)):
        return False

    calls = []
    for message in messages:
        calls.extend(_message_value(message, "tool_calls", []) or [])

    if len(calls) != 1:
        return False

    call = calls[0]
    args = _message_value(call, "args", {})
    return (
        _message_value(call, "name") == "task"
        and isinstance(args, Mapping)
        and args.get("subagent_type") == "procurement-order"
        and isinstance(args.get("description"), str)
        and bool(args["description"].strip())
    )


class OrderTaskRoutingMiddleware(AgentMiddleware):
    """Apply a bounded first-turn tool choice; preserve normal model calls."""

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        messages = _current_request_messages(request)
        if not _needs_first_order_delegation(messages):
            return await handler(request)

        logger.info("OrderTaskRouting: enforcing first-turn order delegation")
        task_tools = [
            tool for tool in (getattr(request, "tools", None) or [])
            if _message_value(tool, "name") == "task"
        ]
        if len(task_tools) != 1:
            logger.error("OrderTaskRouting: task tool unavailable or ambiguous")
            return AIMessage(content=_UNAVAILABLE)

        # The local 0.4.12 runtime confirmed ModelRequest tool_choice support.
        try:
            forced_request = request.override(
                tools=task_tools,
                tool_choice="required",
            )
        except Exception:
            logger.exception("OrderTaskRouting: cannot enforce task selection")
            return AIMessage(content=_UNAVAILABLE)

        response = await handler(forced_request)
        if not _valid_order_delegation(response):
            logger.error("OrderTaskRouting: invalid task target/model response")
            return AIMessage(content=_UNAVAILABLE)

        return response
