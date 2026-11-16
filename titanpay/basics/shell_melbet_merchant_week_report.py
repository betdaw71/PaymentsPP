"""
Отчёт по конверсии Melbet за прошлую неделю — для мерчанта.

Таблицы:
  1) итог недели
  2) по дням (пн–вс, МСК)
  3) по временным слотам (по умолчанию 3ч)
  4) по категориям сумм
  5) день × сумма
  6) слот × сумма

Метрики:
  create / declined / issued / success / prog
  iss→ok = Success / (create − Declined)   — основная конверсия с выданным реком
  cr→ok  = Success / create
  ok_fiat — сумма Success в валюте заявки (KZT)

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_melbet_merchant_week_report.py

  # прошлая календарная неделя пн–вс МСК (по умолчанию)
  WEEK=prev

  # последние 7 суток от сейчас
  WEEK=last7

  # явные даты (МСК, until не включается)
  SINCE=2026-11-03 UNTIL=2026-11-10

  MERCHANT=melbet PS=C2CKZT HOURS=3
  FORMAT=text|md|tsv
  INCLUDE_PSP=0
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.models import PayIn

MSK = ZoneInfo("Europe/Moscow")
MERCHANT = (os.environ.get("MERCHANT") or "melbet").strip()
PS = (os.environ.get("PS") or "").strip()
WEEK = (os.environ.get("WEEK") or "prev").strip().lower()
SINCE_RAW = (os.environ.get("SINCE") or "").strip()
UNTIL_RAW = (os.environ.get("UNTIL") or "").strip()
HOURS = max(1, min(12, int(os.environ.get("HOURS") or "3")))
FORMAT = (os.environ.get("FORMAT") or "text").strip().lower()
INCLUDE_PSP = (os.environ.get("INCLUDE_PSP") or "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

WEEKDAYS_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")

BUCKETS = (
    (Decimal("0"), Decimal("5000"), "0–5k"),
    (Decimal("5000"), Decimal("10000"), "5–10k"),
    (Decimal("10000"), Decimal("20000"), "10–20k"),
    (Decimal("20000"), Decimal("50000"), "20–50k"),
    (Decimal("50000"), Decimal("100000"), "50–100k"),
    (Decimal("100000"), None, "100k+"),
)


class Cell:
    __slots__ = ("n", "declined", "success", "progress", "failed", "fiat_ok")

    def __init__(self) -> None:
        self.n = 0
        self.declined = 0
        self.success = 0
        self.progress = 0
        self.failed = 0
        self.fiat_ok = Decimal("0")

    def add(self, status: str, amount) -> None:
        self.n += 1
        if status == "Declined":
            self.declined += 1
            return
        if status == "Success":
            self.success += 1
            self.fiat_ok += Decimal(str(amount or 0))
        elif status in {"In Progress", "Pending"}:
            self.progress += 1
        else:
            self.failed += 1

    @property
    def issued(self) -> int:
        return self.n - self.declined

    def iss_ok(self) -> float | None:
        if self.issued <= 0:
            return None
        return 100.0 * self.success / self.issued

    def cr_ok(self) -> float | None:
        if self.n <= 0:
            return None
        return 100.0 * self.success / self.n


def _parse_date(raw: str) -> datetime:
    raw = raw.replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=MSK)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {raw!r}")


def _window() -> tuple[datetime, datetime, str]:
    now = timezone.now().astimezone(MSK)
    if SINCE_RAW and UNTIL_RAW:
        return _parse_date(SINCE_RAW), _parse_date(UNTIL_RAW), "custom"
    if WEEK in {"last7", "7d", "rolling"}:
        end = now
        start = end - timedelta(days=7)
        return start, end, "last7"
    # previous full calendar week Mon 00:00 → next Mon 00:00 MSK
    today = now.date()
    this_monday = today - timedelta(days=today.weekday())
    prev_monday = this_monday - timedelta(days=7)
    start = datetime(prev_monday.year, prev_monday.month, prev_monday.day, tzinfo=MSK)
    end = datetime(this_monday.year, this_monday.month, this_monday.day, tzinfo=MSK)
    return start, end, "prev_week"


def _bucket(amount) -> str:
    amt = Decimal(str(amount or 0))
    for lo, hi, name in BUCKETS:
        if hi is None:
            if amt >= lo:
                return name
        elif lo <= amt < hi:
            return name
    return "other"


def _slot_label(dt: datetime) -> str:
    hour = (dt.hour // HOURS) * HOURS
    end_h = hour + HOURS
    return f"{hour:02d}:00–{end_h:02d}:00"


def _pct(v: float | None) -> str:
    return f"{v:.1f}%" if v is not None else "—"


def _provider(pay_in) -> str:
    order = pay_in.order
    if order is None or not order.payment_details_id:
        return "(no_req)"
    try:
        return order.payment_details.group.trader.user.username or "(no_trader)"
    except Exception:  # noqa: BLE001
        return "(no_trader)"


def _print_table(headers: list[str], rows: list[list[str]], *, title: str) -> None:
    if FORMAT == "md":
        print(f"\n### {title}")
        print("| " + " | ".join(headers) + " |")
        print("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            print("| " + " | ".join(row) + " |")
        return
    if FORMAT == "tsv":
        print(f"\n# {title}")
        print("\t".join(headers))
        for row in rows:
            print("\t".join(row))
        return

    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    print(f"\n=== {title} ===")
    print("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))


def _row(label: str, cell: Cell) -> list[str]:
    return [
        label,
        str(cell.n),
        str(cell.declined),
        str(cell.issued),
        str(cell.success),
        str(cell.progress),
        str(cell.failed),
        _pct(cell.iss_ok()),
        _pct(cell.cr_ok()),
        f"{cell.fiat_ok:,.0f}",
    ]


HEADERS = [
    "срез",
    "create",
    "decl",
    "issued",
    "ok",
    "prog",
    "fail",
    "iss→ok",
    "cr→ok",
    "ok_fiat",
]


def run() -> None:
    start, end, mode = _window()
    qs = PayIn.objects.filter(
        merchant__user__username=MERCHANT,
        created_at__gte=start,
        created_at__lt=end,
    ).select_related(
        "status",
        "payment_system",
        "order__payment_details__group__trader__user",
    )
    if PS:
        qs = qs.filter(payment_system__name__iexact=PS)

    total = Cell()
    by_day: dict[str, Cell] = defaultdict(Cell)
    by_weekday: dict[int, Cell] = defaultdict(Cell)
    by_slot: dict[str, Cell] = defaultdict(Cell)
    by_bucket: dict[str, Cell] = defaultdict(Cell)
    by_day_bucket: dict[str, dict[str, Cell]] = defaultdict(lambda: defaultdict(Cell))
    by_slot_bucket: dict[str, dict[str, Cell]] = defaultdict(lambda: defaultdict(Cell))
    by_ps: dict[str, Cell] = defaultdict(Cell)
    by_psp: dict[str, Cell] = defaultdict(Cell)
    day_order: list[str] = []
    d = start.astimezone(MSK).date()
    last_day = (end - timedelta(microseconds=1)).astimezone(MSK).date()
    while d <= last_day:
        day_order.append(d.isoformat())
        d += timedelta(days=1)

    slot_order: list[str] = []
    for h in range(0, 24, HOURS):
        slot_order.append(f"{h:02d}:00–{h + HOURS:02d}:00")
    bucket_names = [b[2] for b in BUCKETS]

    n = 0
    for pay_in in qs.iterator(chunk_size=500):
        n += 1
        status = pay_in.status.name if pay_in.status else "-"
        amount = pay_in.amount
        created = pay_in.created_at
        if timezone.is_naive(created):
            created = timezone.make_aware(created)
        local = created.astimezone(MSK)
        day = local.strftime("%Y-%m-%d")
        wd = local.weekday()
        slot = _slot_label(local)
        bkt = _bucket(amount)
        ps_name = pay_in.payment_system.name if pay_in.payment_system else "-"

        total.add(status, amount)
        by_day[day].add(status, amount)
        by_weekday[wd].add(status, amount)
        by_slot[slot].add(status, amount)
        by_bucket[bkt].add(status, amount)
        by_day_bucket[day][bkt].add(status, amount)
        by_slot_bucket[slot][bkt].add(status, amount)
        by_ps[ps_name].add(status, amount)
        if INCLUDE_PSP:
            by_psp[_provider(pay_in)].add(status, amount)

    print("=" * 100)
    print("ОТЧЁТ КОНВЕРСИИ MELBET (для мерчанта)")
    print(f"  merchant={MERCHANT}  ps={PS or 'ALL'}  tz=Europe/Moscow  mode={mode}")
    print(f"  период: {start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M}  (until не включён)")
    print(f"  payins={n}  слот={HOURS}ч  format={FORMAT}")
    print("=" * 100)
    print("iss→ok = Success / issued (рек выдан). cr→ok = Success / все create.")
    print("prog — ещё In Progress (на закрытой неделе обычно ~0).")

    _print_table(HEADERS, [_row("НЕДЕЛЯ", total)], title="1. Итог периода")

    day_rows = []
    for day in day_order:
        cell = by_day.get(day) or Cell()
        try:
            wd = datetime.strptime(day, "%Y-%m-%d").weekday()
            label = f"{day} ({WEEKDAYS_RU[wd]})"
        except ValueError:
            label = day
        day_rows.append(_row(label, cell))
    day_rows.append(_row("ИТОГО", total))
    _print_table(HEADERS, day_rows, title="2. По дням недели (МСК)")

    wd_rows = []
    for wd in range(7):
        cell = by_weekday.get(wd) or Cell()
        if cell.n == 0 and mode == "last7":
            # still show for completeness on rolling windows that miss a weekday
            pass
        wd_rows.append(_row(WEEKDAYS_RU[wd], cell))
    _print_table(HEADERS, wd_rows, title="3. Агрегат по дням недели (пн–вс)")

    slot_rows = [_row(slot, by_slot.get(slot) or Cell()) for slot in slot_order]
    _print_table(HEADERS, slot_rows, title=f"4. По временным слотам ({HOURS}ч, МСК)")

    bucket_rows = []
    for name in bucket_names:
        cell = by_bucket.get(name) or Cell()
        if cell.n:
            bucket_rows.append(_row(name, cell))
    _print_table(HEADERS, bucket_rows, title="5. По категориям сумм")

    # day × amount: iss→ok matrix
    matrix_headers = ["день"] + bucket_names + ["all iss→ok"]
    matrix_rows = []
    for day in day_order:
        try:
            wd = datetime.strptime(day, "%Y-%m-%d").weekday()
            label = f"{day} ({WEEKDAYS_RU[wd]})"
        except ValueError:
            label = day
        row = [label]
        for name in bucket_names:
            cell = by_day_bucket[day].get(name) or Cell()
            row.append(_pct(cell.iss_ok()) if cell.issued else "—")
        row.append(_pct((by_day.get(day) or Cell()).iss_ok()))
        matrix_rows.append(row)
    _print_table(matrix_headers, matrix_rows, title="6. День × сумма — iss→ok %")

    vol_headers = ["день"] + [f"{b} ok/iss" for b in bucket_names]
    vol_rows = []
    for day in day_order:
        try:
            wd = datetime.strptime(day, "%Y-%m-%d").weekday()
            label = f"{day} ({WEEKDAYS_RU[wd]})"
        except ValueError:
            label = day
        row = [label]
        for name in bucket_names:
            cell = by_day_bucket[day].get(name) or Cell()
            row.append(f"{cell.success}/{cell.issued}" if cell.n else "—")
        vol_rows.append(row)
    _print_table(vol_headers, vol_rows, title="7. День × сумма — ok/issued")

    slot_matrix_headers = ["слот"] + bucket_names + ["all iss→ok"]
    slot_matrix_rows = []
    for slot in slot_order:
        row = [slot]
        for name in bucket_names:
            cell = by_slot_bucket[slot].get(name) or Cell()
            row.append(_pct(cell.iss_ok()) if cell.issued else "—")
        row.append(_pct((by_slot.get(slot) or Cell()).iss_ok()))
        slot_matrix_rows.append(row)
    _print_table(slot_matrix_headers, slot_matrix_rows, title="8. Слот × сумма — iss→ok %")

    if by_ps:
        ps_rows = [_row(name, cell) for name, cell in sorted(by_ps.items(), key=lambda x: -x[1].n)]
        _print_table(HEADERS, ps_rows, title="9. По payment_system")

    if INCLUDE_PSP and by_psp:
        psp_rows = [
            _row(name, cell)
            for name, cell in sorted(by_psp.items(), key=lambda x: (-x[1].issued, -x[1].n))
        ]
        _print_table(HEADERS, psp_rows, title="10. По провайдерам (внутреннее, INCLUDE_PSP=1)")

    print("\n" + "=" * 100)
    print("Кратко для мерчанта:")
    print(
        f"  За период create={total.n}, issued={total.issued}, success={total.success}, "
        f"iss→ok={_pct(total.iss_ok())}, объём success={total.fiat_ok:,.0f}"
    )
    best_day = max(day_order, key=lambda d: (by_day.get(d) or Cell()).iss_ok() or -1) if day_order else None
    worst_day = min(day_order, key=lambda d: (by_day.get(d) or Cell()).iss_ok() if (by_day.get(d) or Cell()).issued else 999) if day_order else None
    if best_day and (by_day.get(best_day) or Cell()).issued:
        print(f"  Лучший день по iss→ok: {best_day} ({_pct((by_day[best_day]).iss_ok())})")
    if worst_day and (by_day.get(worst_day) or Cell()).issued:
        print(f"  Слабый день по iss→ok: {worst_day} ({_pct((by_day[worst_day]).iss_ok())})")
    best_slot = max(slot_order, key=lambda s: (by_slot.get(s) or Cell()).iss_ok() or -1)
    if (by_slot.get(best_slot) or Cell()).issued:
        print(f"  Лучший слот: {best_slot} ({_pct(by_slot[best_slot].iss_ok())})")
    print("=" * 100)


run()
