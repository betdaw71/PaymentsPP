"""
Остатки / сеттлменты pandapay за октябрь (для сверки).

  docker compose exec -T app python manage.py shell \
    < titanpay/basics/shell_pandapay_october_ledger.py
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Sum
from django.utils import timezone

from merchant.models import Merchant
from trade.models import Transaction, WithdrawalRequest

MSK = ZoneInfo("Europe/Moscow")
YEAR, MONTH = 2026, 10
MERCHANT = "pandapay"

oct1 = datetime(YEAR, MONTH, 1, tzinfo=MSK)
nov1 = datetime(YEAR, MONTH + 1, 1, tzinfo=MSK) if MONTH < 12 else datetime(YEAR + 1, 1, 1, tzinfo=MSK)

m = Merchant.objects.select_related("user", "balance").get(user__username=MERCHANT)
bal = m.balance
if bal is None:
    raise SystemExit("pandapay has no USDT balance")


def net_delta(since, until) -> Decimal:
    inn = (
        Transaction.objects.filter(
            to_balance=bal, creation_date__gte=since, creation_date__lt=until
        ).aggregate(s=Sum("value"))["s"]
        or Decimal("0")
    )
    out = (
        Transaction.objects.filter(
            from_balance=bal, creation_date__gte=since, creation_date__lt=until
        ).aggregate(s=Sum("value"))["s"]
        or Decimal("0")
    )
    return inn - out


now = timezone.now()
delta_after_oct = net_delta(nov1, now + timedelta(days=1))
bal_31 = (bal.amount or Decimal("0")) - delta_after_oct
delta_oct = net_delta(oct1, nov1)
bal_1 = bal_31 - delta_oct

wrs = WithdrawalRequest.objects.filter(
    from_user=m.user, status=1, date__gte=oct1, date__lt=nov1
)
settle = wrs.aggregate(s=Sum("amount"))["s"] or Decimal("0")

print("MERCHANT", MERCHANT)
print("BALANCE_NOW", bal.amount)
print("BALANCE_1_10", bal_1)
print("BALANCE_31_10", bal_31)
print("NET_DELTA_OCT", delta_oct)
print("SETTLEMENTS_APPROVED_USDT", settle)
print("SETTLEMENTS_N", wrs.count())
for w in wrs.order_by("date"):
    when = w.date.astimezone(MSK).isoformat() if w.date else ""
    print("WR", when, w.amount, w.address_to, (w.comment or "")[:80])
print("DONE")
