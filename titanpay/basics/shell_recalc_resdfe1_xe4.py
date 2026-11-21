"""Пересчёт KZT pay-in команды resdfe1 на курс xe+4 (как у resdfe).

Проблема: в PSP_XE_MARKUP_BY_TRADER не было ключа resdfe1 → fallback = markup
мерчанта (обычно xe+5) → psp_usd ≈ merchant_usd, FX≈0, trader_fee чуть ниже.

Формула (как dual_fx.quote_dual_fx, без live XE — от курсов на ордере):
  merchant_rate  = order.merchant_rate или amount/usd
  merchant_markup = xe markup мерчанта
  psp_rate       = merchant_rate * TARGET_XE / merchant_markup
  new_psp_usd    = amount / psp_rate
  new_trader_fee = mdr_in% × new_psp_usd

Dry-run (по умолчанию) — только суммы расхождения:
  docker compose exec -T -e TRADER=resdfe1 app \\
    python manage.py shell < titanpay/basics/shell_recalc_resdfe1_xe4.py

Применить (после просмотра dry-run + .env \"resdfe1\":\"1.04\"):
  docker compose exec -T -e TRADER=resdfe1 -e APPLY=1 app \\
    python manage.py shell < titanpay/basics/shell_recalc_resdfe1_xe4.py

Опционально:
  TARGET_XE=1.04
  SINCE=2026-11-01          # Europe/Moscow day
  UNTIL=2026-11-19
  MERCHANT=melbet
  LIMIT=30                  # сколько строк diff печатать
  OPEN_TOO=1                # также New / Money sent (только поля, без ledger)
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction as db_transaction
from django.db.models import Q

from basics.models import Trader, TraderTeamRates
from payments.dual_fx import merchant_fx_markup
from trade.models import Balance, InOrder, Transaction, TransactionType

MSK = ZoneInfo("Europe/Moscow")
Q2 = Decimal("0.01")
Q3 = Decimal("0.001")
ZERO = Decimal("0.00")

TRADER = (os.environ.get("TRADER") or "resdfe1").strip() or "resdfe1"
APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
TARGET_XE = Decimal((os.environ.get("TARGET_XE") or "1.04").strip() or "1.04")
SINCE_RAW = (os.environ.get("SINCE") or "").strip()
UNTIL_RAW = (os.environ.get("UNTIL") or "").strip()
MERCHANT = (os.environ.get("MERCHANT") or "").strip()
LIMIT = int((os.environ.get("LIMIT") or "30").strip() or "30")
OPEN_TOO = (os.environ.get("OPEN_TOO") or "").strip().lower() in {"1", "true", "yes"}
COMMENT = f"FX markup recalc {TRADER} xe+{(TARGET_XE - 1) * 100:.0f}"


def money(raw) -> Decimal:
    return Decimal(str(raw or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def money_str(raw) -> str:
    return f"{money(raw):,.2f}"


def parse_day(raw: str, *, end: bool = False) -> datetime | None:
    if not raw:
        return None
    day = datetime.strptime(raw[:10], "%Y-%m-%d").replace(tzinfo=MSK)
    if end:
        from datetime import timedelta

        return day + timedelta(days=1)
    return day


def configured_markup(username: str) -> Decimal | None:
    raw = getattr(settings, "PSP_XE_MARKUP_BY_TRADER", None) or ""
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(str(raw)) if str(raw).strip() else {}
        except Exception:
            data = {}
    for key, val in (data or {}).items():
        if str(key).strip().lower() == username.strip().lower():
            try:
                return Decimal(str(val))
            except Exception:
                return None
    return None


def mdr_in_for(order, trader) -> Decimal:
    ps = order.solution.payment_system if order.solution_id else None
    if trader.team_id and ps is not None:
        row = (
            TraderTeamRates.objects.filter(team_id=trader.team_id, payment_system=ps)
            .only("mdr_in")
            .first()
        )
        if row is not None and row.mdr_in is not None:
            return Decimal(str(row.mdr_in))
    if trader.team_id and trader.team.rate_in is not None:
        return Decimal(str(trader.team.rate_in))
    old_psp = money(order.psp_usd_amount) or money(order.usd_amount)
    old_fee = money(order.trader_fee)
    if old_psp > 0 and old_fee > 0:
        return (old_fee * Decimal(100) / old_psp).quantize(Decimal("0.01"))
    return Decimal("4")


def expected_quote(order, trader) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """→ merchant_markup, psp_markup, merchant_rate, psp_rate, psp_usd"""
    amount = money(order.amount)
    usd = money(order.usd_amount)
    ps = order.solution.payment_system if order.solution_id else None
    merchant = order.solution.merchant if order.solution_id else None
    merchant_markup = merchant_fx_markup(ps, merchant=merchant)
    mr = Decimal(str(getattr(order, "merchant_rate", 0) or 0))
    if mr <= 0 and usd > 0 and amount > 0:
        mr = (amount / usd).quantize(Q3, rounding=ROUND_HALF_UP)
    if mr <= 0 or amount <= 0 or merchant_markup <= 0 or TARGET_XE <= 0:
        return merchant_markup, TARGET_XE, mr, mr, usd
    psp_rate = (mr * TARGET_XE / merchant_markup).quantize(Q3, rounding=ROUND_HALF_UP)
    if psp_rate <= 0:
        psp_rate = mr
    psp_usd = money(amount / psp_rate) if psp_rate > 0 else usd
    return merchant_markup, TARGET_XE, mr, psp_rate, psp_usd


def already_applied(order) -> bool:
    return Transaction.objects.filter(
        linked_in_order=order, comment__icontains=f"FX markup recalc {TRADER}"
    ).exists()


def is_kzt(order) -> bool:
    ps = order.solution.payment_system if order.solution_id else None
    if ps is None:
        return False
    cur = (ps.currency.symbol if ps.currency_id else "") or ""
    name = (ps.name or "") or ""
    return cur.upper() == "KZT" or "KZT" in name.upper()


trader = (
    Trader.objects.select_related("user", "team", "balance_usdt")
    .filter(user__username=TRADER)
    .first()
)
if trader is None:
    print(f"FAIL: trader {TRADER!r} not found")
    raise SystemExit(1)

cfg = configured_markup(TRADER)
print("=" * 72)
print(f"RECALC {TRADER} → xe+{(TARGET_XE - 1) * 100:.0f}  APPLY={int(APPLY)}")
print(f"  team={trader.team.name if trader.team_id else None}")
print(f"  PSP_XE_MARKUP_BY_TRADER[{TRADER}] = {cfg!r}")
if cfg != TARGET_XE:
    print(
        f"  ! в settings сейчас не {TARGET_XE}. Для НОВЫХ сделок добавь в .env и restart:\n"
        f'    PSP_XE_MARKUP_BY_TRADER=…,"{TRADER}":"{TARGET_XE}"…'
    )
else:
    print("  FX config ok for new orders")
print(f"  SINCE={SINCE_RAW or '-'}  UNTIL={UNTIL_RAW or '-'}  MERCHANT={MERCHANT or '-'}")
print("=" * 72)

statuses = ["Completed"]
if OPEN_TOO:
    statuses += ["New", "Money sent by user", "Arbitrage"]

qs = (
    InOrder.objects.filter(
        status__name__in=statuses,
        payment_details__group__trader=trader,
    )
    .select_related(
        "status",
        "solution__payment_system__currency",
        "solution__merchant__user",
        "payment_details__group__trader__user",
        "payment_details__group__trader__team",
    )
    .order_by("completion_date", "creation_date", "id")
)
since = parse_day(SINCE_RAW)
until = parse_day(UNTIL_RAW, end=True)
if since is not None:
    qs = qs.filter(
        Q(completion_date__gte=since)
        | Q(completion_date__isnull=True, creation_date__gte=since)
    )
if until is not None:
    qs = qs.filter(
        Q(completion_date__lt=until)
        | Q(completion_date__isnull=True, creation_date__lt=until)
    )
if MERCHANT:
    qs = qs.filter(solution__merchant__user__username=MERCHANT)

tot = {
    "n": 0,
    "skip_ok": 0,
    "skip_non_kzt": 0,
    "skip_done": 0,
    "diff": 0,
    "usd": ZERO,
    "old_psp": ZERO,
    "new_psp": ZERO,
    "d_psp": ZERO,
    "old_fee": ZERO,
    "new_fee": ZERO,
    "d_fee": ZERO,
    "old_fx": ZERO,
    "new_fx": ZERO,
    "d_fx": ZERO,
    "applied": 0,
}
printed = 0
rows_to_apply: list[tuple] = []

for order in qs.iterator(chunk_size=200):
    tot["n"] += 1
    if not is_kzt(order):
        tot["skip_non_kzt"] += 1
        continue
    amount = money(order.amount)
    usd = money(order.usd_amount)
    if amount <= 0 or usd <= 0:
        tot["skip_ok"] += 1
        continue
    if already_applied(order):
        tot["skip_done"] += 1
        continue

    m_markup, p_markup, mr, pr, new_psp = expected_quote(order, trader)
    old_psp_raw = money(order.psp_usd_amount)
    old_psp = old_psp_raw if old_psp_raw > 0 else usd
    old_fee = money(order.trader_fee)
    mdr = mdr_in_for(order, trader)
    new_fee = money(mdr * new_psp / Decimal(100))
    d_psp = money(new_psp - old_psp)
    d_fee = money(new_fee - old_fee)
    old_fx = money(old_psp - usd)
    new_fx = money(new_psp - usd)
    d_fx = money(new_fx - old_fx)

    if abs(d_psp) < Decimal("0.01") and abs(d_fee) < Decimal("0.01"):
        tot["skip_ok"] += 1
        continue

    tot["diff"] += 1
    tot["usd"] += usd
    tot["old_psp"] += old_psp
    tot["new_psp"] += new_psp
    tot["d_psp"] += d_psp
    tot["old_fee"] += old_fee
    tot["new_fee"] += new_fee
    tot["d_fee"] += d_fee
    tot["old_fx"] += old_fx
    tot["new_fx"] += new_fx
    tot["d_fx"] += d_fx

    st = order.status.name if order.status_id else "?"
    if printed < LIMIT:
        printed += 1
        moid = order.merchant_order_id or "-"
        print(
            f"  {st:12} {order.id} moid={moid} amt={money_str(amount)} "
            f"usd={money_str(usd)} psp {money_str(old_psp)}→{money_str(new_psp)} "
            f"(Δ{money_str(d_psp)}) fee {money_str(old_fee)}→{money_str(new_fee)} "
            f"(Δ{money_str(d_fee)}) mdr={mdr}% mr={mr}→{pr} mm={m_markup}"
        )

    rows_to_apply.append((order.id, st, pr, new_psp, new_fee, d_fee))

print("\n" + "=" * 72)
print("ИТОГО (Completed" + (" + open" if OPEN_TOO else "") + ")")
print(f"  scanned={tot['n']}  diffs={tot['diff']}  already_ok={tot['skip_ok']}  "
      f"already_applied={tot['skip_done']}  non_kzt={tot['skip_non_kzt']}")
print(f"  merchant USD:     {money_str(tot['usd'])}")
print(f"  old psp USD:      {money_str(tot['old_psp'])}")
print(f"  new psp USD:      {money_str(tot['new_psp'])}")
print(f"  Δ psp USD:        {money_str(tot['d_psp'])}")
print(f"  old FX:           {money_str(tot['old_fx'])}")
print(f"  new FX:           {money_str(tot['new_fx'])}")
print(f"  Δ FX (касса):     {money_str(tot['d_fx'])}")
print(f"  old trader_fee:   {money_str(tot['old_fee'])}")
print(f"  new trader_fee:   {money_str(tot['new_fee'])}")
print(f"  Δ trader_fee:     {money_str(tot['d_fee'])}  ← доначислить на баланс {TRADER}")
print("=" * 72)

if not APPLY:
    print("DRY-RUN. Чтобы применить: APPLY=1 (после правки .env на \"resdfe1\":\"1.04\").")
    raise SystemExit(0)

if not rows_to_apply:
    print("Nothing to apply.")
    raise SystemExit(0)

aggregator = Balance.objects.get(type=2)
tx_deposit = TransactionType.objects.get(name="Deposit")
tx_charge = TransactionType.objects.get(name="Charge")

for order_id, st, pr, new_psp, new_fee, d_fee in rows_to_apply:
    with db_transaction.atomic():
        order = (
            InOrder.objects.select_for_update()
            .select_related("payment_details__group__trader__balance_usdt")
            .get(pk=order_id)
        )
        if already_applied(order):
            continue
        order.psp_rate = pr
        order.psp_usd_amount = new_psp
        old_fee = money(order.trader_fee)
        order.trader_fee = new_fee
        order.save(update_fields=["psp_rate", "psp_usd_amount", "trader_fee"])

        # Ledger только на Completed: комиссия уже ушла на баланс.
        if st == "Completed" and abs(d_fee) >= Decimal("0.01"):
            t = order.payment_details.group.trader
            if d_fee > 0:
                Transaction.create(
                    _from=aggregator,
                    _to=t.balance_usdt,
                    value=d_fee,
                    _transaction_type=tx_deposit,
                    _linked_in_order=order,
                    _comment=COMMENT,
                )
            else:
                Transaction.create(
                    _from=t.balance_usdt,
                    _to=aggregator,
                    value=-d_fee,
                    _transaction_type=tx_charge,
                    _linked_in_order=order,
                    _comment=COMMENT,
                )
        tot["applied"] += 1

trader.balance_usdt.refresh_from_db()
print(f"APPLIED={tot['applied']}  {TRADER} balance_usdt now={money_str(trader.balance_usdt.amount)}")
print("DONE")
