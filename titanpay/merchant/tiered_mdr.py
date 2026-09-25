"""Amount-based pay-in MDR for merchants that use tiered rates."""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from merchant.kzt_settlement import merchant_fee_in_kzt, uses_melbet_kzt_settlement

# (min_inclusive, max_exclusive, mdr_percent) in order currency (RUB).
Tier = tuple[Decimal, Decimal, Decimal]

NSPAY_MDR_TIERS: Sequence[Tier] = (
    (Decimal("5000"), Decimal("10000"), Decimal("11")),
    (Decimal("10000"), Decimal("999999999"), Decimal("10.5")),
)

TIERED_MERCHANT_MDR: dict[str, Sequence[Tier]] = {
    "nspay": NSPAY_MDR_TIERS,
}


def effective_mdr_in(solution, amount) -> Decimal:
    username = getattr(getattr(solution.merchant, "user", None), "username", "") or ""
    tiers = TIERED_MERCHANT_MDR.get(username)
    if not tiers:
        return solution.mdr_in
    amt = Decimal(str(amount))
    for lo, hi, mdr in tiers:
        if lo <= amt < hi:
            return mdr
    return solution.mdr_in


def merchant_payin_fee(*, solution, amount: Decimal, usd_amount: Decimal) -> Decimal:
    mdr = effective_mdr_in(solution, amount)
    if uses_melbet_kzt_settlement(solution.merchant, solution.payment_system):
        return merchant_fee_in_kzt(amount, mdr)
    return mdr * usd_amount / Decimal(100)
