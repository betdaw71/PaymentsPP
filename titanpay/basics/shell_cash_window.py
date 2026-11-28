"""Окно кассы: NET-маржа + оценка Δ A−L с SINCE до сейчас (Europe/Moscow).

По умолчанию сегодня с 14:00 MSK:

  docker compose exec -T app \\
    python manage.py shell < titanpay/basics/shell_cash_window.py

Явное окно:
  docker compose exec -T -e SINCE='2026-11-18 14:00' app \\
    python manage.py shell < titanpay/basics/shell_cash_window.py

  FROM_HOUR=14          # если SINCE пуст — сегодня HH:00 MSK
  UNTIL='2026-11-18 19:30'  # иначе now
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from basics.cash_register import (
    MSK,
    _period_pnl,
    c2ckzt_usdt_rate,
    deposit_from_psp_names,
    format_telegram,
    kzt_to_usd,
    liability_merchant_names,
    money,
    owed_to_trader_names,
    prepaid_to_psp_names,
    rolling_merchant_names,
    snapshot,
)
from basics.models import TeamLead, Trader
from merchant.kzt_settlement import MELBET_USERNAME
from merchant.models import Agent, Merchant
from trade.models import Transaction

ZERO = Decimal("0.00")
FROM_HOUR = int((os.environ.get("FROM_HOUR") or "14").strip() or "14")
SINCE_RAW = (os.environ.get("SINCE") or "").strip()
UNTIL_RAW = (os.environ.get("UNTIL") or "").strip()


def parse_msk(raw: str) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt, n in (
        ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y-%m-%d %H:%M", 16),
        ("%Y-%m-%d", 10),
    ):
        try:
            return datetime.strptime(raw[:n], fmt).replace(tzinfo=MSK)
        except ValueError:
            continue
    return None


def net_flow(balance_ids, since, until) -> Decimal:
    ids = [i for i in balance_ids if i]
    if not ids:
        return ZERO
    qs = Transaction.objects.filter(
        creation_date__gte=since, creation_date__lt=until
    )
    inn = qs.filter(to_balance_id__in=ids).aggregate(s=Sum("value"))["s"] or 0
    out = qs.filter(from_balance_id__in=ids).aggregate(s=Sum("value"))["s"] or 0
    return money(Decimal(str(inn)) - Decimal(str(out)))


def top_comments(balance_ids, since, until, limit=6):
    ids = [i for i in balance_ids if i]
    if not ids:
        return []
    by = defaultdict(lambda: ZERO)
    for tx in (
        Transaction.objects.filter(creation_date__gte=since, creation_date__lt=until)
        .filter(Q(from_balance_id__in=ids) | Q(to_balance_id__in=ids))
        .only("value", "comment", "from_balance_id", "to_balance_id")
    ):
        v = money(tx.value)
        c = (tx.comment or "-")[:70]
        if tx.to_balance_id in ids:
            by[c] += v
        if tx.from_balance_id in ids:
            by[c] -= v
    return sorted(by.items(), key=lambda kv: abs(kv[1]), reverse=True)[:limit]


now = timezone.now().astimezone(MSK)
until = parse_msk(UNTIL_RAW) or now
if SINCE_RAW:
    since = parse_msk(SINCE_RAW)
    if since is None:
        print(f"FAIL: bad SINCE={SINCE_RAW!r}")
        raise SystemExit(1)
else:
    since = now.replace(hour=FROM_HOUR, minute=0, second=0, microsecond=0)
    if since > until:
        # если сейчас раньше FROM_HOUR — окно со вчерашнего FROM_HOUR
        from datetime import timedelta

        since = since - timedelta(days=1)

print("=" * 72)
print(f"CASH WINDOW  {since.isoformat()}  →  {until.isoformat()}  (Europe/Moscow)")
print("=" * 72)

snap = snapshot(now=until)
print("\n--- касса СЕЙЧАС ---")
print(format_telegram(snap))

pnl = _period_pnl(since, until)
print("\n--- NET маржа за окно (учётная, по completed orders) ---")
print(f"  orders in/out:  {pnl['orders_in']} / {pnl['orders_out']}")
print(f"  turnover in:    {pnl['turnover_in']} USDT")
print(f"  turnover out:   {pnl['turnover_out']} USDT")
print(f"  payin MDR:      {pnl['payin_mdr']}")
print(f"  payin FX:       {pnl['payin_fx']}")
print(f"  payout MDR:     {pnl['payout_mdr']}")
print(f"  trader fee:     {pnl['trader_fee']}")
print(f"  agent fee:      {pnl['agent_fee']}")
print(f"  expenses:       {pnl['expenses']} (n={pnl['expense_count']})")
print(f"  ★ NET:          {pnl['net']} USDT")
print(
    "  формула: payin_mdr + payin_fx + payout_mdr − trader − agent − expenses − Melbet курс залива"
)
print(f"  Melbet курс залива: {pnl.get('melbet_rate_gap', '0.00')}")

rate = c2ckzt_usdt_rate()
rows: list[tuple] = []

print("\n--- оценка Δ A−L по леджеру за то же окно ---")
print(f"  C2CKZT rate={rate} (Melbet KZT→USD)")

melbet = (
    Merchant.objects.filter(user__username__iexact=MELBET_USERNAME)
    .select_related("balance_kzt", "frozen_balance_kzt", "balance", "frozen_balance")
    .first()
)
if melbet:
    ids = [melbet.balance_kzt_id, melbet.frozen_balance_kzt_id]
    kzt_flow = net_flow(ids, since, until)
    recv_delta = money(-kzt_to_usd(kzt_flow, rate=rate))
    rows.append(("melbet_recv", "asset", recv_delta, f"kzt_flow={kzt_flow}"))
    print(f"  melbet_recv: kzt_flow={kzt_flow} → Δasset≈{recv_delta}")

for tr in Trader.objects.filter(user__username__in=owed_to_trader_names()).select_related(
    "user", "balance_usdt", "frozen_balance_usdt"
):
    ids = [tr.balance_usdt_id, tr.frozen_balance_usdt_id]
    flow = net_flow(ids, since, until)
    rows.append((f"trader:{tr.user.username}", "liab", money(-flow), f"lk_flow={flow}"))
    print(f"  trader {tr.user.username}: lk_flow={flow} → ΔA−L={money(-flow)}")
    for c, v in top_comments(ids, since, until, 4):
        print(f"      {v:+}  {c}")

for tr in Trader.objects.filter(user__username__in=prepaid_to_psp_names()).select_related(
    "user", "balance_usdt", "frozen_balance_usdt"
):
    ids = [tr.balance_usdt_id, tr.frozen_balance_usdt_id]
    flow = net_flow(ids, since, until)
    av = money(tr.balance_usdt.amount if tr.balance_usdt_id else 0)
    fr = money(tr.frozen_balance_usdt.amount if tr.frozen_balance_usdt_id else 0)
    if av + fr <= 0:
        d_held = money(-flow)
    else:
        d_held = flow
    rows.append((f"psp:{tr.user.username}", "asset", d_held, f"flow={flow}"))
    print(f"  psp {tr.user.username}: flow={flow} → Δasset≈{d_held}")

for tr in Trader.objects.filter(user__username__in=deposit_from_psp_names()).select_related(
    "user", "balance_usdt"
):
    ids = [tr.balance_usdt_id]
    flow = net_flow(ids, since, until)
    if flow == 0:
        continue
    rows.append((f"deposit_psp:{tr.user.username}", "liab", money(-flow), f"flow={flow}"))
    print(f"  deposit_psp {tr.user.username}: flow={flow} → ΔA−L={money(-flow)}")

for m in Merchant.objects.filter(user__username__in=liability_merchant_names()).select_related(
    "user", "balance", "frozen_balance"
):
    ids = [m.balance_id, m.frozen_balance_id]
    flow = net_flow(ids, since, until)
    if flow == 0:
        continue
    rows.append((f"merchant:{m.user.username}", "liab", money(-flow), f"flow={flow}"))
    print(f"  merchant {m.user.username}: flow={flow} → ΔA−L={money(-flow)}")

for m in Merchant.objects.filter(user__username__in=rolling_merchant_names()).select_related(
    "user", "balance", "frozen_balance"
):
    ids = [m.balance_id, m.frozen_balance_id]
    flow = net_flow(ids, since, until)
    if flow == 0:
        continue
    rows.append((f"mostbet:{m.user.username}", "mixed", money(-flow), f"flow={flow}"))
    print(f"  mostbet {m.user.username}: flow={flow} → ΔA−L≈{money(-flow)}")

for ag in Agent.objects.select_related("user", "balance", "frozen_balance"):
    ids = [ag.balance_id, ag.frozen_balance_id]
    flow = net_flow(ids, since, until)
    if flow == 0:
        continue
    rows.append((f"agent:{ag.user.username}", "liab", money(-flow), f"flow={flow}"))
    print(f"  agent {ag.user.username}: flow={flow} → ΔA−L={money(-flow)}")

for tl in TeamLead.objects.select_related("user", "balance", "frozen_balance"):
    ids = [tl.balance_id, tl.frozen_balance_id]
    flow = net_flow(ids, since, until)
    if flow == 0:
        continue
    rows.append((f"tl:{tl.user.username}", "liab", money(-flow), f"flow={flow}"))
    print(f"  tl {tl.user.username}: flow={flow} → ΔA−L={money(-flow)}")

try:
    from trade.models import CryptoDepositCredit

    credits = money(
        CryptoDepositCredit.objects.filter(
            credited=True, created_at__gte=since, created_at__lt=until
        ).aggregate(s=Sum("amount"))["s"]
        or 0
    )
except Exception:
    credits = ZERO
print(f"  CryptoDepositCredit credited: +{credits} USDT (on-chain, не в LK-леджере)")

print("\n--- сводка ---")
ledger_al = money(sum((r[2] for r in rows), ZERO))
net = money(pnl["net"])
print(f"  касса сейчас (A−L):           {snap['cash']} USDT")
print(f"  учётная маржа агрегатор:      {snap['memo'].get('platform_aggregator', '0.00')}")
print(f"  ★ NET за окно:                {pnl['net']} USDT")
print(f"  ★ SUM ledger ΔA−L (без Tron): {ledger_al} USDT")
print(f"  GAP (ledgerΔ − NET):          {money(ledger_al - net)} USDT")
print(
    "  note: Δ реального TronLink-кошелька в ledger нет — если был top-up/вывод, "
    "касса сдвинется ещё на on-chain Δ."
)
print("DONE")
