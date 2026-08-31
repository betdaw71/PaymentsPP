"""Каноническая подпись мерчанта: SHA256(json_sorted(body) + private_key)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from payments.utils import UUIDEncoder


def canonical_json(data: Any) -> str:
    """Тот же JSON, по которому считается Signature: ключи отсортированы, без пробелов."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        cls=UUIDEncoder,
        ensure_ascii=True,
    )


def sign_canonical(data: Any, private_key) -> tuple[str, str]:
    """Вернуть (hex-подпись, каноническую JSON-строку)."""
    body = canonical_json(data)
    signature = hashlib.sha256((body + str(private_key)).encode()).hexdigest()
    return signature, body


def signed_json_headers(data: Any, private_key) -> tuple[dict[str, str], bytes]:
    """Заголовок Signature и тело, байты которого входят в хеш."""
    signature, body = sign_canonical(data, private_key)
    headers = {"Signature": signature, "Content-Type": "application/json"}
    return headers, body.encode()
