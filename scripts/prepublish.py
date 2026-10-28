"""Explicit, read-only pre-publication gate. Not a legal sign-off tool."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.audit_release import inspect


def release_gates(root: Path) -> list[str]:
    findings: list[str] = []
    _, issues = inspect(root)
    if issues:
        findings.append("SOURCE_SCAN_REVIEW_REQUIRED")
    license_path = root / "LICENSE"
    if not license_path.is_file() or not license_path.read_text(encoding="utf-8").strip():
        findings.append("LICENSE_NOT_APPROVED")
    # Legal/provenance/privacy sign-off is a manual, non-automatable gate.
    # Do not infer this from file existence, user-side test logs or the scan.
    findings.append("MANUAL_IP_PRIVACY_AND_THIRD_PARTY_REVIEW_REQUIRED")
    return findings


def main() -> int:
    findings = release_gates(ROOT)
    for reason in findings:
        print("PUBLISH_BLOCKER=" + reason)
    print("PUBLISH_PREFLIGHT=BLOCKED")
    print("ACTION=Review docs/PUBLISH_CHECKLIST.md before public distribution")
    # This helper intentionally cannot approve publication automatically.
    return 1


if __name__ == "__main__":
    sys.exit(main())
