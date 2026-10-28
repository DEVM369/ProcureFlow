"""No external dependencies; approval grant and fake mutation invariants."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from synthetic_hitl import (ACTION_ARGS, ACTION_NAME, SyntheticApprovalLedger,
                            validate_synthetic_action)
import verify_deepagents_hitl as hitl_runner


class SyntheticHITLTests(unittest.TestCase):
    def setUp(self):
        self.ledger = SyntheticApprovalLedger()
        self.thread = "v4-fake-local-fixture"

    def test_unapproved_fake_write_is_refused(self):
        with self.assertRaises(PermissionError):
            self.ledger.execute_fake_order(self.thread, ACTION_NAME, ACTION_ARGS)
        self.assertEqual(self.ledger.orders(), [])

    def test_approved_exact_request_writes_one_ram_only_order(self):
        self.ledger.grant_after_human_approval(self.thread, ACTION_NAME, ACTION_ARGS)
        row = self.ledger.execute_fake_order(self.thread, ACTION_NAME, ACTION_ARGS)
        self.assertTrue(row["synthetic"])
        self.assertEqual(row["orderDetail"], ACTION_ARGS["order_detail"])
        self.assertEqual(len(self.ledger.orders()), 1)

    def test_replay_and_duplicate_grants_fail_closed(self):
        self.ledger.grant_after_human_approval(self.thread, ACTION_NAME, ACTION_ARGS)
        with self.assertRaises(PermissionError):
            self.ledger.grant_after_human_approval(self.thread, ACTION_NAME, ACTION_ARGS)
        self.ledger.execute_fake_order(self.thread, ACTION_NAME, ACTION_ARGS)
        with self.assertRaises(PermissionError):
            self.ledger.execute_fake_order(self.thread, ACTION_NAME, ACTION_ARGS)
        with self.assertRaises(PermissionError):
            self.ledger.grant_after_human_approval(self.thread, ACTION_NAME, ACTION_ARGS)
        self.assertEqual(len(self.ledger.orders()), 1)

    def test_forged_or_modified_args_do_not_consume_grant(self):
        self.ledger.grant_after_human_approval(self.thread, ACTION_NAME, ACTION_ARGS)
        changed = {**ACTION_ARGS, "remark": "other"}
        with self.assertRaises(ValueError):
            self.ledger.execute_fake_order(self.thread, ACTION_NAME, changed)
        self.assertEqual(self.ledger.orders(), [])
        self.ledger.execute_fake_order(self.thread, ACTION_NAME, ACTION_ARGS)
        self.assertEqual(len(self.ledger.orders()), 1)

    def test_not_real_data_or_mcp_tools(self):
        for name in ("order_update", "supplier_query", "unexpected"):
            with self.assertRaises(ValueError):
                validate_synthetic_action(name, ACTION_ARGS)
        with self.assertRaises(ValueError):
            validate_synthetic_action(ACTION_NAME, {"order_detail": []})
        with self.assertRaises(ValueError):
            self.ledger.grant_after_human_approval("real-production-thread", ACTION_NAME, ACTION_ARGS)

    def test_revoke_refuses_execution(self):
        self.ledger.grant_after_human_approval(self.thread, ACTION_NAME, ACTION_ARGS)
        self.ledger.revoke(self.thread)
        with self.assertRaises(PermissionError):
            self.ledger.execute_fake_order(self.thread, ACTION_NAME, ACTION_ARGS)
        self.assertEqual(self.ledger.orders(), [])

    def test_isolated_ledgers_never_share_orders(self):
        other = SyntheticApprovalLedger()
        self.ledger.grant_after_human_approval(self.thread, ACTION_NAME, ACTION_ARGS)
        self.ledger.execute_fake_order(self.thread, ACTION_NAME, ACTION_ARGS)
        self.assertEqual(other.orders(), [])

    def test_real_interrupt_inspection_rejects_extra_and_changed_actions(self):
        valid = {
            "action_requests": [{"name": ACTION_NAME, "args": ACTION_ARGS}],
            "review_configs": [{"action_name": ACTION_NAME,
                                "allowed_decisions": ["approve", "reject"]}],
        }
        interrupt = {"__interrupt__": [SimpleNamespace(value=valid)]}
        actual = hitl_runner._extract_exact_interrupt(interrupt)
        self.assertEqual(actual["args"], ACTION_ARGS)
        bad = [
            {**valid, "action_requests": []},
            {**valid, "action_requests": [valid["action_requests"][0]] * 2},
            {**valid, "action_requests": [{"name": "order_update", "args": ACTION_ARGS}]},
            {**valid, "review_configs": [{"action_name": "order_update",
                                         "allowed_decisions": ["approve", "reject"]}]},
            {**valid, "review_configs": [{"action_name": ACTION_NAME,
                                         "allowed_decisions": ["approve", "edit", "reject"]}]},
            {**valid, "review_configs": []},
        ]
        for value in bad:
            with self.subTest(value=str(value)[:70]):
                with self.assertRaises((ValueError, RuntimeError)):
                    hitl_runner._extract_exact_interrupt(
                        {"__interrupt__": [SimpleNamespace(value=value)]})
        with self.assertRaises(RuntimeError):
            hitl_runner._extract_exact_interrupt({"__interrupt__": []})

    def test_real_graph_smoke_stays_local_and_has_human_interrupt(self):
        source = (ROOT / "scripts" / "verify_deepagents_hitl.py").read_text("utf-8")
        self.assertIn("from deepagents import create_deep_agent", source)
        self.assertIn("HumanInTheLoopMiddleware", source)
        self.assertIn('Command(resume={"decisions": [{"type": decision}]}', source)
        self.assertIn("from langchain_core.language_models.chat_models import BaseChatModel", source)
        self.assertNotIn("load_mcp_tools", source)
        self.assertNotIn("httpx", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("ChatOpenAI", source)


if __name__ == "__main__":
    unittest.main()
