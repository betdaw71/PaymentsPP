"""
Опустить min_amount_in у живых KGS-групп Melbet, чтобы суммы ~150–300
не отсекались (diagnose: prisma/payplat no_free_card, resdfe in_lim=[2000..]).

  TRADERS=resdfe,resdfe1 \\
  MIN_IN=100 \\
  PS=PHONEKGS,C2CKGS \\
  docker compose exec -T -e TRADERS -e MIN_IN -e PS app \\
    python manage.py shell < titanpay/basics/shell_lower_melbet_kgs_min_in.py

DRY_RUN=1 — только показать, без save.
"""
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

from basics.models import PaymentDetailsGroup
from payments.psp_payin import psp_trader_usernames

TRADERS = [
    u.strip()
    for u in (os.environ.get("TRADERS") or "resdfe,resdfe1").split(",")
    if u.strip()
]
PS_NAMES = [
    p.strip().upper()
    for p in (os.environ.get("PS") or "PHONEKGS,C2CKGS").split(",")
    if p.strip()
]
try:
    MIN_IN = Decimal(str(os.environ.get("MIN_IN") or "100").strip())
except (InvalidOperation, ValueError):
    MIN_IN = Decimal("100")
DRY_RUN = (os.environ.get("DRY_RUN") or "0").strip().lower() in ("1", "true", "yes")
INCLUDE_PSP = (os.environ.get("INCLUDE_PSP") or "0").strip().lower() in ("1", "true", "yes")
psp = {n.lower() for n in psp_trader_usernames()}

print("=== Lower Melbet KGS min_amount_in ===")
print(f"traders={TRADERS} ps={PS_NAMES} min_in={MIN_IN} dry_run={DRY_RUN}")

for uname in TRADERS:
    if not INCLUDE_PSP and uname.lower() in psp:
        print(f"  skip PSP {uname} (INCLUDE_PSP=1 to touch)")
        continue
    qs = PaymentDetailsGroup.objects.filter(
        trader__user__username__iexact=uname,
        payment_system__name__in=PS_NAMES,
        currency__symbol="KGS",
    ).select_related("payment_system", "trader__user")
    if not qs.exists():
        print(f"  ! {uname}: no KGS groups for {PS_NAMES}")
        continue
    for g in qs:
        before = g.min_amount_in
        if before is not None and before <= MIN_IN:
            print(
                f"  {uname} {g.payment_system.name} {g.id} "
                f"min_in={before} (already <= {MIN_IN}) max={g.max_amount_in}"
            )
            continue
        print(
            f"  {uname} {g.payment_system.name} {g.id} "
            f"min_in {before} -> {MIN_IN} max={g.max_amount_in}"
            + (" [dry]" if DRY_RUN else "")
        )
        if not DRY_RUN:
            g.min_amount_in = MIN_IN
            g.save(update_fields=["min_amount_in", "updated_at"])

print("\nПроверка:")
print(
    "  TRADERS="
    + ",".join(TRADERS)
    + " docker compose exec -T -e TRADERS app "
    "python manage.py shell < titanpay/basics/shell_diagnose_melbet_kgs_live.py"
)
