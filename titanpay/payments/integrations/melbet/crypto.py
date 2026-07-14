from __future__ import annotations

import hashlib
import hmac


def sign_body(body: bytes, secret_key: str) -> str:
    """HMAC-SHA256 hex digest over raw request body (empty bytes for GET)."""
    key = secret_key.encode("utf-8")
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def verify_body(body: bytes, signature: str, secret_key: str) -> bool:
    if not signature:
        return False
    expected = sign_body(body, secret_key)
    return hmac.compare_digest(expected, signature.strip())
