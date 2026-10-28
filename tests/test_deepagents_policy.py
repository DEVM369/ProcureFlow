"""Offline safety contracts for the optional true DeepAgents runtime probe."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "procureflow_deepagents_policy", ROOT / "scripts" / "deepagents_policy.py"
)
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)


def named(names):
    return [SimpleNamespace(name=n) for n in names]


class TrueDeepAgentsPolicyTests(unittest.TestCase):
    def test_exact_catalog_produces_six_reads(self):
        tools = named(sorted(POLICY.EXPECTED_CATALOG))
        reads = POLICY.enforce_safe_catalog(tools)
        self.assertEqual(len(reads), 6)
        self.assertFalse({t.name for t in reads} & POLICY.FORBIDDEN_WRITES)

    def test_unknown_missing_and_duplicate_catalog_rejected(self):
        base = sorted(POLICY.EXPECTED_CATALOG)
        for candidate in (base[:-1], base + ["external_query"],
                          base[:-1] + [base[0]]):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    POLICY.enforce_safe_catalog(named(candidate))

    def test_only_exact_read_only_subagents_allowed(self):
        safe = [{"name": n, "tools": named(sorted(names))}
                for n, names in POLICY.READ_ONLY_CHILD_TOOLS.items()]
        POLICY.enforce_subagent_capabilities(safe)
        with self.assertRaises(ValueError):
            POLICY.enforce_subagent_capabilities(safe + [safe[0]])
        unsafe = [{"name": entry["name"], "tools": list(entry["tools"])}
                  for entry in safe]
        unsafe[1]["tools"].append(SimpleNamespace(name="order_create"))
        with self.assertRaises(ValueError):
            POLICY.enforce_subagent_capabilities(unsafe)

    def test_graph_runner_requires_true_deepagents_api(self):
        source = (ROOT / "scripts" / "verify_deepagents_graph.py").read_text("utf-8")
        self.assertIn("from deepagents import create_deep_agent", source)
        self.assertIn("from langchain_core.language_models.chat_models import BaseChatModel", source)
        self.assertIn("await graph.ainvoke(", source)
        self.assertIn("from agent.middlewares.order_task_routing import OrderTaskRoutingMiddleware", source)
        self.assertIn('"http://127.0.0.1:18881"', source)
        self.assertNotIn("ChatOpenAI", source)


if __name__ == "__main__":
    unittest.main()
