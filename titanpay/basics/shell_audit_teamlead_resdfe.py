"""Сверка доли тимлида neuyz vs оборот resdfe (MSK).

После фикса: teamlead_percentage = % от usd_amount (оборота).

  docker compose exec -T -e HOURS=72 -e TEAMLEAD=neuyz -e TRADER=resdfe \\
    app python manage.py shell < titanpay/basics/shell_audit_teamlead_resdfe.py
"""
from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from basics.models import Trader, TraderTeam
from trade.models import InOrder, OutOrder, Transaction

HOURS = float(os.environ.get("HOURS", "72"))
TL = (os.environ.get("TEAMLEAD") or "neuyz").strip()
TRADER = (os.environ.get("TRADER") or "resdfe").strip()

since = timezone.now() - timedelta(hours=HOURS)
trader = Trader.objects.select_related("user", "team", "team__teamlead__user").filter(
    user__username__iexact=TRADER
).first()
if trader is None:
    raise SystemExit(f"trader {TRADER!r} not found")

team: TraderTeam | None = trader.team
pct = Decimal(str(getattr(team, "teamlead_percentage", 0) or 0))
tl_name = ""
if team and team.teamlead_id and team.teamlead.user_id:
    tl_name = team.teamlead.user.username

print(f"trader={trader.user.username} team={team.name if team else None}")
print(f"teamlead={tl_name!r} pct={pct}% (of turnover usd_amount) window={HOURS}h")

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
        to_balance=team.teamlead.balance if team and team.teamlead_id else None,
    ).aggregate(s=Sum("value"))["s"]
    if team and team.teamlead_id
    else Decimal("0")
) or Decimal("0")

# старые начисления могли быть % от trader_fee — для справки
old_expected_fee = Decimal("0")
trader_fees = (ins.aggregate(s=Sum("trader_fee"))["s"] or Decimal("0")) + (
    outs.aggregate(s=Sum("trader_fee"))["s"] or Decimal("0")
)
old_expected_fee = (trader_fees * pct / Decimal("100")).quantize(Decimal("0.01"))

print(f"Completed IN n={ins.count()} turnover_usd={turn_in}")
print(f"Completed OUT n={outs.count()} turnover_usd={turn_out}")
print(f"expected TL @ {pct}% of turnover: {expected}")
print(f"(legacy would be {pct}% of trader_fee={trader_fees}: {old_expected_fee})")
print(f"actual Teamlead commission to TL balance: {paid}")
print(f"gap vs turnover formula: {expected - paid}")
print("DONE")
