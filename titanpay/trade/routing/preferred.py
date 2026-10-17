"""Preferred trader pin for pay-out routing (merchant username → trader username)."""
from __future__ import annotations

import json

from django.conf import settings


def parse_preferred_trader_map(raw=None) -> dict[str, str]:
    if raw is None:
        raw = getattr(settings, "PAYOUT_PREFERRED_TRADER_BY_MERCHANT", None)
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(str(raw or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            data = {}
    out: dict[str, str] = {}
    for key, val in (data or {}).items():
        merchant = str(key).strip().lower()
        trader = str(val).strip()
        if merchant and trader:
            out[merchant] = trader
    return out


def preferred_payout_trader_username(merchant) -> str | None:
    """Melbet staging pin first, then PAYOUT_PREFERRED_TRADER_BY_MERCHANT (mostbet → payplat1)."""
    from merchant.kzt_settlement import melbet_kzt_test_trader_username

    test = melbet_kzt_test_trader_username(merchant)
    if test:
        return test
    if merchant is None or not getattr(merchant, "user", None):
        return None
    mapping = parse_preferred_trader_map()
    return mapping.get((merchant.user.username or "").strip().lower())
