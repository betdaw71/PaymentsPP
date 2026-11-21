"""Доначислить тимлиду разницу: % от оборота − уже уплаченные Teamlead commission.

Списывает с balance_usdt трейдера (как live complete), на баланс тимлида.

  # dry-run за 72ч
  docker compose exec -T -e HOURS=72 -e TEAMLEAD=neuyz -e TRADER=resdfe \\
    app python manage.py shell < titanpay/basics/shell_backfill_teamlead_turnover.py

  # записать
  docker compose exec -T -e HOURS=72 -e APPLY=1 -e TEAMLEAD=neuyz -e TRADER=resdfe \\
    app python manage.py shell < titanpay/basics/shell_backfill_teamlead_turnover.py
"""
from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from basics.models import Trader
from trade.models import InOrder, OutOrder, Transaction, TransactionType

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
HOURS = float(os.environ.get("HOURS", "72"))
TL = (os.environ.get("TEAMLEAD") or "neuyz").strip()
TRADER = (os.environ.get("TRADER") or "resdfe").strip()

since = timezone.now() - timedelta(hours=HOURS)
trader = (
    Trader.objects.select_related("user", "team", "team__teamlead__user", "balance_usdt")
    .filter(user__username__iexact=TRADER)
    .first()
)
if trader is None or trader.team_id is None or trader.team.teamlead_id is None:
    raise SystemExit(f"FAIL: trader {TRADER!r} or teamlead link missing")

tl = trader.team.teamlead
if tl.user.username.lower() != TL.lower():
    print(f"WARN: team.teamlead={tl.user.username!r} != requested {TL!r} — using linked TL")

pct = Decimal(str(trader.team.teamlead_percentage or 0))
ins = InOrder.objects.filter(
    status__name="Completed",
    completion_date__gte=since,
    payment_details__group__trader=trader,
)
outs = OutOrder.objects.filter(
    status__name="Completed",
    completion_date__gte=since,
    payment_details__group__trader=trader,
)
turn_in = ins.aggregate(s=Sum("usd_amount"))["s"] or Decimal("0")
turn_out = outs.aggregate(s=Sum("usd_amount"))["s"] or Decimal("0")
expected = ((turn_in + turn_out) * pct / Decimal("100")).quantize(Decimal("0.01"))

paid = (
    Transaction.objects.filter(
        comment="Teamlead commission",
        creation_date__gte=since,
        to_balance_id=tl.balance_id,
    ).aggregate(s=Sum("value"))["s"]
    or Decimal("0")
)
gap = (expected - paid).quantize(Decimal("0.01"))

print(f"trader={trader.user.username} bal={trader.balance_usdt.amount}")
print(f"teamlead={tl.user.username} bal={tl.balance.amount} pct={pct}%")
print(f"window={HOURS}h turnover={turn_in + turn_out} expected={expected} paid={paid} gap={gap}")
print(f"APPLY={APPLY}")

if gap <= 0:
    print("nothing to backfill (gap<=0)")
    print("DONE")
    raise SystemExit(0)

if trader.balance_usdt.amount < gap:
    print(f"FAIL: trader balance {trader.balance_usdt.amount} < gap {gap}")
    raise SystemExit(1)

if not APPLY:
    print("DRY-RUN — APPLY=1 чтобы провести Transaction Teamlead commission (backfill)")
    print("DONE")
    raise SystemExit(0)

tx_type = TransactionType.objects.get(name="Charge")
with transaction.atomic():
    Transaction.create(
        _from=trader.balance_usdt,
        _to=tl.balance,
        value=gap,
        _transaction_type=tx_type,
        _comment="Teamlead commission",
    )
trader.balance_usdt.refresh_from_db()
tl.balance.refresh_from_db()
print(f"credited {gap} → {tl.user.username}")
print(f"trader bal now={trader.balance_usdt.amount} tl bal now={tl.balance.amount}")
print("DONE")
