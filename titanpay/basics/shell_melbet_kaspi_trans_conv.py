"""
Аналитика Melbet «Kaspi P2P Trans KZT» — ответ на отключение трафика
из‑за низкой конверсии.

1) Разбор списка merchant_order_id от Melbet (детали + сводка когорты)
2) Контекст метода за DAYS (по умолчанию 7 суток) — create / issued / success
3) Срезы: статус, трейдер, банк, суммы, час МСК
4) Черновик ответа мерчанту

  # список из письма Melbet (по умолчанию уже зашит)
  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_melbet_kaspi_trans_conv.py

  # свои id + окно
  MOIDS='24750525419,24750506617' DAYS=7 \\
    docker compose exec -T -e MOIDS -e DAYS app \\
    python manage.py shell < titanpay/basics/shell_melbet_kaspi_trans_conv.py

  # только когорты id, без окна метода
  CONTEXT=0 ...

  MERCHANT=melbet
  PS=C2CKZT                 # внутренний PS (можно C2C,C2CKZT)
  METHOD_LIKE=kaspi         # MelbetTransactionSession.melbet_method icontains
  DAYS=7
  FORMAT=text|md
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from payments.integrations.melbet.models import MelbetTransactionSession
from payments.models import PayIn
from payments.psp_payin import is_psp_trader, requisite_for_payin
from trade.models import InOrder

MSK = ZoneInfo("Europe/Moscow")

DEFAULT_MOIDS = (
    "24750525419",
    "24750506617",
    "24750448393",
    "24750326809",
    "24750297973",
    "24750201293",
    "24750126935",
    "24750118533",
    "24749928877",
    "24749876839",
    "24749837149",
)

MERCHANT = (os.environ.get("MERCHANT") or "melbet").strip() or "melbet"
PS_RAW = (os.environ.get("PS") or "C2CKZT").strip() or "C2CKZT"
PS_NAMES = [p.strip().upper() for p in PS_RAW.split(",") if p.strip()]
METHOD_LIKE = (os.environ.get("METHOD_LIKE") or "kaspi").strip().lower()
DAYS = max(1, min(60, int(os.environ.get("DAYS") or "7")))
CONTEXT = (os.environ.get("CONTEXT") or "1").strip().lower() not in {"0", "false", "no", "off"}
FORMAT = (os.environ.get("FORMAT") or "text").strip().lower()
SAMPLE = max(5, min(50, int(os.environ.get("SAMPLE") or "15")))


def _moids() -> list[str]:
    raw = (os.environ.get("MOIDS") or "").strip()
    if not raw:
        return list(DEFAULT_MOIDS)
    parts = re.split(r"[\s,;]+", raw)
    return [p.strip() for p in parts if p.strip()]


def _pct(num: int, den: int) -> str:
    if den <= 0:
        return "—"
    return f"{100.0 * num / den:.1f}%"


def _msk(dt) -> str:
    if dt is None:
        return "-"
    try:
        return timezone.localtime(dt, MSK).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:  # noqa: BLE001
        return str(dt)


def _trader_name(order: InOrder | None) -> str:
    if order is None or not order.payment_details_id:
        return "(no_req)"
    try:
        return order.payment_details.group.trader.user.username
    except Exception:  # noqa: BLE001
        return "?"


def _bank(pay_in: PayIn | None, order: InOrder | None) -> str:
    if pay_in is not None:
        try:
            req = requisite_for_payin(pay_in) or {}
            bank = (req.get("bank") or req.get("bankName") or "").strip()
            if bank:
                return bank
        except Exception:  # noqa: BLE001
            pass
    if order and order.payment_details_id:
        try:
            d = order.payment_details
            bank = (getattr(d, "bank_name", None) or "").strip()
            if bank:
                return bank
            gps = d.group.payment_system
            if gps:
                return gps.name
        except Exception:  # noqa: BLE001
            pass
    return "-"


def _melbet_method(pay_in: PayIn | None) -> str:
    if pay_in is None:
        return ""
    s = (
        MelbetTransactionSession.objects.filter(pay_in=pay_in)
        .order_by("-created_at")
        .only("melbet_method")
        .first()
    )
    return (s.melbet_method if s else "") or ""


def _reason(pay_in: PayIn | None, order: InOrder | None) -> str:
    pay_st = pay_in.status.name if pay_in and pay_in.status_id else None
    ord_st = order.status.name if order and order.status_id else None
    has_detail = bool(order and order.payment_details_id)
    comment = (getattr(order, "arbitrage_comment", None) or "").strip() if order else ""
    if ord_st == "Cannot process" or (pay_st == "Declined" and not has_detail):
        return "no_requisite / Cannot process"
    if pay_st == "Success" or ord_st == "Completed":
        return "ok"
    if pay_st == "In Progress" or ord_st in {"New", "Money sent by user", "Arbitrage"}:
        return f"open ({pay_st}/{ord_st})"
    if pay_st in {"Failed", "Expired", "Declined"} or ord_st in {
        "Expired",
        "Cancelled",
        "Cancelled by trader",
        "Cancelled by support",
    }:
        base = f"no_pay / {ord_st or pay_st}"
        return f"{base}; {comment}" if comment else base
    return f"{pay_st}/{ord_st}"


def _find_payin(moid: str) -> PayIn | None:
    qs = (
        PayIn.objects.filter(merchant_order_id=moid)
        .select_related(
            "status",
            "currency",
            "payment_system",
            "merchant__user",
            "order__status",
            "order__payment_details__group__trader__user",
            "order__payment_details__group__payment_system",
        )
        .order_by("-created_at")
    )
    if MERCHANT:
        hit = qs.filter(merchant__user__username__iexact=MERCHANT).first()
        if hit:
            return hit
    return qs.first()


def _bucket(amount) -> str:
    try:
        a = Decimal(str(amount or 0))
    except Exception:  # noqa: BLE001
        return "?"
    edges = (
        (Decimal("0"), Decimal("5000"), "0–5k"),
        (Decimal("5000"), Decimal("10000"), "5–10k"),
        (Decimal("10000"), Decimal("20000"), "10–20k"),
        (Decimal("20000"), Decimal("50000"), "20–50k"),
        (Decimal("50000"), Decimal("100000"), "50–100k"),
        (Decimal("100000"), None, "100k+"),
    )
    for lo, hi, label in edges:
        if a >= lo and (hi is None or a < hi):
            return label
    return "?"


class Cohort:
    __slots__ = ("n", "declined", "success", "progress", "failed", "fiat_ok", "rows")

    def __init__(self) -> None:
        self.n = 0
        self.declined = 0
        self.success = 0
        self.progress = 0
        self.failed = 0
        self.fiat_ok = Decimal("0")
        self.rows: list[dict] = []

    def add(self, row: dict) -> None:
        self.n += 1
        self.rows.append(row)
        st = row["pay_status"]
        if st == "Declined":
            self.declined += 1
        elif st == "Success":
            self.success += 1
            self.fiat_ok += Decimal(str(row.get("amount") or 0))
        elif st in {"In Progress", "Pending", "New"}:
            self.progress += 1
        else:
            self.failed += 1

    @property
    def issued(self) -> int:
        return self.n - self.declined

    def print_summary(self, title: str) -> None:
        print(f"\n=== {title} ===")
        print(f"  create:     {self.n}")
        print(f"  declined:   {self.declined}  (без реквизита)")
        print(f"  issued:     {self.issued}")
        print(f"  success:    {self.success}")
        print(f"  progress:   {self.progress}")
        print(f"  failed*:    {self.failed}  (*Expired/Failed/прочее)")
        print(f"  iss→ok:     {_pct(self.success, self.issued)}")
        print(f"  cr→ok:      {_pct(self.success, self.n)}")
        print(f"  ok_fiat:    {self.fiat_ok}")


def _print_cuts(rows: list[dict], *, key: str, title: str, limit: int = 20) -> None:
    buckets: dict[str, Cohort] = defaultdict(Cohort)
    for r in rows:
        buckets[str(r.get(key) or "-")].add(r)
    print(f"\n--- {title} ---")
    items = sorted(buckets.items(), key=lambda kv: (-kv[1].n, kv[0]))
    for name, c in items[:limit]:
        print(
            f"  {name:28s} n={c.n:4d} iss={c.issued:4d} ok={c.success:4d} "
            f"iss→ok={_pct(c.success, c.issued):>6s} cr→ok={_pct(c.success, c.n):>6s}"
        )
    if len(items) > limit:
        print(f"  … +{len(items) - limit} more")


def analyze_moids(moids: list[str]) -> Cohort:
    print("\n" + "=" * 78)
    print(f"Melbet Kaspi P2P Trans — список от мерчанта  n={len(moids)}")
    print("=" * 78)
    cohort = Cohort()
    missing: list[str] = []
    for moid in moids:
        pay = _find_payin(moid)
        if pay is None:
            missing.append(moid)
            print(f"\n{moid}: NOT FOUND")
            continue
        order = pay.order
        method = _melbet_method(pay)
        trader = _trader_name(order)
        bank = _bank(pay, order)
        psp = False
        if order and order.payment_details_id:
            try:
                psp = is_psp_trader(order.payment_details.group.trader)
            except Exception:  # noqa: BLE001
                psp = False
        row = {
            "moid": moid,
            "pay_id": str(pay.id),
            "pay_status": pay.status.name if pay.status_id else "-",
            "order_status": order.status.name if order and order.status_id else "-",
            "amount": pay.amount,
            "currency": pay.currency.symbol if pay.currency_id else "",
            "ps": pay.payment_system.name if pay.payment_system_id else "-",
            "method": method,
            "trader": trader,
            "bank": bank,
            "psp": psp,
            "created": pay.created_at,
            "reason": _reason(pay, order),
        }
        cohort.add(row)
        print(
            f"\n{moid}  {row['pay_status']}/{row['order_status']}  "
            f"{row['amount']} {row['currency']}  ps={row['ps']}  method={method or '-'}"
        )
        print(f"  pay_in={row['pay_id']}  created={_msk(row['created'])}")
        print(f"  trader={trader}{' [psp]' if psp else ''}  bank={bank}")
        print(f"  reason={row['reason']}")

    if missing:
        print(f"\n! missing moids: {', '.join(missing)}")
    cohort.print_summary("СВОДКА по списку Melbet")
    if cohort.rows:
        _print_cuts(cohort.rows, key="pay_status", title="по статусу PayIn")
        _print_cuts(cohort.rows, key="trader", title="по трейдеру")
        _print_cuts(cohort.rows, key="bank", title="по банку реквизита")
        _print_cuts(cohort.rows, key="reason", title="по причине")
        statuses = Counter(r["pay_status"] for r in cohort.rows)
        print("\n--- статусы (count) ---")
        for k, v in statuses.most_common():
            print(f"  {k}: {v}")
    return cohort


def _context_qs(since):
    """PayIn Melbet на PS; по умолчанию только melbet_method ~ kaspi.

    INCLUDE_NO_METHOD=1 — добавить PayIn на этом PS без Melbet-сессии
    (может смешать Halyk/Kaspi, если method не писался).
    """
    include_no_method = (os.environ.get("INCLUDE_NO_METHOD") or "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    base = PayIn.objects.filter(
        created_at__gte=since,
        merchant__user__username__iexact=MERCHANT,
        payment_system__name__in=PS_NAMES,
    )
    related = (
        "status",
        "currency",
        "payment_system",
        "order__status",
        "order__payment_details__group__trader__user",
        "order__payment_details__group__payment_system",
    )
    if not METHOD_LIKE:
        return base.select_related(*related)

    kaspi_ids = MelbetTransactionSession.objects.filter(
        pay_in_id__in=base.values("id"),
        melbet_method__icontains=METHOD_LIKE,
    ).values_list("pay_in_id", flat=True)
    q = Q(id__in=kaspi_ids)
    if include_no_method:
        with_any_session = MelbetTransactionSession.objects.filter(
            pay_in_id__in=base.values("id")
        ).values_list("pay_in_id", flat=True)
        q = q | Q(id__in=base.exclude(id__in=with_any_session).values("id"))
    return PayIn.objects.filter(q).select_related(*related)


def analyze_context() -> Cohort:
    since = timezone.now() - timedelta(days=DAYS)
    print("\n" + "=" * 78)
    print(
        f"Контекст метода  merchant={MERCHANT} ps={PS_NAMES} "
        f"method~{METHOD_LIKE!r}  days={DAYS}  since={_msk(since)}"
    )
    print("=" * 78)
    qs = _context_qs(since).order_by("created_at")
    cohort = Cohort()
    for pay in qs.iterator(chunk_size=200):
        order = pay.order
        method = _melbet_method(pay)
        # Если METHOD_LIKE задан и у сессии другой method — пропускаем явный non-kaspi
        if METHOD_LIKE and method and METHOD_LIKE not in method.lower():
            continue
        trader = _trader_name(order)
        bank = _bank(pay, order)
        psp = False
        if order and order.payment_details_id:
            try:
                psp = is_psp_trader(order.payment_details.group.trader)
            except Exception:  # noqa: BLE001
                psp = False
        created_local = timezone.localtime(pay.created_at, MSK) if pay.created_at else None
        row = {
            "moid": pay.merchant_order_id or "",
            "pay_id": str(pay.id),
            "pay_status": pay.status.name if pay.status_id else "-",
            "order_status": order.status.name if order and order.status_id else "-",
            "amount": pay.amount,
            "currency": pay.currency.symbol if pay.currency_id else "",
            "ps": pay.payment_system.name if pay.payment_system_id else "-",
            "method": method,
            "trader": trader,
            "bank": bank,
            "psp": "psp" if psp else "local",
            "bucket": _bucket(pay.amount),
            "hour": f"{created_local.hour:02d}h" if created_local else "-",
            "day": created_local.strftime("%Y-%m-%d") if created_local else "-",
            "created": pay.created_at,
            "reason": _reason(pay, order),
        }
        cohort.add(row)

    cohort.print_summary(f"Контекст {DAYS}d / {PS_NAMES} / method~{METHOD_LIKE!r}")
    if not cohort.rows:
        print("  (пусто — проверьте PS / METHOD_LIKE / MERCHANT)")
        return cohort

    _print_cuts(cohort.rows, key="day", title="по дням МСК")
    _print_cuts(cohort.rows, key="hour", title="по часу МСК")
    _print_cuts(cohort.rows, key="bucket", title="по сумме")
    _print_cuts(cohort.rows, key="trader", title="по трейдеру")
    _print_cuts(cohort.rows, key="psp", title="psp vs local")
    _print_cuts(cohort.rows, key="bank", title="по банку")
    _print_cuts(cohort.rows, key="pay_status", title="по статусу PayIn")
    _print_cuts(cohort.rows, key="reason", title="по причине (топ)")

    # failed sample for merchant reply
    fails = [r for r in cohort.rows if r["pay_status"] not in {"Success", "In Progress", "Pending", "New"}]
    fails = sorted(fails, key=lambda r: r["created"] or timezone.now(), reverse=True)[:SAMPLE]
    if fails:
        print(f"\n--- sample не-Success (до {SAMPLE}) ---")
        for r in fails:
            print(
                f"  {r['moid'] or r['pay_id']}  {r['pay_status']}/{r['order_status']}  "
                f"{r['amount']}  {r['trader']}  {r['bank']}  {r['reason']}"
            )
    return cohort


def draft_reply(list_c: Cohort, ctx: Cohort | None) -> None:
    print("\n" + "=" * 78)
    print("ЧЕРНОВИК ОТВЕТА MELBET")
    print("=" * 78)
    lines = []
    lines.append(
        "Добрый день. По методу Kaspi P2P Trans KZT разобрали указанные order_id "
        f"({list_c.n} шт.):"
    )
    lines.append(
        f"— Success {list_c.success}, без реквизита (Declined) {list_c.declined}, "
        f"прочие {list_c.failed + list_c.progress}; "
        f"конверсия issued→Success {_pct(list_c.success, list_c.issued)}, "
        f"create→Success {_pct(list_c.success, list_c.n)}."
    )
    if ctx and ctx.n:
        lines.append(
            f"За последние {DAYS} суток по тому же контуру (PS {','.join(PS_NAMES)}"
            + (f", method~{METHOD_LIKE}" if METHOD_LIKE else "")
            + f"): create {ctx.n}, issued {ctx.issued}, Success {ctx.success}, "
            f"iss→ok {_pct(ctx.success, ctx.issued)}, cr→ok {_pct(ctx.success, ctx.n)}, "
            f"успешный объём {ctx.fiat_ok} KZT."
        )
        # top fail reasons
        reasons = Counter(r["reason"] for r in ctx.rows if r["pay_status"] != "Success")
        top = reasons.most_common(3)
        if top:
            pretty = "; ".join(f"{k}={v}" for k, v in top)
            lines.append(f"Основные причины незакрытия: {pretty}.")
    lines.append(
        "Готовы восстановить трафик после стабилизации выдачи/оплаты; "
        "просим вернуть метод и прислать контрольную выборку после включения."
    )
    print("\n".join(lines))
    if FORMAT == "md":
        print("\n```")
        print("\n".join(lines))
        print("```")


def main() -> None:
    print(
        f"Melbet Kaspi Trans conv  merchant={MERCHANT} ps={PS_NAMES} "
        f"method~{METHOD_LIKE!r} days={DAYS} context={int(CONTEXT)}"
    )
    list_c = analyze_moids(_moids())
    ctx = analyze_context() if CONTEXT else None
    draft_reply(list_c, ctx)
    print("\nDONE")


main()
