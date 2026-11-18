"""
Реквизиты Melbet Kaspi P2P Trans с просадкой конверсии за последние сутки
относительно базового окна.

Сравнивает iss→ok по каждому PaymentDetails (карта/телефон) и по банку:
  last HOURS (default 24)  vs  предыдущие BASE_DAYS (default 6).

  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_melbet_kaspi_req_drop.py

  MERCHANT=melbet PS=C2CKZT METHOD_LIKE=kaspi
  HOURS=24 BASE_DAYS=6
  MIN_ISSUED_NOW=3 MIN_ISSUED_BASE=5
  DROP_PP=15          # падение iss→ok в процентных пунктах
  MAX_NOW_PCT=40      # и/или текущая конверсия ниже порога
  TOP=40
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.utils import timezone

from payments.integrations.melbet.models import MelbetTransactionSession
from payments.models import PayIn
from payments.psp_payin import requisite_for_payin

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")

MERCHANT = (os.environ.get("MERCHANT") or "melbet").strip() or "melbet"
PS_NAMES = [
    p.strip().upper()
    for p in (os.environ.get("PS") or "C2CKZT").split(",")
    if p.strip()
]
METHOD_LIKE = (os.environ.get("METHOD_LIKE") or "kaspi").strip().lower()
HOURS = max(1, min(72, int(os.environ.get("HOURS") or "24")))
BASE_DAYS = max(1, min(30, int(os.environ.get("BASE_DAYS") or "6")))
MIN_ISSUED_NOW = max(1, int(os.environ.get("MIN_ISSUED_NOW") or "3"))
MIN_ISSUED_BASE = max(1, int(os.environ.get("MIN_ISSUED_BASE") or "5"))
DROP_PP = Decimal(str(os.environ.get("DROP_PP") or "15"))
MAX_NOW_PCT = Decimal(str(os.environ.get("MAX_NOW_PCT") or "40"))
TOP = max(5, min(100, int(os.environ.get("TOP") or "40")))


def pct(ok: int, iss: int) -> Decimal | None:
    if iss <= 0:
        return None
    return (Decimal(ok) * Decimal(100) / Decimal(iss)).quantize(Q2, rounding=ROUND_HALF_UP)


def pct_s(ok: int, iss: int) -> str:
    p = pct(ok, iss)
    return f"{p}%" if p is not None else "—"


class Cell:
    __slots__ = ("c", "d", "ok")

    def __init__(self) -> None:
        self.c = 0
        self.d = 0
        self.ok = 0

    def add(self, status: str) -> None:
        self.c += 1
        if status == "Declined":
            self.d += 1
        elif status == "Success":
            self.ok += 1

    @property
    def iss(self) -> int:
        return self.c - self.d


def _mask_card(card: str | None) -> str:
    d = "".join(ch for ch in str(card or "") if ch.isdigit())
    if len(d) >= 10:
        return f"{d[:6]}…{d[-4:]}"
    if d:
        return d
    return ""


def _mask_phone(phone: str | None) -> str:
    s = str(phone or "").strip()
    if not s:
        return ""
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 6:
        return f"+{digits[:-4]}…{digits[-4:]}" if s.startswith("+") or digits.startswith("996") else f"…{digits[-4:]}"
    return s


def _req_key(pay: PayIn) -> tuple[str, str, str, str]:
    """(detail_id, label, trader, bank)"""
    order = pay.order
    if order is None or not order.payment_details_id:
        return ("(no_req)", "(no_req)", "(no_req)", "-")
    d = order.payment_details
    detail_id = str(d.id)
    trader = "?"
    bank = "-"
    try:
        trader = d.group.trader.user.username
    except Exception:  # noqa: BLE001
        pass
    try:
        req = requisite_for_payin(pay) or {}
        bank = (req.get("bank") or req.get("bankName") or "").strip() or bank
    except Exception:  # noqa: BLE001
        pass
    if bank == "-":
        bank = (getattr(d, "bank_name", None) or "").strip() or bank
    card = _mask_card(getattr(d, "card_number", None))
    phone = _mask_phone(getattr(d, "phone", None))
    owner = (getattr(d.group, "owner", None) or "")[:20]
    if card:
        label = f"card {card}"
    elif phone:
        label = f"phone {phone}"
    else:
        label = f"detail {detail_id[:8]}"
    if owner:
        label = f"{label} / {owner}"
    return detail_id, label, trader, bank or "-"


def _load_pays(since, until):
    base = PayIn.objects.filter(
        created_at__gte=since,
        created_at__lt=until,
        merchant__user__username__iexact=MERCHANT,
        payment_system__name__in=PS_NAMES,
    ).select_related(
        "status",
        "order__payment_details__group__trader__user",
        "order__payment_details__group__payment_system",
    )
    if not METHOD_LIKE:
        return list(base.iterator(chunk_size=500))

    kaspi_ids = list(
        MelbetTransactionSession.objects.filter(
            pay_in_id__in=base.values("id"),
            melbet_method__icontains=METHOD_LIKE,
        ).values_list("pay_in_id", flat=True)
    )
    if not kaspi_ids:
        return []
    return list(
        PayIn.objects.filter(id__in=kaspi_ids)
        .select_related(
            "status",
            "order__payment_details__group__trader__user",
            "order__payment_details__group__payment_system",
        )
        .iterator(chunk_size=500)
    )


def _aggregate(pays: list[PayIn]):
    by_req: dict[str, Cell] = defaultdict(Cell)
    by_bank: dict[str, Cell] = defaultdict(Cell)
    by_trader: dict[str, Cell] = defaultdict(Cell)
    meta: dict[str, tuple[str, str, str]] = {}
    for p in pays:
        st = p.status.name if p.status_id else ""
        detail_id, label, trader, bank = _req_key(p)
        by_req[detail_id].add(st)
        by_bank[bank].add(st)
        by_trader[trader].add(st)
        meta[detail_id] = (label, trader, bank)
    return by_req, by_bank, by_trader, meta


def _print_drops(
    title: str,
    now_map: dict[str, Cell],
    base_map: dict[str, Cell],
    *,
    label_of,
    min_now: int,
    min_base: int,
):
    rows = []
    for key, now in now_map.items():
        if now.iss < min_now:
            continue
        base = base_map.get(key) or Cell()
        now_p = pct(now.ok, now.iss)
        base_p = pct(base.ok, base.iss) if base.iss >= min_base else None
        drop = None
        if now_p is not None and base_p is not None:
            drop = base_p - now_p
        # кандидаты: сильное падение ИЛИ низкая текущая при достаточной базе
        bad = False
        if drop is not None and drop >= DROP_PP:
            bad = True
        if now_p is not None and now_p <= MAX_NOW_PCT and now.iss >= min_now:
            # только если база была заметно лучше или базы мало (новый плохой рек)
            if base_p is None or base_p - now_p >= Decimal("5") or base.iss < min_base:
                bad = True
        if not bad:
            continue
        rows.append(
            (
                drop if drop is not None else Decimal("-1"),
                now_p if now_p is not None else Decimal("0"),
                key,
                label_of(key),
                now,
                base,
                now_p,
                base_p,
                drop,
            )
        )
    rows.sort(key=lambda r: (-(r[0] or 0), r[1], -r[4].iss))
    print(f"\n=== {title}  (drop≥{DROP_PP}pp или now≤{MAX_NOW_PCT}% @ iss≥{min_now}) ===")
    if not rows:
        print("  (нет кандидатов)")
        return rows
    print(
        f"  {'label':42} {'trader/bank':18} "
        f"{'now_iss':>7} {'now_ok':>6} {'now%':>7} "
        f"{'base_iss':>8} {'base_ok':>7} {'base%':>7} {'Δpp':>7}"
    )
    for drop, _np, key, label, now, base, now_p, base_p, dpp in rows[:TOP]:
        extra = ""
        if isinstance(label, tuple):
            text, extra = label[0], label[1]
        else:
            text = label
        delta = f"{dpp:+.1f}" if dpp is not None else "n/a"
        print(
            f"  {text[:42]:42} {extra[:18]:18} "
            f"{now.iss:7d} {now.ok:6d} {pct_s(now.ok, now.iss):>7} "
            f"{base.iss:8d} {base.ok:7d} {pct_s(base.ok, base.iss):>7} {delta:>7}"
        )
    if len(rows) > TOP:
        print(f"  … +{len(rows) - TOP} more")
    return rows


def main() -> None:
    now = timezone.now()
    win_end = now
    win_start = now - timedelta(hours=HOURS)
    base_end = win_start
    base_start = win_start - timedelta(days=BASE_DAYS)

    print(
        f"Melbet Kaspi requisite drop  merchant={MERCHANT} ps={PS_NAMES} "
        f"method~{METHOD_LIKE!r}"
    )
    print(
        f"  NOW:  {_msk(win_start)} → {_msk(win_end)}  ({HOURS}h)\n"
        f"  BASE: {_msk(base_start)} → {_msk(base_end)}  ({BASE_DAYS}d before)"
    )

    pays_now = _load_pays(win_start, win_end)
    pays_base = _load_pays(base_start, base_end)
    print(f"  loaded now={len(pays_now)} base={len(pays_base)}")

    now_req, now_bank, now_trader, meta = _aggregate(pays_now)
    base_req, base_bank, base_trader, meta_b = _aggregate(pays_base)
    meta = {**meta_b, **meta}

    # overall
    def _tot(pays):
        c = Cell()
        for p in pays:
            c.add(p.status.name if p.status_id else "")
        return c

    tn, tb = _tot(pays_now), _tot(pays_base)
    print(
        f"\n=== OVERALL ===\n"
        f"  now:  create={tn.c} iss={tn.iss} ok={tn.ok} iss→ok={pct_s(tn.ok, tn.iss)}\n"
        f"  base: create={tb.c} iss={tb.iss} ok={tb.ok} iss→ok={pct_s(tb.ok, tb.iss)}"
    )
    if tn.iss and tb.iss and pct(tn.ok, tn.iss) is not None and pct(tb.ok, tb.iss) is not None:
        print(f"  Δpp:  {pct(tb.ok, tb.iss) - pct(tn.ok, tn.iss):+.1f}")

    def req_label(detail_id: str):
        label, trader, bank = meta.get(detail_id, (detail_id, "?", "-"))
        return (f"{label}", f"{trader}/{bank}")

    def bank_label(bank: str):
        return (bank, "")

    def trader_label(trader: str):
        return (trader, "")

    drop_reqs = _print_drops(
        "РЕКВИЗИТЫ с просадкой",
        now_req,
        base_req,
        label_of=req_label,
        min_now=MIN_ISSUED_NOW,
        min_base=MIN_ISSUED_BASE,
    )
    _print_drops(
        "БАНКИ с просадкой",
        now_bank,
        base_bank,
        label_of=bank_label,
        min_now=max(MIN_ISSUED_NOW, 5),
        min_base=max(MIN_ISSUED_BASE, 10),
    )
    _print_drops(
        "ТРЕЙДЕРЫ с просадкой",
        now_trader,
        base_trader,
        label_of=trader_label,
        min_now=max(MIN_ISSUED_NOW, 5),
        min_base=max(MIN_ISSUED_BASE, 10),
    )

    # new bad requisites: enough volume now, almost no history, poor now%
    print(f"\n=== НОВЫЕ/РЕДКИЕ реквизиты (base_iss<{MIN_ISSUED_BASE}, now_iss≥{MIN_ISSUED_NOW}, now%≤{MAX_NOW_PCT}) ===")
    fresh = []
    for detail_id, now in now_req.items():
        if now.iss < MIN_ISSUED_NOW:
            continue
        base = base_req.get(detail_id) or Cell()
        if base.iss >= MIN_ISSUED_BASE:
            continue
        now_p = pct(now.ok, now.iss)
        if now_p is None or now_p > MAX_NOW_PCT:
            continue
        label, trader, bank = meta.get(detail_id, (detail_id, "?", "-"))
        fresh.append((now_p, now.iss, label, trader, bank, now, base))
    fresh.sort(key=lambda x: (x[0], -x[1]))
    if not fresh:
        print("  (нет)")
    else:
        for now_p, iss, label, trader, bank, now, base in fresh[:TOP]:
            print(
                f"  {label[:48]:48} {trader}/{bank}  "
                f"now iss={now.iss} ok={now.ok} {pct_s(now.ok, now.iss)}  "
                f"base iss={base.iss} ok={base.ok}"
            )

    # actionable: worst drop requisites one-liners
    print("\n=== ACTION (выключить/ограничить) ===")
    if not drop_reqs and not fresh:
        print("  Явной просадки по отдельным реквизитам нет — смотреть трейдера/банк целиком.")
    for drop, _np, key, label, now, base, now_p, base_p, dpp in (drop_reqs or [])[:15]:
        text = label[0] if isinstance(label, tuple) else label
        extra = label[1] if isinstance(label, tuple) else ""
        delta = f"Δ={dpp:+.1f}pp" if dpp is not None else "Δ=n/a"
        print(
            f"  detail={key[:8]}…  {text}  {extra}  "
            f"now {pct_s(now.ok, now.iss)} ({now.ok}/{now.iss})  "
            f"base {pct_s(base.ok, base.iss)} ({base.ok}/{base.iss})  {delta}"
        )
    print("\nDONE")


def _msk(dt) -> str:
    try:
        return timezone.localtime(dt, MSK).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:  # noqa: BLE001
        return str(dt)


main()
