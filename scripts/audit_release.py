"""Conservative, read-only scanner for the distributed source tree.

Not a substitute for human secret inspection, dependency/license compliance,
or a professional release review. It prints paths/reasons, NEVER secret values.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys


EXCLUDED_DIRECTORIES = frozenset({".git", "__pycache__", ".pytest_cache", "node_modules", ".venv"})
RISKY_EXTENSIONS = frozenset({".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db", ".zip"})
RISKY_NAMES = frozenset({".env", "motorparts_db.sql", "credentials.json", "secrets.json"})
# One inspected, original browser screenshot. Keep binaries blocked unless byte-for-byte
# identical to the approved fixture (never allow images by extension alone).
APPROVED_BINARY_ASSETS = {
    "docs/assets/procureflow-demo.png": "8aeb60a1fee8df46600f5e352ded6598212557fb91eead7a025fe6cf87b1692b",
}
SECRETS = {
    "private_key": re.compile(rb"-----BEGIN [^-\r\n]*PRIVATE KEY-----"),
    "openai_key": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "mongodb_password_uri": re.compile(rb"mongodb(?:\+srv)?://[^/:@\s]+:[^/@\s]+@", re.I),
    "github_token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{24,}\b"),
    "aws_access_key_id": re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
}


def inspect(root: Path) -> tuple[int, list[tuple[str, str]]]:
    issues: list[tuple[str, str]] = []
    inspected = 0
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in rel.parts):
            continue
        if path.is_symlink():
            issues.append((rel.as_posix(), "symbolic_link"))
            continue
        if not path.is_file():
            continue
        inspected += 1
        name = path.name.lower()
        if (name in RISKY_NAMES or name.startswith(".env.")
                or path.suffix.lower() in RISKY_EXTENSIONS):
            issues.append((rel.as_posix(), "risky_filename"))
        try:
            if path.stat().st_size > 2_000_000:
                issues.append((rel.as_posix(), "large_file_manual_review"))
                continue
            data = path.read_bytes()
        except OSError:
            issues.append((rel.as_posix(), "unreadable"))
            continue
        approved_digest = APPROVED_BINARY_ASSETS.get(rel.as_posix())
        if approved_digest is not None:
            if hashlib.sha256(data).hexdigest() != approved_digest:
                issues.append((rel.as_posix(), "approved_asset_hash_mismatch"))
            continue
        if b"\x00" in data:
            issues.append((rel.as_posix(), "binary_file_manual_review"))
            continue
        for reason, pattern in SECRETS.items():
            if pattern.search(data):
                issues.append((rel.as_posix(), reason))
    return inspected, issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only source scan")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error("--root must identify an existing directory")
    inspected, issues = inspect(args.root.resolve())
    print(f"PUBLIC_SCAN_FILES={inspected}")
    print(f"PUBLIC_SCAN_FINDINGS={len(issues)}")
    for rel, reason in issues:
        print(f"REVIEW_PATH={rel} REASON={reason}")
    print("PUBLIC_SOURCE_SCAN=" + ("PASS" if not issues else "MANUAL_REVIEW_REQUIRED"))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
