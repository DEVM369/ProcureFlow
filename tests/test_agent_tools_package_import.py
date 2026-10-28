"""Prevent optional private Agent tools from blocking the safe MCP adapter.

Only Python stdlib is needed.  In a subprocess, fake the optional third-party
MCP client so importing the real package path and loading its tool groups can
be checked without network activity or a running model.
"""

from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AgentToolsPackageImportTests(unittest.TestCase):
    def test_package_is_importable_without_private_search_or_chart_modules(self):
        source = textwrap.dedent("""
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path.cwd() / 'src'))
            import agent.tools
            assert not hasattr(agent.tools, 'web_search')
            assert not hasattr(agent.tools, 'create_generate_chart_tool')
            print('AGENT_TOOLS_PACKAGE_IMPORT=PASS')
        """)
        completed = subprocess.run(
            [sys.executable, "-B", "-c", source], cwd=ROOT,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("AGENT_TOOLS_PACKAGE_IMPORT=PASS", completed.stdout)

    def test_mcp_loader_imports_via_actual_package_and_stays_local_only(self):
        source = textwrap.dedent("""
            import asyncio
            import sys
            from pathlib import Path
            from types import ModuleType, SimpleNamespace

            sys.path.insert(0, str(Path.cwd() / 'src'))
            pkg = ModuleType('langchain_mcp_adapters')
            client_mod = ModuleType('langchain_mcp_adapters.client')
            class FakeMCPClient:
                def __init__(self, config):
                    assert config == {'erp-api': {
                        'url': 'http://127.0.0.1:18880/mcp',
                        'transport': 'streamable_http',
                    }}
                async def get_tools(self, *, server_name):
                    assert server_name == 'erp-api'
                    return [SimpleNamespace(name=n) for n in (
                        'supplier_query', 'part_query', 'part_search',
                        'part_by_supplier', 'inventory_warning',
                        'order_search_details', 'order_create', 'order_update',
                    )]
            client_mod.MultiServerMCPClient = FakeMCPClient
            sys.modules['langchain_mcp_adapters'] = pkg
            sys.modules['langchain_mcp_adapters.client'] = client_mod

            from agent.tools.mcp_client import load_mcp_tools
            async def check():
                groups = await load_mcp_tools()
                assert tuple(len(group) for group in groups) == (8, 5, 3, 0)
                assert {t.name for t in groups[1]} == {
                    'supplier_query', 'part_query', 'part_search',
                    'part_by_supplier', 'inventory_warning',
                }
            asyncio.run(check())
            print('AGENT_MCP_PACKAGE_IMPORT=PASS')
        """)
        completed = subprocess.run(
            [sys.executable, "-B", "-c", source], cwd=ROOT,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("AGENT_MCP_PACKAGE_IMPORT=PASS", completed.stdout)


if __name__ == "__main__":
    unittest.main()
