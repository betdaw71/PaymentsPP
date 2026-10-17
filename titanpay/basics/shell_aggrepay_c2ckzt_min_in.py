"""
Aggrepay C2CKZT: min_limit_in = 4000 для FTD и повторных.

По умолчанию DRY_RUN. APPLY=1 пишет в БД.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_aggrepay_c2ckzt_min_in.py

  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_aggrepay_c2ckzt_min_in.py
"""
from __future__ import annotations

import os
from decimal import Decimal

from merchant.models import MerchantSolution

MERCHANT = (os.environ.get("MERCHANT") or "aggrepay").strip()
PS = (os.environ.get("PS") or "C2CKZT").strip()
NEW_MIN = Decimal(os.environ.get("MIN_IN") or "4000")


def env_apply() -> bool:
    raw = (os.environ.get("APPLY") or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


apply = env_apply()
print(f"aggrepay C2CKZT min_in={NEW_MIN}  mode={'APPLY' if apply else 'DRY_RUN'}\n")

sols = list(
    MerchantSolution.objects.filter(
        merchant__user__username=MERCHANT,
        payment_system__name=PS,
    ).select_related("payment_system", "merchant__user", "traffic").order_by("ftd", "status")
)
if not sols:
    print(f"NOT FOUND MerchantSolution merchant={MERCHANT} ps={PS}")
else:
    for sol in sols:
        ftd = "FTD/первичка" if sol.ftd else "повтор/вторичка"
        print(
            f"  id={sol.id}  status={sol.status}  {ftd}  traffic={sol.traffic.name if sol.traffic_id else '-'}  "
            f"in=[{sol.min_limit_in} .. {sol.max_limit_in}]  out=[{sol.min_limit_out} .. {sol.max_limit_out}]"
        )
        if sol.min_limit_in == NEW_MIN:
            print("    already ok")
            continue
        if sol.max_limit_in and sol.max_limit_in < NEW_MIN:
            print(f"    SKIP: max_limit_in={sol.max_limit_in} < {NEW_MIN}")
            continue
        if not apply:
            print(f"    DRY: min_limit_in {sol.min_limit_in} -> {NEW_MIN}")
            continue
        old = sol.min_limit_in
        sol.min_limit_in = NEW_MIN
        sol.save(update_fields=["min_limit_in"])
        print(f"    APPLY min_limit_in {old} -> {sol.min_limit_in}")

if not apply:
    print("\nDRY_RUN — для записи: -e APPLY=1")
