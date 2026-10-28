"""Offline demonstration security and behavioral regression suite (stdlib)."""

import unittest

from demo.engine import DemoEngine, DemoInputError, DemoNotFound, DemoWriteDisabled


class DemoWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.demo = DemoEngine()

    def _reach_approval(self, engine=None):
        engine = engine or self.demo
        thread_id, events = engine.chat("创建订单，请先补齐虚构物料")
        supplement_event = next(e for e in events if e["type"] == "interrupt")
        result = engine.resume(thread_id, supplement_event["approval_id"],
                               {"supplement": "物料101 数量50 单价42"})
        approval_event = next(e for e in result if e["type"] == "interrupt")
        return thread_id, supplement_event, approval_event

    def test_read_only_analysis_never_mutates_orders(self):
        thread, events = self.demo.chat("分析库存")
        self.assertEqual(self.demo.orders(), [])
        self.assertIn("task", self.demo._get(thread).tool_names)
        self.assertEqual(events[-1]["interrupted"], False)
        self.assertIn("固定模拟数据", events[-2]["content"])

    def test_first_interrupt_contains_live_thread_and_ticket(self):
        thread, events = self.demo.chat("创建订单")
        first = next(e for e in events if e["type"] == "interrupt")
        self.assertEqual(first["thread_id"], thread)
        self.assertTrue(first["approval_id"])
        self.assertEqual(first["interrupt_type"], "order_info_supplement")
        self.assertEqual(events[-1]["thread_id"], thread)

    def test_missing_fields_then_separate_approval_ticket(self):
        thread, first, second = self._reach_approval()
        self.assertEqual(first["thread_id"], second["thread_id"])
        self.assertNotEqual(first["approval_id"], second["approval_id"])
        self.assertEqual(second["interrupt_type"], "hitl_approval")
        self.assertEqual(self.demo.orders(), [])

    def test_denial_causes_no_mutation(self):
        thread, _, approval = self._reach_approval()
        events = self.demo.resume(thread, approval["approval_id"],
                                  {"decisions": [{"type": "reject"}]})
        self.assertIn("拒绝", events[0]["content"])
        self.assertEqual(self.demo.orders(), [])
        self.assertEqual(self.demo._get(thread).phase, "complete")

    def test_approval_is_disabled_by_default(self):
        thread, _, approval = self._reach_approval()
        with self.assertRaises(DemoWriteDisabled):
            self.demo.resume(thread, approval["approval_id"],
                             {"decisions": [{"type": "approve"}]})
        self.assertEqual(self.demo.orders(), [])
        # Rejection remains possible after forbidden approval.
        self.demo.resume(thread, approval["approval_id"],
                         {"decisions": [{"type": "reject"}]})

    def test_opt_in_in_memory_approval_with_replay_guard(self):
        demo = DemoEngine(allow_in_memory_writes=True)
        thread, _, approval = self._reach_approval(demo)
        events = demo.resume(thread, approval["approval_id"],
                             {"decisions": [{"type": "approve"}]})
        self.assertIn("内存", events[0]["content"])
        self.assertEqual(len(demo.orders()), 1)
        self.assertTrue(demo.orders()[0]["synthetic"])
        with self.assertRaises(DemoInputError):
            demo.resume(thread, approval["approval_id"],
                        {"decisions": [{"type": "approve"}]})
        self.assertEqual(len(demo.orders()), 1)

    def test_missing_or_old_ticket_is_rejected(self):
        thread, first, second = self._reach_approval()
        for ticket in (None, first["approval_id"], "random-ticket"):
            with self.subTest(ticket=ticket), self.assertRaises(DemoInputError):
                self.demo.resume(thread, ticket, {"decisions": [{"type": "reject"}]})
        self.assertEqual(self.demo._get(thread).approval_id, second["approval_id"])

    def test_invalid_resume_shape_does_not_consume_ticket(self):
        thread, _, approval = self._reach_approval()
        for bad in ("approve", {}, {"decisions": []}, {"decisions": [{"type": "rewrite"}]},
                    {"decisions": [{"type": "reject", "extra": 1}]}):
            with self.subTest(bad=bad), self.assertRaises(DemoInputError):
                self.demo.resume(thread, approval["approval_id"], bad)
        self.assertEqual(self.demo._get(thread).approval_id, approval["approval_id"])

    def test_open_interrupt_cannot_be_skipped_by_new_message(self):
        thread, _ = self.demo.chat("创建订单")
        with self.assertRaises(DemoInputError):
            self.demo.chat("直接执行", thread)
        self.assertEqual(self.demo.orders(), [])

    def test_no_real_credentials_or_connection_needed(self):
        demo = DemoEngine()
        demo.chat("库存预警")
        self.assertEqual(demo.orders(), [])
        with self.assertRaises(DemoWriteDisabled):
            demo.create_order({"orderDetail": [{"partId": 101}]}, idempotency_key="known-good-key")

    def test_direct_mutation_idempotency(self):
        demo = DemoEngine(allow_in_memory_writes=True)
        record = {"orderDetail": [{"partId": 101, "quantity": 50, "unitPrice": 42.0}]}
        first = demo.create_order(record, idempotency_key="stable-idempotency-one")
        second = demo.create_order(record, idempotency_key="stable-idempotency-one")
        self.assertEqual(first, second)
        self.assertEqual(len(demo.orders()), 1)

    def test_partial_update_does_not_replace_order_number(self):
        demo = DemoEngine(allow_in_memory_writes=True)
        record = {"orderDetail": [{"partId": 101, "quantity": 50, "unitPrice": 42.0}]}
        initial = demo.create_order(record, idempotency_key="stable-idempotency-two")
        changed = demo.update_order(initial["id"], {"remark": "updated"})
        self.assertEqual(changed["orderNumber"], initial["orderNumber"])
        self.assertEqual(changed["orderDetail"], initial["orderDetail"])
        with self.assertRaises(DemoInputError):
            demo.update_order(initial["id"], {"orderNumber": "overwrite"})

    def test_checkpoint_is_sanitized_and_not_real_langgraph(self):
        thread, _ = self.demo.chat("Private example: pretend-password")
        summary = self.demo.checkpoint_summary(thread)
        self.assertNotIn("pretend-password", str(summary))
        self.assertEqual(summary["states"][0]["values"]["messages"][0]["type"], "human")
        self.assertEqual(summary["states"][0]["values"]["messages"][0]["tool_calls"], [])

    def test_unknown_thread_and_bad_input_are_safely_rejected(self):
        with self.assertRaises(DemoNotFound):
            self.demo.display_messages("does-not-exist")
        for value in (None, "", "x" * 2001, ["bad"]):
            with self.subTest(value=str(value)[:10]), self.assertRaises(DemoInputError):
                self.demo.chat(value)


if __name__ == "__main__":
    unittest.main()
