"""
Конверсия Melbet (когорта PayIn.created_at) интервалами — чтобы увидеть сдвиг
после выгрузки новой платёжной страницы.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_melbet_conversion_intervals.py

  HOURS=3 DAYS=3
  SINCE='2026-10-16 12:00' UNTIL='2026-10-17 12:00'
  DEPLOY='2026-10-16 21:00'   # вертикальная метка в таблице
  TZ=UTC|Europe/Moscow
  MERCHANT=melbet PS=C2CKZT

iss→ok  = Success / (create − Declined)  — конверсия с выданными реквизитами
iss→paid = клик «Я оплатил» / issued     — UX страницы
cr→ok   = Success / create
Последний интервал ещё дозревает (In Progress).
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.models import PayIn

MERCHANT = (os.environ.get("MERCHANT") or "melbet").strip()
PS = (os.environ.get("PS") or "").strip()
HOURS = max(1, int(os.environ.get("HOURS") or "3"))
DAYS = float(os.environ.get("DAYS") or "3")
SINCE_RAW = (os.environ.get("SINCE") or "").strip()
UNTIL_RAW = (os.environ.get("UNTIL") or "").strip()
DEPLOY_RAW = (os.environ.get("DEPLOY") or "").strip()
TZ_NAME = (os.environ.get("TZ") or "UTC").strip() or "UTC"
TZ = ZoneInfo(TZ_NAME)

PAID_ORDER = frozenset({"Money sent by user", "Arbitrage", "Completed"})
OPEN_PAYIN = frozenset({"In Progress", "Pending"})


def _parse(raw: str) -> datetime:
    raw = raw.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=TZ)
            return dt.astimezone(TZ)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: {raw!r}")


def _floor(dt: datetime) -> datetime:
    dt = dt.astimezone(TZ)
    hour = (dt.hour // HOURS) * HOURS
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0)


def _window() -> tuple[datetime, datetime]:
    end = _parse(UNTIL_RAW) if UNTIL_RAW else timezone.now().astimezone(TZ)
    if SINCE_RAW:
        start = _parse(SINCE_RAW)
    else:
        start = end - timedelta(days=DAYS)
    return _floor(start), end


class Cell:
    __slots__ = ("n", "declined", "success", "progress", "failed", "paid", "fiat_ok")

    def __init__(self):
        self.n = 0
        self.declined = 0
        self.success = 0
        self.progress = 0
        self.failed = 0
        self.paid = 0
        self.fiat_ok = Decimal("0")

    def add(self, status: str, order_status: str | None, amount) -> None:
        self.n += 1
        if status == "Declined":
            self.declined += 1
            return
        if status == "Success":
            self.success += 1
            self.fiat_ok += Decimal(str(amount or 0))
        elif status in OPEN_PAYIN:
            self.progress += 1
        else:
            self.failed += 1
        if order_status in PAID_ORDER or status == "Success":
            self.paid += 1

    @property
    def issued(self) -> int:
        return self.n - self.declined

    def pct(self, num: int, den: int) -> str:
        if den <= 0:
            return "   -"
        return f"{100.0 * num / den:5.1f}%"


def run() -> None:
    start, end = _window()
    deploy = _parse(DEPLOY_RAW) if DEPLOY_RAW else None

    qs = PayIn.objects.filter(
        merchant__user__username=MERCHANT,
        created_at__gte=start,
        created_at__lt=end,
    )
    if PS:
        qs = qs.filter(payment_system__name__iexact=PS)

    rows = qs.values_list("created_at", "status__name", "order__status__name", "amount")
    buckets: dict[datetime, Cell] = defaultdict(Cell)
    total = Cell()
    n = 0
    for created, status, order_status, amount in rows.iterator():
        n += 1
        if timezone.is_naive(created):
            created = timezone.make_aware(created)
        key = _floor(created.astimezone(TZ))
        buckets[key].add(status or "-", order_status, amount)
        total.add(status or "-", order_status, amount)

    keys = []
    cur = start
    while cur < end:
        keys.append(cur)
        cur += timedelta(hours=HOURS)

    print("=" * 108)
    print(f"MELBET CONVERSION  {HOURS}h buckets")
    print(f"  merchant={MERCHANT}  ps={PS or '(all)'}  tz={TZ_NAME}")
    print(f"  window={start:%Y-%m-%d %H:%M} .. {end:%Y-%m-%d %H:%M}  n={n}")
    if deploy:
        print(f"  deploy mark={deploy:%Y-%m-%d %H:%M %Z}")
    print("=" * 108)
    print(
        f"{'interval':<22} {'n':>5} {'decl':>5} {'iss':>5} {'ok':>5} {'prog':>5} "
        f"{'fail':>5} {'paid':>5}  iss→ok  Δ     cr→ok  iss→paid  ok_fiat"
    )
    print("-" * 108)

    prev_iss_ok: float | None = None
    now = timezone.now().astimezone(TZ)
    for key in keys:
        if deploy and key <= deploy < key + timedelta(hours=HOURS):
            print(f"  >>> DEPLOY {deploy:%Y-%m-%d %H:%M %Z} <<<")
        cell = buckets.get(key) or Cell()
        iss_ok = (100.0 * cell.success / cell.issued) if cell.issued else None
        delta = ""
        if iss_ok is not None and prev_iss_ok is not None:
            delta = f"{iss_ok - prev_iss_ok:+5.1f}"
        elif iss_ok is not None:
            delta = "    ·"
        else:
            delta = "    -"
        if iss_ok is not None:
            prev_iss_ok = iss_ok
        open_mark = " *" if key + timedelta(hours=HOURS) > now else ""
        print(
            f"{key:%Y-%m-%d %H:%M} {TZ_NAME[:3]:<3}{open_mark:<2} "
            f"{cell.n:5} {cell.declined:5} {cell.issued:5} {cell.success:5} "
            f"{cell.progress:5} {cell.failed:5} {cell.paid:5}  "
            f"{cell.pct(cell.success, cell.issued)} {delta}  "
            f"{cell.pct(cell.success, cell.n)}  "
            f"{cell.pct(cell.paid, cell.issued)}  "
            f"{cell.fiat_ok:>10,.0f}"
        )

    print("-" * 108)
    print(
        f"{'TOTAL':<22} {total.n:5} {total.declined:5} {total.issued:5} {total.success:5} "
        f"{total.progress:5} {total.failed:5} {total.paid:5}  "
        f"{total.pct(total.success, total.issued)}       "
        f"{total.pct(total.success, total.n)}  "
        f"{total.pct(total.paid, total.issued)}  "
        f"{total.fiat_ok:>10,.0f}"
    )
    print()
    print("iss→ok = Success / issued (рек выдан). iss→paid = клик «Я оплатил» / issued.")
    print("* = интервал ещё открыт, In Progress дозреют в Success/Failed.")
    print("Рост iss→paid / iss→ok после DEPLOY — эффект страницы; провал cr→ok при том же iss→ok — роутинг/PSP.")


run()
