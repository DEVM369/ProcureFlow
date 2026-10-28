"""Dependency-free tests of the real-source Agent MCP loader's safe adaptation."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


TOOL_NAMES = (
    "supplier_query", "part_query", "part_search", "part_by_supplier",
    "inventory_warning", "order_search_details", "order_create", "order_update",
)


class FakeMCPClient:
    names = TOOL_NAMES
    last_config = None

    def __init__(self, config):
        self.__class__.last_config = config

    async def get_tools(self, *, server_name):
        assert server_name == "erp-api"
        return [SimpleNamespace(name=name) for name in self.names]


def load_adapted_source_with_fake_mcp():
    root = Path(__file__).resolve().parents[1]
    path = root / "src" / "agent" / "tools" / "mcp_client.py"
    module_name = "isolated_test_agent_mcp_loader"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    pkg = ModuleType("langchain_mcp_adapters")
    client_module = ModuleType("langchain_mcp_adapters.client")
    client_module.MultiServerMCPClient = FakeMCPClient
    with patch.dict(sys.modules, {"langchain_mcp_adapters": pkg,
                                  "langchain_mcp_adapters.client": client_module}):
        spec.loader.exec_module(module)
    return module


class AgentMCPConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = load_adapted_source_with_fake_mcp()

    def test_local_only_is_accepted(self):
        config = self.loader.validate_mcp_server_config(self.loader.MCP_SERVER_CONFIG)
        self.assertEqual(config, {"erp-api": {
            "url": "http://127.0.0.1:18880/mcp", "transport": "streamable_http"
        }})

    def test_remote_targets_and_additional_servers_are_rejected(self):
        cases = (
            {"erp-api": {"url": "http://127.0.0.1:8000/mcp", "transport": "streamable_http"}},
            {"erp-api": {"url": "https://example.invalid/mcp", "transport": "streamable_http"}},
            {"erp-api": {"url": "http://127.0.0.1:18880/mcp", "transport": "sse"}},
            {"erp-api": {"url": "http://127.0.0.1:18880/mcp", "transport": "streamable_http"},
             "analysis": {"url": "https://example.invalid/mcp", "transport": "streamable_http"}},
            {},
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.loader.validate_mcp_server_config(case)


class AgentMCPGroupingTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = load_adapted_source_with_fake_mcp()

    async def test_eight_tools_split_five_plus_three_and_no_remote_chart(self):
        FakeMCPClient.names = TOOL_NAMES
        tools, analyst, order, charts = await self.loader.load_mcp_tools()
        self.assertEqual(len(tools), 8)
        self.assertEqual({t.name for t in analyst}, set(TOOL_NAMES[:5]))
        self.assertEqual({t.name for t in order}, set(TOOL_NAMES[5:]))
        self.assertEqual(charts, [])
        self.assertEqual(set(FakeMCPClient.last_config), {"erp-api"})

    async def test_duplicate_or_unexpected_tool_fails_closed(self):
        for names in (TOOL_NAMES[:-1], TOOL_NAMES + ("external_tool",),
                      TOOL_NAMES + ("order_create",)):
            FakeMCPClient.names = names
            with self.subTest(names=names), self.assertRaises(RuntimeError):
                await self.loader.load_mcp_tools()
        FakeMCPClient.names = TOOL_NAMES


if __name__ == "__main__":
    unittest.main()
