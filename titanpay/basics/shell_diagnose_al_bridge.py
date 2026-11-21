"""Где деньги: мост A−L по строкам кассы за N дней (из Transaction).

Модель Melbet+команда (верная):
  top-up команды: кошелёк↑ + долг resdfe↑ → A−L 0
  Melbet IN: долг resdfe↓ на ~usd, Melbet prepaid↓ на ~(usd−mdr) → A−L ≈ +(mdr−trader−agent)

Скрипт НЕ врёт про «burn −5500». Считает Δ каждой строки A−L из леджера
и сравнивает сумму с day NET. Остаток = куда реально утекло / не попало в кассу.

  DAYS=5 \\
  docker compose exec -T -e DAYS app \\
    python manage.py shell < titanpay/basics/shell_diagnose_al_bridge.py
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from basics.cash_register import (
    MSK,
    _period_pnl,
    c2ckzt_usdt_rate,
    deposit_from_psp_names,
    kzt_to_usd,
    liability_merchant_names,
    money,
    moscow_bounds,
    owed_to_trader_names,
    prepaid_to_psp_names,
    rolling_merchant_names,
    snapshot,
)
from basics.models import TeamLead, Trader
from merchant.kzt_settlement import MELBET_USERNAME
from merchant.models import Agent, Merchant
from trade.models import Transaction

DAYS = int(os.environ.get("DAYS") or "5")
ZERO = Decimal("0.00")


def section(t: str) -> None:
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)


def net_flow(balance_ids, since) -> Decimal:
    """Δ amount ≈ into − out of этих balance за окно."""
    ids = [i for i in balance_ids if i]
    if not ids:
        return ZERO
    inn = (
        Transaction.objects.filter(to_balance_id__in=ids, creation_date__gte=since).aggregate(
            s=Sum("value")
        )["s"]
        or 0
    )
    out = (
        Transaction.objects.filter(from_balance_id__in=ids, creation_date__gte=since).aggregate(
            s=Sum("value")
        )["s"]
        or 0
    )
    return money(Decimal(str(inn)) - Decimal(str(out)))


def top_comments(balance_ids, since, limit=8):
    from django.db.models import Q

    ids = [i for i in balance_ids if i]
    if not ids:
        return []
    by = defaultdict(lambda: ZERO)
    for tx in Transaction.objects.filter(creation_date__gte=since).filter(
        Q(from_balance_id__in=ids) | Q(to_balance_id__in=ids)
    ).only("value", "comment", "from_balance_id", "to_balance_id"):
        v = money(tx.value)
        c = (tx.comment or "")[:60]
        if tx.to_balance_id in ids:
            by[c] += v
        if tx.from_balance_id in ids:
            by[c] -= v
    return sorted(by.items(), key=lambda kv: abs(kv[1]), reverse=True)[:limit]


def main() -> None:
    now = timezone.now().astimezone(MSK)
    _, day_start, _ = moscow_bounds(now)
    since = day_start - timedelta(days=DAYS - 1)
    rate = c2ckzt_usdt_rate()
    snap = snapshot(now=now)

    section(f"МОСТ A−L за {DAYS}д с {since.astimezone(MSK).date()} (MSK)")
    print(f"Сейчас: A−L={snap['cash']}  assets={snap['assets']['total']}  liab={snap['liabilities']['total']}")
    print(f"day NET={snap['pnl']['day']['net']}  month={snap['pnl']['month']['net']}")
    print(f"C2CKZT rate={rate}  (Melbet KZT→USD)")

    day_nets = []
    for i in range(DAYS):
        d0 = since + timedelta(days=i)
        p = _period_pnl(d0, d0 + timedelta(days=1))
        day_nets.append(money(p["net"]))
        print(f"  {d0.date()} NET={p['net']}")
    sum_net = money(sum(day_nets, ZERO))
    print(f"SUM day NET = {sum_net}  ← столько A−L ДОЛЖЕН был вырасти, если всё бьётся")

    rows = []  # (name, kind asset|liab, delta_al_contrib, detail)

    # --- Melbet receivable (asset when KZT<0) ---
    melbet = (
        Merchant.objects.filter(user__username__iexact=MELBET_USERNAME)
        .select_related("balance_kzt", "frozen_balance_kzt", "balance", "frozen_balance")
        .first()
    )
    melbet_ids = []
    if melbet:
        melbet_ids = [melbet.balance_kzt_id, melbet.frozen_balance_kzt_id]
        kzt_now = money(
            (melbet.balance_kzt.amount if melbet.balance_kzt_id else 0)
            + (melbet.frozen_balance_kzt.amount if melbet.frozen_balance_kzt_id else 0)
        )
        kzt_flow = net_flow(melbet_ids, since)  # + = KZT balance up (less prepaid)
        # receivable USD = -kzt/rate when kzt<0
        # Δ receivable ≈ -Δkzt/rate (if stayed negative)
        recv_delta = money(-kzt_to_usd(kzt_flow, rate=rate))
        rows.append(("melbet_recv", "asset", recv_delta, f"kzt_now={kzt_now} kzt_flow={kzt_flow}"))
        print()
        print(f"Melbet KZT now={kzt_now}  flow={kzt_flow}  → Δ receivable USD≈{recv_delta}")
        print("  (flow>0 = кредиты IN съели prepaid; Δ recv отрицательный)")

    # --- owed traders (resdfe) liability ---
    owed_names = owed_to_trader_names()
    for tr in Trader.objects.filter(user__username__in=owed_names).select_related(
        "user", "balance_usdt", "frozen_balance_usdt", "team"
    ):
        ids = [tr.balance_usdt_id, tr.frozen_balance_usdt_id]
        flow = net_flow(ids, since)  # + = долг им вырос
        # A−L contrib: −Δ liability
        rows.append((f"trader:{tr.user.username}", "liab", money(-flow), f"lk_flow={flow}"))
        print(f"trader {tr.user.username}: LK flow={flow} (долг↑ если +)  → ΔA−L={money(-flow)}")
        for c, v in top_comments(ids, since, 5):
            print(f"    {v:+}  {c}")

    # --- prepaid PSP assets ---
    for tr in Trader.objects.filter(user__username__in=prepaid_to_psp_names()).select_related(
        "user", "balance_usdt", "frozen_balance_usdt"
    ):
        ids = [tr.balance_usdt_id, tr.frozen_balance_usdt_id]
        flow = net_flow(ids, since)
        # held = |avail+frozen|; for prepaid usually negative LK.
        # Approximate Δ held ≈ -flow if LK stays negative (more neg = more held when flow out of LK)
        # If amount goes more negative, flow is negative, held increases: Δheld ≈ -flow for neg balances
        av = money(tr.balance_usdt.amount if tr.balance_usdt_id else 0)
        fr = money(tr.frozen_balance_usdt.amount if tr.frozen_balance_usdt_id else 0)
        held_now = money(abs(av + fr))
        # Heuristic: prepaid asset tracks abs(LK). Δheld ≈ -sign(LK_mid)*flow ≈ -flow when LK<0
        if av + fr <= 0:
            d_held = money(-flow)  # out of LK (flow-) → more neg → held+
        else:
            d_held = flow
        rows.append((f"psp:{tr.user.username}", "asset", d_held, f"held_now={held_now} flow={flow}"))
        print(f"PSP {tr.user.username}: held_now={held_now} flow={flow} → Δasset≈{d_held}")
        for c, v in top_comments(ids, since, 4):
            print(f"    {v:+}  {c}")

    # --- deposit-from-PSP liabilities (payplat/prochub/layerone) ---
    for tr in Trader.objects.filter(user__username__in=deposit_from_psp_names()).select_related(
        "user", "balance_usdt", "frozen_balance_usdt"
    ):
        ids = [tr.balance_usdt_id]
        flow = net_flow(ids, since)
        # owed = available if >0
        rows.append((f"deposit_psp:{tr.user.username}", "liab", money(-flow), f"flow={flow}"))
        print(f"deposit-PSP {tr.user.username}: flow={flow} → ΔA−L={money(-flow)}")

    # --- liability merchants ---
    for m in Merchant.objects.filter(user__username__in=liability_merchant_names()).select_related(
        "user", "balance", "frozen_balance"
    ):
        ids = [m.balance_id, m.frozen_balance_id]
        flow = net_flow(ids, since)
        rows.append((f"merchant:{m.user.username}", "liab", money(-flow), f"flow={flow}"))
        print(f"merchant {m.user.username}: flow={flow} (долг↑ если +) → ΔA−L={money(-flow)}")
        for c, v in top_comments(ids, since, 4):
            print(f"    {v:+}  {c}")

    # --- rolling mostbet ---
    for m in Merchant.objects.filter(user__username__in=rolling_merchant_names()).select_related(
        "user", "balance", "frozen_balance"
    ):
        ids = [m.balance_id, m.frozen_balance_id]
        flow = net_flow(ids, since)
        # net = av+fr-rolling; Δnet≈flow. If net>0 liab, ΔA−L=-flow; if net<0 asset, ΔA−L=+(-flow) wait
        av = money(m.balance.amount if m.balance_id else 0)
        fr = money(m.frozen_balance.amount if m.frozen_balance_id else 0)
        rr = money(m.rolling_reserve)
        net = money(av + fr - rr)
        if net >= 0:
            d_al = money(-flow)  # liability
            kind = "liab"
        else:
            # asset = -net; Δasset ≈ -flow
            d_al = money(-flow)
            kind = "asset"
        rows.append((f"mostbet:{m.user.username}", kind, d_al, f"net_now={net} flow={flow}"))
        print(f"mostbet {m.user.username}: net_now={net} flow={flow} → ΔA−L≈{d_al} ({kind})")

    # --- agents / TL ---
    for ag in Agent.objects.select_related("user", "balance", "frozen_balance"):
        ids = [ag.balance_id, ag.frozen_balance_id]
        flow = net_flow(ids, since)
        if flow == 0:
            continue
        rows.append((f"agent:{ag.user.username}", "liab", money(-flow), f"flow={flow}"))
        print(f"agent {ag.user.username}: flow={flow} → ΔA−L={money(-flow)}")

    for tl in TeamLead.objects.select_related("user", "balance", "frozen_balance"):
        ids = [tl.balance_id, tl.frozen_balance_id]
        flow = net_flow(ids, since)
        if flow == 0:
            continue
        rows.append((f"tl:{tl.user.username}", "liab", money(-flow), f"flow={flow}"))
        print(f"TL {tl.user.username}: flow={flow} → ΔA−L={money(-flow)}")

    # --- crypto topups credited to traders (informational; wallet on-chain ≠ LK) ---
    try:
        from trade.models import CryptoDepositCredit

        credits = money(
            CryptoDepositCredit.objects.filter(
                credited=True, created_at__gte=since
            ).aggregate(s=Sum("amount"))["s"]
            or 0
        )
        print(f"\nCryptoDepositCredit credited window: +{credits} USDT (должно быть на TronLink)")
    except Exception as e:
        print(f"\nCryptoDepositCredit: skip ({e})")
        credits = ZERO

    section("СВОДКА ΔA−L по строкам (ledger, без on-chain кошелька)")
    total_ledger_al = ZERO
    for name, kind, d_al, detail in sorted(rows, key=lambda r: abs(r[2]), reverse=True):
        total_ledger_al += d_al
        print(f"  {d_al:+10}  [{kind:5}] {name:28}  {detail}")
    print(f"\n  SUM ledger ΔA−L (без TronLink) = {total_ledger_al}")
    print(f"  SUM day NET                    = {sum_net}")
    gap = money(total_ledger_al - sum_net)
    print(f"  GAP (ledgerΔ − NET)            = {gap}")
    print("  Если GAP≈0 — маржа бьётся в строках кассы; тетрадь «стоит» из‑за других движений")
    print("  (выводы, top-up, ручные правки). Если GAP<<0 — деньги ушли из A−L строк сверх NET.")
    print("  TronLink Δ не в ledger: смотри ручной баланс кошелька vs CryptoDepositCredit.")

    # Paired Melbet + resdfe check
    section("ПРОВЕРКА: Melbet+resdfe должны дать ≈ Melbet-спред, не −оборот")
    melbet_d = next((r[2] for r in rows if r[0] == "melbet_recv"), ZERO)
    resdfe_d = money(
        sum((r[2] for r in rows if r[0].startswith("trader:")), ZERO)
    )
    paired = money(melbet_d + resdfe_d)
    print(f"  Δ melbet_recv = {melbet_d}")
    print(f"  Δ traders(A−L)= {resdfe_d}  (долг команде: −flow)")
    print(f"  SUM paired    = {paired}  ← ожидаем порядка Melbet pnl (~+157 за 5д), НЕ −5500")
    if paired < money(-500):
        print("  ★ paired сильно отрицательный → Melbet burn НЕ компенсируется снижением долга resdfe")
        print("    (заявки без freeze / не тот trader в OWED_TO_TRADERS / списание не с LK)")
    elif abs(paired) < money(500):
        print("  ★ paired около нуля/маржи → твоя модель верна, Melbet не дыра оборота")

    section("ТОП дыр (куда смотреть дальше)")
    # largest negative A-L contributors
    neg = [r for r in rows if r[2] < 0]
    neg.sort(key=lambda r: r[2])
    for name, kind, d_al, detail in neg[:8]:
        print(f"  {d_al:+10}  {name}  {detail}")
    if not neg:
        print("  нет отрицательных вкладов в ledger — смотри TronLink / ручные выводы")

    print("\nDONE")


main()
