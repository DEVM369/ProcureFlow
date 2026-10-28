"""The public-file scanner must catch representative risky content."""

import shutil
import tempfile
from pathlib import Path
import unittest

from scripts.audit_release import inspect


class SourceAuditTests(unittest.TestCase):
    def test_clean_source_is_accepted(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "safe.py").write_text("DATA = 'synthetic demo'\n", encoding="utf-8")
            count, issues = inspect(root)
            self.assertEqual(count, 1)
            self.assertEqual(issues, [])

    def test_openai_shaped_string_is_flagged_without_printing_value(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "bad.py").write_bytes(b"sk-" + b"a" * 24)
            _, issues = inspect(root)
            self.assertEqual(issues, [("bad.py", "openai_key")])

    def test_approved_demo_screenshot_is_hash_pinned(self):
        original = Path(__file__).resolve().parents[1] / "docs/assets/procureflow-demo.png"
        with tempfile.TemporaryDirectory() as dirname:
            screenshot = Path(dirname) / "docs/assets/procureflow-demo.png"
            screenshot.parent.mkdir(parents=True)
            shutil.copyfile(original, screenshot)
            count, issues = inspect(Path(dirname))
            self.assertEqual(count, 1)
            self.assertEqual(issues, [])
            with screenshot.open("ab") as handle:
                handle.write(b"modified")
            _, issues = inspect(Path(dirname))
            self.assertEqual(issues, [("docs/assets/procureflow-demo.png", "approved_asset_hash_mismatch")])

    def test_unknown_binary_is_still_blocked(self):
        with tempfile.TemporaryDirectory() as dirname:
            binary = Path(dirname) / "docs/assets/unknown.png"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00more")
            _, issues = inspect(Path(dirname))
            self.assertEqual(issues, [("docs/assets/unknown.png", "binary_file_manual_review")])

    def test_dot_env_and_database_dump_are_blocked(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / ".env").write_text("SAMPLE=1", encoding="utf-8")
            (root / "motorparts_db.sql").write_text("SELECT 1;", encoding="utf-8")
            _, issues = inspect(root)
            self.assertEqual({reason for _, reason in issues}, {"risky_filename"})
            self.assertEqual(len(issues), 2)


if __name__ == "__main__":
    unittest.main()
