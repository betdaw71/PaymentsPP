"""Проставить TraderTeamRates.mdr_in по сетке тетради (C2C / C2CKZT, KZT).

  docker compose exec -T app python manage.py shell < basics/shell_apply_psp_kzt_terms.py
  APPLY=1 — записать.

Курс PSP (xe+N / Bitzone Kaspi) — в dual_fx / PSP_XE_MARKUP_BY_TRADER, не здесь.
"""
from __future__ import annotations

import os
from decimal import Decimal

from basics.models import Trader, TraderTeamRates

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
PROD_PS = ("C2C", "C2CKZT")
PROD_CURRENCY = "KZT"

# Ставка in по договору (после dual FX комиссия считается с psp_usd, не урезать на спред).
MDR_IN = {
    "payplat1": Decimal("5.20"),
    "patriot1": Decimal("6.50"),
    "gipay1": Decimal("5.70"),
    "visionx1": Decimal("7.00"),
    "bitzone1": Decimal("6.50"),
    "layerone1": Decimal("6.00"),
    "prochub1": Decimal("7.00"),
    "nexus1": Decimal("6.50"),
    "plutus1": Decimal("6.50"),
}


def run() -> None:
    print(f"APPLY={int(APPLY)}")
    for username, mdr in MDR_IN.items():
        trader = Trader.objects.filter(user__username=username).select_related("user", "team").first()
        if trader is None:
            print(f"  ! {username}: no trader")
            continue
        rows = TraderTeamRates.objects.filter(team=trader.team).select_related(
            "payment_system", "payment_system__currency"
        )
        hit = 0
        for row in rows:
            ps = row.payment_system
            cur = ps.currency.symbol if ps.currency_id else "?"
            if ps.name not in PROD_PS or cur != PROD_CURRENCY:
                continue
            hit += 1
            if row.mdr_in != mdr:
                print(f"  {username} {ps.name}: {row.mdr_in}% → {mdr}%")
                if APPLY:
                    row.mdr_in = mdr
                    row.save(update_fields=["mdr_in"])
            else:
                print(f"  {username} {ps.name}: {row.mdr_in}% (ok)")
        if hit == 0:
            print(f"  ! {username}: no {PROD_PS} {PROD_CURRENCY} rates")


run()
