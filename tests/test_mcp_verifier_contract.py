"""Ensure the opt-in MCP smoke tool cannot become an order-write test."""

import unittest
from unittest.mock import patch

from scripts.verify_mcp_read_only import READ_CASES, EXPECTED_TOOLS, assert_demo_safe


class MCPVerifierContractTests(unittest.TestCase):
    def test_only_six_read_tools_are_invoked(self):
        called = {name for name, _, _ in READ_CASES}
        self.assertEqual(len(called), 6)
        self.assertTrue(called.issubset(EXPECTED_TOOLS))
        self.assertNotIn("order_create", called)
        self.assertNotIn("order_update", called)

    def test_wrong_target_or_enabled_mock_writes_are_rejected(self):
        for health in (
            {"mode": "production", "synthetic": True, "writes_enabled": False},
            {"mode": "deterministic-offline-demo", "synthetic": True, "writes_enabled": True},
            {"mode": "deterministic-offline-demo", "synthetic": False, "writes_enabled": False},
        ):
            with self.subTest(health=health), patch(
                "scripts.verify_mcp_read_only.get_json", return_value=health
            ), self.assertRaises(RuntimeError):
                assert_demo_safe()

    def test_safe_mock_preflight_counts_orders(self):
        health = {"mode": "deterministic-offline-demo",
                  "synthetic": True, "writes_enabled": False}
        orders = {"orders": [], "synthetic": True}
        with patch("scripts.verify_mcp_read_only.get_json", side_effect=[health, orders]):
            self.assertEqual(assert_demo_safe(), 0)


if __name__ == "__main__":
    unittest.main()
