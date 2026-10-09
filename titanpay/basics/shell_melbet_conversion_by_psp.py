"""
Конверсия Melbet pay-in: общая, по провайдерам (PSP-трейдер) и по корзинам суммы.

Когорта: PayIn.created_at в окне (МСК).
issued = не Declined (рек выдан). Конверсия мерчанта обычно issued→Success.
Сегодняшняя цифра занижена из-за In Progress.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_melbet_conversion_by_psp.py

  docker compose exec -T -e DAYS=7 -e MERCHANT=melbet app python manage.py shell \\
    < titanpay/basics/shell_melbet_conversion_by_psp.py

  PS=C2CKZT  COMPARE=1  SENDER=halyk|kaspi
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.integrations.melbet.mapping import sender_bank_for_melbet_method
from payments.models import PayIn

MSK = ZoneInfo("Europe/Moscow")
MERCHANT = (os.environ.get("MERCHANT") or "melbet").strip()
DAYS = float(os.environ.get("DAYS") or "7")
PS = (os.environ.get("PS") or "").strip()
SENDER = (os.environ.get("SENDER") or "").strip().lower()
COMPARE = (os.environ.get("COMPARE") or "1").strip().lower() in {"1", "true", "yes", "on"}

BUCKETS = (
    (Decimal("0"), Decimal("5000"), "0–5k"),
    (Decimal("5000"), Decimal("10000"), "5–10k"),
    (Decimal("10000"), Decimal("20000"), "10–20k"),
    (Decimal("20000"), Decimal("50000"), "20–50k"),
    (Decimal("50000"), None, "50k+"),
)


def env_now():
    return timezone.now().astimezone(MSK)


def window(days: float, *, end=None):
    end = end or env_now()
    start = end - timedelta(days=days)
    return start, end


def bucket_of(amount) -> str:
    amt = Decimal(str(amount or 0))
    for lo, hi, name in BUCKETS:
        if hi is None:
            if amt >= lo:
                return name
        elif lo <= amt < hi:
            return name
    return "other"


def provider_of(pay_in) -> str:
    order = pay_in.order
    if order is None or not order.payment_details_id:
        return "(no_req)"
    try:
        name = order.payment_details.group.trader.user.username
    except Exception:  # noqa: BLE001
        return "(no_trader)"
    return name or "(no_trader)"


def qs_for(start, end):
    qs = PayIn.objects.filter(
        merchant__user__username=MERCHANT,
        created_at__gte=start,
        created_at__lt=end,
    ).select_related(
        "status",
        "payment_system",
        "order",
        "order__status",
        "order__payment_details__group__trader__user",
        "melbet_session",
    )
    if PS:
        qs = qs.filter(payment_system__name=PS)
    if SENDER:
        qs = qs.filter(melbet_session__isnull=False)
    return qs.order_by("created_at")


class Cell:
    __slots__ = ("n", "success", "declined", "progress", "other", "fiat_ok")

    def __init__(self):
        self.n = 0
        self.success = 0
        self.declined = 0
        self.progress = 0
        self.other = 0
        self.fiat_ok = Decimal("0")

    def add(self, status: str, amount):
        self.n += 1
        if status == "Success":
            self.success += 1
            self.fiat_ok += Decimal(str(amount or 0))
        elif status == "Declined":
            self.declined += 1
        elif status in ("In Progress", "Pending"):
            self.progress += 1
        else:
            self.other += 1

    @property
    def issued(self) -> int:
        return self.n - self.declined

    def conv_issued(self) -> float | None:
        if self.issued <= 0:
            return None
        return 100.0 * self.success / self.issued

    def conv_create(self) -> float | None:
        if self.n <= 0:
            return None
        return 100.0 * self.success / self.n


def pct(v):
    return f"{v:5.1f}%" if v is not None else "    -"


def row_line(label, cell: Cell, width=16):
    return (
        f"{label:<{width}}  n={cell.n:5}  decl={cell.declined:4}  issued={cell.issued:5}  "
        f"ok={cell.success:5}  prog={cell.progress:4}  "
        f"iss→ok={pct(cell.conv_issued())}  cr→ok={pct(cell.conv_create())}  "
        f"ok_fiat={cell.fiat_ok:,.0f}"
    )


def collect(start, end):
    total = Cell()
    by_psp: dict[str, Cell] = defaultdict(Cell)
    by_ps: dict[str, Cell] = defaultdict(Cell)
    by_psp_bucket: dict[str, dict[str, Cell]] = defaultdict(lambda: defaultdict(Cell))
    by_day: dict[str, Cell] = defaultdict(Cell)
    by_bucket: dict[str, Cell] = defaultdict(Cell)
    n = 0
    by_method: dict[str, Cell] = defaultdict(Cell)
    for pay_in in qs_for(start, end).iterator(chunk_size=400):
        session = getattr(pay_in, "melbet_session", None)
        method = (session.melbet_method if session is not None else "") or ""
        if SENDER:
            bank = sender_bank_for_melbet_method(method)
            if bank != SENDER:
                continue
        n += 1
        status = pay_in.status.name if pay_in.status else "-"
        amount = pay_in.amount
        psp = provider_of(pay_in)
        bkt = bucket_of(amount)
        ps_name = pay_in.payment_system.name if pay_in.payment_system else "-"
        created = pay_in.created_at
        if timezone.is_naive(created):
            created = timezone.make_aware(created)
        day = created.astimezone(MSK).strftime("%Y-%m-%d")
        total.add(status, amount)
        by_psp[psp].add(status, amount)
        by_ps[ps_name].add(status, amount)
        by_psp_bucket[psp][bkt].add(status, amount)
        by_day[day].add(status, amount)
        by_bucket[bkt].add(status, amount)
        by_method[method or "(no_method)"].add(status, amount)
    return {
        "n": n,
        "total": total,
        "by_psp": by_psp,
        "by_ps": by_ps,
        "by_psp_bucket": by_psp_bucket,
        "by_day": by_day,
        "by_bucket": by_bucket,
        "by_method": by_method,
    }


def print_report(title, start, end, data):
    print("=" * 108)
    print(title)
    print(f"  {start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%Y-%m-%d %H:%M')} {MSK.key}")
    print(f"  merchant={MERCHANT}  ps={PS or 'ALL'}  sender={SENDER or 'ALL'}  payins={data['n']}")
    print("-" * 108)
    print("ИТОГО")
    print("  " + row_line("all", data["total"], 12))
    if data.get("by_method"):
        print("\nПо melbet method (что просят на странице)")
        for name, cell in sorted(data["by_method"].items(), key=lambda x: -x[1].n):
            print("  " + row_line(name, cell, 28))
    print("\nПо payment_system")
    for name, cell in sorted(data["by_ps"].items(), key=lambda x: -x[1].n):
        print("  " + row_line(name, cell, 12))
    print("\nПо дням")
    for day in sorted(data["by_day"]):
        print("  " + row_line(day, data["by_day"][day], 12))
    print("\nПо сумме (все провайдеры)")
    for _lo, _hi, name in BUCKETS:
        cell = data["by_bucket"].get(name)
        if cell and cell.n:
            print("  " + row_line(name, cell, 12))
    print("\nПо провайдерам (трейдер реквизита)")
    print("  (no_req) = Declined/Cannot process без реквизита")
    rows = sorted(data["by_psp"].items(), key=lambda x: (-x[1].issued, -x[1].n))
    for name, cell in rows:
        print("  " + row_line(name, cell, 16))
    print("\nПровайдер × сумма  (только issued>0 или n>=5)")
    bucket_names = [b[2] for b in BUCKETS]
    for psp, _cell in rows:
        buckets = data["by_psp_bucket"][psp]
        interesting = False
        lines = []
        for bname in bucket_names:
            bcell = buckets.get(bname)
            if not bcell or bcell.n == 0:
                continue
            if bcell.issued == 0 and bcell.n < 5:
                continue
            interesting = True
            lines.append("    " + row_line(bname, bcell, 12))
        if interesting:
            print(f"  [{psp}]")
            for line in lines:
                print(line)
    print()
    print("Как читать: iss→ok = Success / (создано − Declined). cr→ok = Success / все create.")
    print("Если мерчант говорит ~20% — сверь с iss→ok за закрытые дни (без сегодняшнего prog).")


end = env_now()
start, _ = window(DAYS, end=end)
# выровнять начало дня для DAYS целых
if DAYS == int(DAYS):
    start = datetime.combine((end - timedelta(days=int(DAYS) - 1)).date(), time.min, tzinfo=MSK)

print("melbet conversion by PSP  (read-only)\n")
cur = collect(start, end)
print_report(f"ТЕКУЩЕЕ ОКНО  {DAYS:g}d", start, end, cur)

if COMPARE:
    prev_end = start
    prev_start = start - (end - start)
    prev = collect(prev_start, prev_end)
    print_report("ПРЕДЫДУЩЕЕ ОКНО той же длины", prev_start, prev_end, prev)
    a, b = cur["total"], prev["total"]
    print("=" * 108)
    print("ДЕЛЬТА iss→ok  текущее − прошлое")
    print(f"  all: {pct(a.conv_issued())} vs {pct(b.conv_issued())}")
    names = set(cur["by_psp"]) | set(prev["by_psp"])
    for name in sorted(names, key=lambda n: -(cur["by_psp"][n].issued if n in cur["by_psp"] else 0)):
        c1 = cur["by_psp"][name]
        c0 = prev["by_psp"][name]
        print(f"  {name:<16}  now {pct(c1.conv_issued())}  prev {pct(c0.conv_issued())}  issued {c1.issued}/{c0.issued}")
