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
from trade.routing.ps_names import c2ckzt_name, kzt_c2c_bank_ps_names, kzt_c2c_merchant_ps_names

TRADER = os.environ.get("TRADER", "resdfe").strip() or "resdfe"
HOURS = int(os.environ.get("HOURS", "24"))
OPEN = ("New", "Money sent by user", "Arbitrage", "Recalculation")


def _dec(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


def _route_ps_names() -> set[str]:
    names = set(kzt_c2c_merchant_ps_names()) | set(kzt_c2c_bank_ps_names()) | {c2ckzt_name(), "C2C"}
    return {n for n in names if n}


def _eligible_reasons(g: PaymentDetailsGroup, c: PaymentDetails, route_ps: set[str]) -> list[str]:
    bad: list[str] = []
    ps = g.payment_system.name if g.payment_system_id else ""
    if ps not in route_ps:
        bad.append(f"ps={ps!r} not in C2CKZT/transgran banks")
    if g.status != 1:
        bad.append(f"group.status={g.status} (need 1 Active)")
    if not g.in_active:
        bad.append("in_active=False")
    if (g.work_type or "") != "by_card":
        bad.append(f"work_type={g.work_type!r} (need by_card)")
    if c.status != 1:
        bad.append(f"detail.status={c.status}")
    if not (c.card_number or "").strip():
        bad.append("empty card_number")
    if c.sbp_enabled:
        bad.append("sbp_enabled")
    if c.sberpay_enabled:
        bad.append("sberpay_enabled")
    return bad


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
    route_ps = _route_ps_names()
    print("=" * 72)
    print(f"REQUISITE DISTRIBUTION  trader={trader.user.username}  window={HOURS}h")
    print(f"C2CKZT/transgran route PS: {sorted(route_ps)}")
    print("=" * 72)

    groups = list(
        PaymentDetailsGroup.objects.filter(trader=trader)
        .select_related("payment_system")
        .order_by("status", "-in_active", "owner")
    )
    print(f"groups: {len(groups)}")

    eligible_total = 0
    details_total = 0
    issued_eligible = 0
    issued_any = 0

    for g in groups:
        ps = g.payment_system.name if g.payment_system else "?"
        cards = list(
            PaymentDetails.objects.filter(group=g)
            .annotate(
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
            )
            .order_by("status", "card_number")
        )

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
        print(f"  issued_{HOURS}h={recent_group}  open_now={open_group}  cards={len(cards)}")
        for c in cards:
            details_total += 1
            issued_any += int(c.recent_cnt or 0)
            bad = _eligible_reasons(g, c, route_ps)
            ok = not bad
            if ok:
                eligible_total += 1
                issued_eligible += int(c.recent_cnt or 0)
            mask = (c.card_number or c.phone or c.deposit_number or "-")[-8:]
            tag = "ELIGIBLE" if ok else "BLOCKED"
            print(
                f"    [{tag}] …{mask}  status={c.status}  "
                f"open={c.open_cnt}  issued_{HOURS}h={c.recent_cnt}  "
                f"ok_{HOURS}h={c.recent_ok}  "
                f"sbp={int(bool(c.sbp_enabled))} sberpay={int(bool(c.sberpay_enabled))}  "
                f"id={c.id}"
            )
            if bad:
                print(f"           why: {'; '.join(bad)}")
            if ok and c.open_cnt:
                print(
                    f"           note: open={c.open_cnt} (Arbitrage/Recalc тоже считаются) "
                    f"— fair-pick предпочитает карты с open=0"
                )

    print(f"\n--- Transgran eligibility summary ---")
    print(f"  details_total={details_total}  eligible_for_C2CKZT_route={eligible_total}")
    if details_total and eligible_total < details_total:
        print(
            f"  → только {eligible_total}/{details_total} реквизитов реально могут получить "
            f"трансгран KZT; остальные BLOCKED (см. why выше)"
        )
    if eligible_total:
        print(f"  issued on eligible ({HOURS}h)={issued_eligible}")

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
            print(
                "  → сильный перекос: проверь BLOCKED + зависшие Arbitrage/Recalc на картах; "
                "fair-pick берёт least open/recent"
            )
        else:
            print("  → перекос умеренный / в пределах шума")


main()
