"""
Вернуть in_active=True живым KGS-группам после FORCE_PRISMA=1 теста.

  TRADERS=resdfe,resdfe1 \\
  docker compose exec -T -e TRADERS app \\
    python manage.py shell < titanpay/basics/shell_restore_melbet_kgs_in_active.py

PS=PHONEKGS,C2CKGS,QRKGS  (по умолчанию все три)
"""
from __future__ import annotations

import os

from basics.models import PaymentDetailsGroup
from payments.prisma_client import prisma_trader_username
from payments.psp_payin import psp_trader_usernames

TRADERS = [
    u.strip()
    for u in (os.environ.get("TRADERS") or "resdfe,resdfe1").split(",")
    if u.strip()
]
PS_NAMES = [
    p.strip().upper()
    for p in (os.environ.get("PS") or "PHONEKGS,C2CKGS,QRKGS").split(",")
    if p.strip()
]
# Не трогаем виртуальные PSP, кроме явного INCLUDE_PSP=1
INCLUDE_PSP = (os.environ.get("INCLUDE_PSP") or "0").strip().lower() in ("1", "true", "yes")
psp = {n.lower() for n in psp_trader_usernames()}
prisma = prisma_trader_username().lower()

print("=== Restore Melbet KGS in_active ===")
print(f"traders={TRADERS} ps={PS_NAMES}")

for uname in TRADERS:
    if not INCLUDE_PSP and uname.lower() in psp and uname.lower() != prisma:
        # payplat/gipay и т.п. — только если явно попросили
        pass
    qs = PaymentDetailsGroup.objects.filter(
        trader__user__username__iexact=uname,
        payment_system__name__in=PS_NAMES,
        currency__symbol="KGS",
    ).select_related("payment_system", "trader__user")
    if not qs.exists():
        print(f"  ! {uname}: no KGS groups for {PS_NAMES}")
        continue
    for g in qs:
        before = g.in_active
        fields = []
        if g.status != 1:
            g.status = 1
            fields.append("status")
        if not g.in_active:
            g.in_active = True
            fields.append("in_active")
        if fields:
            g.save(update_fields=[*fields, "updated_at"])
        print(
            f"  {uname} {g.payment_system.name} {g.id} "
            f"in_active {before} -> {g.in_active} status={g.status}"
        )

print("\nПроверка:")
print(
    "  TRADERS="
    + ",".join(TRADERS)
    + " docker compose exec -T -e TRADERS app "
    "python manage.py shell < titanpay/basics/shell_diagnose_melbet_kgs_live.py"
)
