"""Standard-library approval-to-action binding for an *in-process fake ERP*.

This is a verification fixture, NOT a general-purpose approval service or a
production authorization implementation. No networking, disk persistence or
production ERP adapter is imported. A trusted verifier must inspect a genuine
LangGraph interrupt before issuing the one-time grant.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from threading import RLock


ACTION_NAME = "order_create"
ACTION_ARGS = {
    "order_detail": [{"partId": 101, "quantity": 50, "unitPrice": 42.0}],
    "remark": "SYNTHETIC HITL GRAPH FIXTURE ONLY",
}


def _fingerprint(args: dict) -> str:
    if not isinstance(args, dict):
        raise ValueError("STOP: action arguments must be a dictionary")
    try:
        normalized = json.dumps(args, sort_keys=True, ensure_ascii=True,
                                allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("STOP: non-canonical action arguments") from exc
    return sha256(normalized.encode("ascii")).hexdigest()


def validate_synthetic_action(name: str, args: dict) -> str:
    if name != ACTION_NAME:
        raise ValueError("STOP: unexpected action name")
    if not isinstance(args, dict) or args != ACTION_ARGS:
        raise ValueError("STOP: fictional fixture mismatch")
    return _fingerprint(args)


@dataclass(frozen=True)
class Grant:
    thread_id: str
    action_digest: str
    idempotency_key: str


class SyntheticApprovalLedger:
    """RAM-only, one-use grant bound to a thread and immutable fake request."""
    def __init__(self):
        self._lock = RLock()
        self._grants: dict[str, Grant] = {}
        self._consumed: set[str] = set()
        self._orders: dict[str, dict] = {}
        self._seq = 0
        self.call_attempts = 0

    def grant_after_human_approval(self, thread_id: str, name: str, args: dict) -> str:
        """Only the verifier/controller should call this AFTER HITL inspection."""
        if not isinstance(thread_id, str) or not thread_id.startswith("v4-fake-"):
            raise ValueError("STOP: invalid synthetic thread")
        digest = validate_synthetic_action(name, args)
        with self._lock:
            if thread_id in self._grants or thread_id in self._consumed:
                raise PermissionError("STOP: approval replay")
            # Stable for this approved simulated action, never model-generated.
            key = "fake-v4-" + sha256((thread_id + ":" + digest).encode()).hexdigest()[:32]
            self._grants[thread_id] = Grant(thread_id, digest, key)
            return key

    def execute_fake_order(self, thread_id: str, name: str, args: dict) -> dict:
        """Fail closed by default; never calls HTTP, MCP, SQL or real ERP."""
        with self._lock:
            self.call_attempts += 1
            digest = validate_synthetic_action(name, args)
            grant = self._grants.get(thread_id)
            if grant is None or grant.action_digest != digest:
                raise PermissionError("APPROVAL_EXECUTION_REQUIRED")
            if thread_id in self._consumed:
                raise PermissionError("STOP: approved grant already consumed")
            if grant.idempotency_key in self._orders:
                raise PermissionError("STOP: unexpectedly repeated order write")
            self._seq += 1
            result = {
                "id": self._seq,
                "orderNumber": f"FAKE-V4-{self._seq:04d}",
                "synthetic": True,
                "orderDetail": deepcopy(args["order_detail"]),
                "remark": args["remark"],
                "idempotencyKeyFingerprint": sha256(grant.idempotency_key.encode()).hexdigest()[:12],
            }
            self._orders[grant.idempotency_key] = result
            self._consumed.add(thread_id)
            del self._grants[thread_id]
            return deepcopy(result)

    def orders(self) -> list[dict]:
        with self._lock:
            return [deepcopy(order) for order in self._orders.values()]

    def revoke(self, thread_id: str) -> None:
        with self._lock:
            self._grants.pop(thread_id, None)
