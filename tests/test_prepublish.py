import tempfile
from pathlib import Path
import unittest

from scripts.prepublish import release_gates


class PrepublishTests(unittest.TestCase):
    def test_unlicensed_candidate_stays_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "ok.txt").write_text("synthetic", encoding="utf-8")
            gates = release_gates(root)
            self.assertIn("LICENSE_NOT_APPROVED", gates)
            self.assertIn("MANUAL_IP_PRIVACY_AND_THIRD_PARTY_REVIEW_REQUIRED", gates)

    def test_license_does_not_automatically_clear_manual_review(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "LICENSE").write_text("Example local license text", encoding="utf-8")
            gates = release_gates(root)
            self.assertNotIn("LICENSE_NOT_APPROVED", gates)
            self.assertIn("MANUAL_IP_PRIVACY_AND_THIRD_PARTY_REVIEW_REQUIRED", gates)


if __name__ == "__main__":
    unittest.main()
