"""
Диагностика распределения заявок по реквизитам трейдера.

  docker compose exec -T -e TRADER=resdfe app \\
    python manage.py shell < titanpay/basics/shell_diagnose_trader_requisites.py

Опционально HOURS=24 (окно статистики, по умолчанию 24).
"""
from __future__ import annotations

import os
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone

from basics.models import PaymentDetails, PaymentDetailsGroup, Trader
from trade.models import InOrder

TRADER = os.environ.get("TRADER", "resdfe").strip() or "resdfe"
HOURS = int(os.environ.get("HOURS", "24"))
OPEN = ("New", "Money sent by user", "Arbitrage", "Recalculation")


def _dec(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def main() -> None:
    trader = (
        Trader.objects.select_related("user")
        .filter(user__username__iexact=TRADER)
        .first()
    )
    if trader is None:
        print(f"Trader {TRADER!r} not found")
        return

    since = timezone.now() - timedelta(hours=HOURS)
    print("=" * 72)
    print(f"REQUISITE DISTRIBUTION  trader={trader.user.username}  window={HOURS}h")
    print("=" * 72)

    groups = list(
        PaymentDetailsGroup.objects.filter(trader=trader)
        .select_related("payment_system")
        .order_by("status", "-in_active", "owner")
    )
    print(f"groups: {len(groups)}")

    for g in groups:
        ps = g.payment_system.name if g.payment_system else "?"
        cards = PaymentDetails.objects.filter(group=g).annotate(
            open_cnt=Count("inorders", filter=Q(inorders__status__name__in=OPEN), distinct=True),
            recent_cnt=Count(
                "inorders",
                filter=Q(inorders__creation_date__gte=since),
                distinct=True,
            ),
            recent_ok=Count(
                "inorders",
                filter=Q(inorders__creation_date__gte=since, inorders__status__name="Completed"),
                distinct=True,
            ),
        ).order_by("status", "card_number")

        recent_group = (
            InOrder.objects.filter(payment_details__group=g, creation_date__gte=since).count()
        )
        open_group = InOrder.objects.filter(
            payment_details__group=g, status__name__in=OPEN
        ).count()

        print(
            f"\nGROUP {g.id}  owner={g.owner!r}  ps={ps}  status={g.status} "
            f"in_active={g.in_active} work={g.work_type}"
        )
        print(
            f"  vol={_dec(g.current_volume)}/{_dec(g.limit_per_period)}  "
            f"amount=[{_dec(g.min_amount_in)}..{_dec(g.max_amount_in)}]  "
            f"interval={getattr(g, 'deal_interval_sec', 0) or 0}s  "
            f"amount_diff={getattr(g, 'amount_diff', 0) or 0}  "
            f"traffic={[t.name for t in g.allowed_traffic.all()]}"
        )
        print(f"  issued_{HOURS}h={recent_group}  open_now={open_group}  cards={cards.count()}")
        for c in cards:
            mask = (c.card_number or c.phone or c.deposit_number or "-")[-8:]
            print(
                f"    card …{mask}  status={c.status}  "
                f"open={c.open_cnt}  issued_{HOURS}h={c.recent_cnt}  "
                f"ok_{HOURS}h={c.recent_ok}  "
                f"sbp={int(bool(c.sbp_enabled))} sberpay={int(bool(c.sberpay_enabled))}  "
                f"id={c.id}"
            )

    totals = (
        InOrder.objects.filter(
            payment_details__group__trader=trader,
            creation_date__gte=since,
        )
        .values("payment_details_id")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    n_cards = totals.count()
    if n_cards:
        counts = [row["n"] for row in totals]
        print(f"\n--- Fairness ({HOURS}h by card) ---")
        print(f"  cards_with_orders: {n_cards}")
        print(f"  min/median/max issued: {min(counts)} / {sorted(counts)[len(counts)//2]} / {max(counts)}")
        if max(counts) >= 3 * max(min(counts), 1):
            print("  → сильный перекос: раньше был random pick; после фикса — least-loaded")
        else:
            print("  → перекос умеренный / в пределах шума")


main()
