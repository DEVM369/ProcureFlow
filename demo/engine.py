"""Deterministic procurement walkthrough, NOT a language model or production ERP.

This keeps a local in-memory conversation and a one-use decision ticket so
reviewers can explore routing / field completion / HITL without any network,
database, business secrets, or real order side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4


SUPPLIERS = (
    {"id": 11, "name": "Example Supplier Alpha", "city": "Demo City A", "qualified": True},
    {"id": 12, "name": "Example Supplier Beta", "city": "Demo City B", "qualified": True},
)
PARTS = (
    {"id": 101, "name": "1000BASE-T1 connector (synthetic)", "category": "电子电气", "supplierId": 11},
    {"id": 102, "name": "Spark plug (synthetic)", "category": "动力系统", "supplierId": 12},
)
INVENTORY = (
    {"partId": 101, "quantity": 20, "safetyStock": 60},
    {"partId": 102, "quantity": 90, "safetyStock": 50},
)


class DemoInputError(ValueError):
    """A caller-supplied request fails the deterministic demo contract."""


class DemoNotFound(KeyError):
    """No matching local, ephemeral demonstration session exists."""


class DemoWriteDisabled(PermissionError):
    """Explicitly opt in to disposable in-memory writes for a demo."""


@dataclass
class Conversation:
    thread_id: str
    phase: str = "ready"
    approval_id: str | None = None
    messages: list[dict] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DemoEngine:
    def __init__(self, *, allow_in_memory_writes: bool = False):
        self.allow_in_memory_writes = allow_in_memory_writes
        self._lock = RLock()
        self._threads: dict[str, Conversation] = {}
        self._orders: dict[int, dict] = {}
        self._idempotency: dict[str, int] = {}
        self._next_order_id = 1

    def _get(self, thread_id: str) -> Conversation:
        thread = self._threads.get(thread_id)
        if thread is None:
            raise DemoNotFound("Unknown synthetic thread")
        return thread

    @staticmethod
    def _validate_message(message: object, label: str) -> str:
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
            raise DemoInputError(f"{label} must be a nonempty string of at most 2000 characters")
        return message.strip()

    @staticmethod
    def _new_ticket() -> str:
        return str(uuid4())

    @staticmethod
    def _add_message(thread: Conversation, role: str, content: str) -> None:
        thread.messages.append({
            "id": str(uuid4()), "role": role, "content": content, "source": "offline-demo"
        })

    def chat(self, message: object, thread_id: str | None = None) -> tuple[str, list[dict]]:
        """Simulate a read-only analysis or a new missing-field interrupt."""
        message = self._validate_message(message, "message")
        with self._lock:
            if thread_id is None:
                thread_id = str(uuid4())
                thread = Conversation(thread_id)
                self._threads[thread_id] = thread
            else:
                if not isinstance(thread_id, str):
                    raise DemoInputError("thread_id must be a string or null")
                thread = self._get(thread_id)

            if thread.phase in ("awaiting_info", "awaiting_approval"):
                raise DemoInputError("Pending interrupt must be resumed, not replaced by chat")

            self._add_message(thread, "user", message)
            thread.tool_names.append("task")
            start = {"type": "tool_start", "tool_name": "task", "tool_call_id": str(uuid4()), "source": "demo-main"}
            end = {"type": "tool_end", "tool_name": "task", "source": "demo-main"}

            if any(marker in message.lower() for marker in ("创建订单", "采购订单", "下单", "create order")):
                thread.phase = "awaiting_info"
                thread.approval_id = self._new_ticket()
                thread.tool_names.append("request_order_info")
                return thread_id, [
                    start, end,
                    {"type": "interrupt", "interrupt_type": "order_info_supplement",
                     "thread_id": thread_id, "approval_id": thread.approval_id,
                     "missing_fields": ["partId", "quantity", "unitPrice"],
                     "collected_data": {"scenario": "fictional automotive materials"}},
                    {"type": "done", "thread_id": thread_id, "interrupted": True},
                ]

            answer = (
                "演示分析：虚构物料 1000BASE-T1 connector 库存 20，安全库存 60；"
                "可向虚构供应商 Alpha / Beta 进一步询价。此结果来自固定模拟数据，不是实时模型推理或真实报价。"
            )
            self._add_message(thread, "assistant", answer)
            return thread_id, [start, end,
                               {"type": "token", "content": answer, "source": "demo-main"},
                               {"type": "done", "thread_id": thread_id,
                                "content": answer, "interrupted": False}]

    def resume(self, thread_id: str, approval_id: str, resume: object) -> list[dict]:
        """Consume exactly one current ticket, then enter the next demo stage."""
        with self._lock:
            thread = self._get(thread_id)
            if not isinstance(approval_id, str) or approval_id != thread.approval_id:
                raise DemoInputError("Missing, consumed, or stale approval ticket")
            if not isinstance(resume, dict):
                raise DemoInputError("resume must be a JSON object")

            if thread.phase == "awaiting_info":
                if set(resume) != {"supplement"}:
                    raise DemoInputError("Only supplement is accepted for missing-field interruption")
                supplement = self._validate_message(resume["supplement"], "supplement")
                self._add_message(thread, "user", supplement)
                thread.phase = "awaiting_approval"
                thread.approval_id = self._new_ticket()
                thread.tool_names.append("order_create")
                return [
                    {"type": "interrupt", "interrupt_type": "hitl_approval",
                     "thread_id": thread_id, "approval_id": thread.approval_id,
                     "action_requests": [{"name": "order_create", "args": {
                         "order_detail": [{"partId": 101, "quantity": 50, "unitPrice": 42.0}],
                         "remark": "SYNTHETIC IN-MEMORY DEMO ONLY"}}],
                     "review_configs": []},
                    {"type": "done", "thread_id": thread_id, "interrupted": True},
                ]

            if thread.phase != "awaiting_approval":
                raise DemoInputError("No approval stage awaiting a decision")

            decisions = resume.get("decisions")
            if (set(resume) != {"decisions"} or not isinstance(decisions, list)
                    or len(decisions) != 1 or not isinstance(decisions[0], dict)
                    or set(decisions[0]) != {"type"}
                    or decisions[0]["type"] not in ("approve", "reject")):
                raise DemoInputError("Expected one approve or reject decision")

            decision = decisions[0]["type"]
            if decision == "approve" and not self.allow_in_memory_writes:
                raise DemoWriteDisabled("Approval demo is disabled until --allow-in-memory-writes is set")

            thread.approval_id = None  # one-use ticket, before any synthetic write
            thread.phase = "complete"
            if decision == "reject":
                answer = "演示审批已拒绝：未创建任何订单。"
            else:
                order = self.create_order(
                    {"orderDetail": [{"partId": 101, "quantity": 50, "unitPrice": 42.0}],
                     "remark": "SYNTHETIC DEMO"},
                    idempotency_key="demo-approval-" + approval_id,
                )
                answer = f"演示审批已通过：仅创建内存中的虚构订单 #{order['id']}。"
            self._add_message(thread, "assistant", answer)
            return [{"type": "token", "content": answer, "source": "demo-main"},
                    {"type": "done", "thread_id": thread_id,
                     "content": answer, "interrupted": False}]

    def create_order(self, order: object, *, idempotency_key: str | None) -> dict:
        """An optional in-memory fake ERP write; never contacts a database."""
        if not self.allow_in_memory_writes:
            raise DemoWriteDisabled("Synthetic writes disabled by default")
        if not isinstance(idempotency_key, str) or not 8 <= len(idempotency_key) <= 128:
            raise DemoInputError("Stable idempotency key required")
        if not isinstance(order, dict) or not isinstance(order.get("orderDetail"), list) or not order["orderDetail"]:
            raise DemoInputError("Synthetic order requires orderDetail")
        with self._lock:
            if idempotency_key in self._idempotency:
                return dict(self._orders[self._idempotency[idempotency_key]])
            number = self._next_order_id
            self._next_order_id += 1
            value = {"id": number, "orderNumber": "DEMO-" + str(number).zfill(4),
                     "orderDetail": order["orderDetail"],
                     "remark": str(order.get("remark", ""))[:200], "synthetic": True}
            self._orders[number] = value
            self._idempotency[idempotency_key] = number
            return dict(value)

    def update_order(self, order_id: int, patch: object) -> dict:
        if not self.allow_in_memory_writes:
            raise DemoWriteDisabled("Synthetic writes disabled by default")
        if not isinstance(patch, dict) or not patch:
            raise DemoInputError("Nonempty partial update required")
        # Deliberately small patch surface. Never invent orderNumber/orderTime.
        if not set(patch).issubset({"remark", "status"}):
            raise DemoInputError("Only remark/status can be updated in this mock")
        with self._lock:
            if order_id not in self._orders:
                raise DemoNotFound("Unknown synthetic order")
            self._orders[order_id].update(patch)
            return dict(self._orders[order_id])

    def orders(self) -> list[dict]:
        with self._lock:
            return [dict(order) for order in self._orders.values()]

    def sessions(self) -> list[dict]:
        with self._lock:
            return [{"thread_id": t.thread_id,
                     "title": (t.messages[0]["content"][:50] if t.messages else "新对话"),
                     "message_count": len(t.messages), "created_at": t.created_at,
                     "updated_at": t.created_at} for t in self._threads.values()]

    def display_messages(self, thread_id: str) -> list[dict]:
        with self._lock:
            return [dict(m) for m in self._get(thread_id).messages]

    def checkpoint_summary(self, thread_id: str) -> dict:
        """Explicitly not a LangGraph checkpoint: projection-like demo contract."""
        with self._lock:
            thread = self._get(thread_id)
            messages = [{"type": "human" if m["role"] == "user" else "ai", "tool_calls": []}
                        for m in thread.messages[-100:]]
            return {"thread_id": thread_id, "states": [{
                "config": {"configurable": {"thread_id": thread_id}},
                "values": {"messages": messages, "message_count": len(thread.messages),
                           "truncated": len(thread.messages) > 100},
                "created_at": thread.created_at, "parent_config": None,
            }]}
