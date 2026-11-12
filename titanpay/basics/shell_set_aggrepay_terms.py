"""Aggrepay: mdr_in=6% на C2C/C2CKZT KZT + напоминание xe+4 в .env.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_set_aggrepay_terms.py

  APPLY=1 — записать MDR.
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.conf import settings

from merchant.models import Merchant, MerchantSolution

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
USERNAME = (os.environ.get("MERCHANT") or "aggrepay").strip()
TARGET_MDR = Decimal((os.environ.get("MDR_IN") or "6").strip())
PS_NAMES = {"C2C", "C2CKZT"}

merchant = (
    Merchant.objects.select_related("user", "agent")
    .filter(user__username__iexact=USERNAME)
    .first()
)
if merchant is None:
    print(f"FAIL: merchant {USERNAME!r} not found")
    raise SystemExit(1)

print(f"merchant={USERNAME} APPLY={APPLY} target mdr_in={TARGET_MDR}% on {sorted(PS_NAMES)}")
print(f"XE_KZT_MARKUP_BY_MERCHANT={settings.XE_KZT_MARKUP_BY_MERCHANT}")
print("  → нужен \"aggrepay\":\"1.04\" (xe+4). Если нет в .env — добавь и restart app.")

sols = MerchantSolution.objects.filter(merchant=merchant).select_related(
    "payment_system", "payment_system__currency", "traffic"
)
hit = 0
for sol in sols:
    ps = sol.payment_system
    if ps is None or ps.name not in PS_NAMES:
        continue
    cur = ps.currency.symbol if ps.currency_id else "?"
    if cur != "KZT":
        continue
    hit += 1
    traffic = getattr(getattr(sol, "traffic", None), "name", None) or "—"
    if sol.mdr_in != TARGET_MDR:
        print(
            f"  solution {sol.id} {ps.name} ftd={sol.ftd} traffic={traffic}: "
            f"{sol.mdr_in}% → {TARGET_MDR}%"
        )
        if APPLY:
            sol.mdr_in = TARGET_MDR
            sol.save(update_fields=["mdr_in"])
    else:
        print(f"  solution {sol.id} {ps.name} ftd={sol.ftd} traffic={traffic}: {sol.mdr_in}% (ok)")

if hit == 0:
    print("  ! no C2C/C2CKZT KZT solutions")
print("DONE")
