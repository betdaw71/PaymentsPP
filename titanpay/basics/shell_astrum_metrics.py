"""Замер Astrum (astrum_kzt / asterisk): выдача, конверсия, доля объёма vs остальные PSP.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_astrum_metrics.py

  HOURS=6 / DAYS=1  MERCHANT= (пусто = все)  PS=C2CKZT
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone

from payments.models import AstrumPayInSession, PayIn
from payments.psp_payin import parse_routing_share_map

HOURS = float(os.environ.get("HOURS") or "0")
DAYS = float(os.environ.get("DAYS") or ("0" if HOURS else "1"))
MERCHANT = (os.environ.get("MERCHANT") or "").strip()
PS = (os.environ.get("PS") or "").strip()
ASTRUM = (os.environ.get("TRADER") or "astrum_kzt").strip().lower()


class Cell:
    __slots__ = ("n", "issued", "success", "declined", "progress", "failed", "fiat_ok", "usd_ok")

    def __init__(self):
        self.n = self.issued = self.success = self.declined = self.progress = self.failed = 0
        self.fiat_ok = Decimal("0")
        self.usd_ok = Decimal("0")

    def add(self, pay_in) -> None:
        self.n += 1
        st = pay_in.status.name if pay_in.status_id else ""
        if st == "Declined":
            self.declined += 1
            return
        self.issued += 1
        if st == "Success":
            self.success += 1
            amt = Decimal(str(pay_in.amount or 0))
            self.fiat_ok += amt
            order = pay_in.order
            if order is not None:
                usd = order.psp_usd_amount or order.usd_amount or 0
                self.usd_ok += Decimal(str(usd or 0))
        elif st == "In Progress":
            self.progress += 1
        elif st in ("Failed", "Expired"):
            self.failed += 1

    def line(self, name: str) -> str:
        iss = self.issued or 1
        conv = (100.0 * self.success / iss) if self.issued else 0.0
        return (
            f"{name:16} n={self.n:4} issued={self.issued:4} ok={self.success:3} "
            f"prog={self.progress:3} fail={self.failed:3} dec={self.declined:3} "
            f"iss→ok={conv:5.1f}%  fiat_ok={self.fiat_ok:.0f}  usd_ok={self.usd_ok:.2f}"
        )


def provider_of(pay_in) -> str:
    order = pay_in.order
    if order is None or not order.payment_details_id:
        return "(no_req)"
    try:
        return (order.payment_details.group.trader.user.username or "?").lower()
    except Exception:  # noqa: BLE001
        return "(no_trader)"


def run() -> None:
    delta = timedelta(hours=HOURS) if HOURS > 0 else timedelta(days=DAYS or 1)
    since = timezone.now() - delta
    print(f"=== Astrum metrics since {since:%Y-%m-%d %H:%M} UTC ===")
    share = parse_routing_share_map()
    if share:
        total = sum(share.values()) or Decimal("1")
        a_w = share.get(ASTRUM)
        pct = ((a_w / total) * Decimal("100")) if a_w is not None else Decimal("0")
        print(f"SHARE configured: astrum≈{pct:.1f}%  map={{{', '.join(f'{k}:{v}' for k, v in share.items())}}}")
    else:
        print("SHARE map empty — cascade only")

    qs = PayIn.objects.filter(created_at__gte=since).select_related(
        "status",
        "payment_system",
        "merchant__user",
        "order",
        "order__payment_details__group__trader__user",
    )
    if MERCHANT:
        qs = qs.filter(merchant__user__username=MERCHANT)
    if PS:
        qs = qs.filter(payment_system__name=PS)

    by_psp: dict[str, Cell] = defaultdict(Cell)
    total = Cell()
    for pay_in in qs.iterator(chunk_size=500):
        cell = by_psp[provider_of(pay_in)]
        cell.add(pay_in)
        total.add(pay_in)

    print("\nby PSP (issued→Success):")
    print(total.line("ALL"))
    for name, cell in sorted(by_psp.items(), key=lambda kv: (-kv[1].issued, kv[0])):
        print(cell.line(name))

    astrum = by_psp.get(ASTRUM, Cell())
    issued_all = sum(c.issued for c in by_psp.values()) or 1
    share_actual = 100.0 * astrum.issued / issued_all
    print(
        f"\n{ASTRUM}: issued share actual={share_actual:.1f}% "
        f"(target ~30%)  iss→ok="
        f"{(100.0 * astrum.success / astrum.issued) if astrum.issued else 0:.1f}%"
    )

    sess = AstrumPayInSession.objects.filter(created_at__gte=since)
    sess_agg = sess.aggregate(
        n=Count("id"),
        with_deal=Count("id", filter=~Q(provider_deal_id="")),
        with_webhook=Count("id", filter=~Q(last_webhook_payload={})),
    )
    print(
        f"AstrumPayInSession: n={sess_agg['n']} with_deal={sess_agg['with_deal']} "
        f"with_webhook={sess_agg['with_webhook']}"
    )
    if MERCHANT:
        print(f"filter merchant={MERCHANT}")
    if PS:
        print(f"filter ps={PS}")
    print("DONE")


run()
