"""Strict validation for a stable server-issued order operation key."""
import re

_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{15,127}\Z", re.ASCII)


def validate_key(key: str | None) -> str:
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("idempotency_key must be an opaque server-issued 16..128 character token")
    return key


def order_number_for_key(key: str) -> str:
    """Stable ERP order number; same key yields same number across retries."""
    import hashlib
    validate_key(key)
    return "PI" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24].upper()
