"""Реальные деньги vs day NET: Melbet prepaid burn + утечка в fees (трейдер/TL/мерч).

Модель пользователя (верно):
  реальные активы = кошельки USDT + балансы на сайтах PSP + Melbet prepaid/долг
  реальные пассивы = долги мерчам + команде (трейдеры/TL) + агентам
  агрегатор type=2 (~300k) — НЕ существует в реальности, в A−L не входит

Теория утечки: «маржа +70$/день не видна в A−L» → либо
  (A) Melbet IN сжигает prepaid ≈ оборот, а day NET считает только спред MDR−trader
  (B) trader_mdr+agent > MDR+FX (переплата команде)
  (C) мерчу кредитуем больше amount−fee
  (D) TL% от оборота «съедает» маржу трейдера (не доп. расход площадки, но видно в расчётах)

  DAYS=5 \\
  docker compose exec -T -e DAYS app \\
    python manage.py shell < titanpay/basics/shell_diagnose_real_money_fee_leak.py
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum
from django.utils import timezone

from basics.cash_register import (
    MSK,
    _period_pnl,
    melbet_fiat_merchant_fee_usd_expr,
    melbet_fiat_trader_fee_usd_expr,
    money,
    moscow_bounds,
    snapshot,
)
from basics.models import TraderTeamRates
from merchant.kzt_settlement import (
    MELBET_USERNAME,
    in_order_credit_kzt,
    uses_melbet_fiat_settlement,
)
from merchant.models import Merchant
from trade.models import InOrder, OutOrder, Transaction

Q2 = Decimal("0.01")
DAYS = int(os.environ.get("DAYS") or "5")
ZERO = Decimal("0.00")


def q(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def pct(base: Decimal, p: Decimal) -> Decimal:
    return q(base * p / Decimal("100"))


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def tl_share_for(order) -> Decimal:
    try:
        team = order.payment_details.group.trader.team
    except Exception:
        return ZERO
    if team is None or not team.teamlead_id:
        return ZERO
    return pct(q(order.usd_amount), q(team.teamlead_percentage))


def merchant_fee_usd(order) -> Decimal:
    mf, amount, usd = q(order.merchant_fee), q(order.amount), q(order.usd_amount)
    try:
        if uses_melbet_fiat_settlement(order.solution.merchant, order.solution.payment_system):
            if amount > 0 and usd > 0:
                return q(mf * usd / amount)
    except Exception:
        pass
    return mf


def trader_fee_usd(order) -> Decimal:
    tf, amount, usd = q(order.trader_fee), q(order.amount), q(order.usd_amount)
    try:
        if uses_melbet_fiat_settlement(order.solution.merchant, order.solution.payment_system):
            # Melbet OUT legacy: trader_fee мог быть в фиате (> usd)
            if amount > 0 and usd > 0 and tf > usd:
                return q(tf * usd / amount)
    except Exception:
        pass
    return tf


def is_melbet_order(order) -> bool:
    try:
        return uses_melbet_fiat_settlement(order.solution.merchant, order.solution.payment_system)
    except Exception:
        return False


def main() -> None:
    now = timezone.now().astimezone(MSK)
    _, day_start, _ = moscow_bounds(now)
    window_start = day_start - timedelta(days=DAYS - 1)
    since = window_start

    snap = snapshot(now=now)
    section("РЕАЛЬНЫЕ ДЕНЬГИ (A−L) vs day NET")
    print(f"as_of={snap['as_of']}")
    print(f"Касса A−L={snap['cash']}  assets={snap['assets']['total']}  liab={snap['liabilities']['total']}")
    print(f"  wallets={snap['assets'].get('wallet_total')}  PSP={snap['assets']['psp_total']}  "
          f"receivables(Melbet/…)={snap['assets'].get('receivables_total')}")
    print(f"  merchants={snap['liabilities']['merchants_total']}  "
          f"traders={snap['liabilities'].get('traders_owed_total')}  "
          f"TL={snap['liabilities']['teamleads_total']}  "
          f"agents={snap['liabilities']['agents_total']}")
    print(f"day NET={snap['pnl']['day']['net']}  month NET={snap['pnl']['month']['net']}")
    print(f"memo aggregator type=2={snap['memo']['platform_aggregator']}  ← НЕ реальные деньги")

    section(f"1) Day NET по дням (последние {DAYS})")
    day_nets = []
    for i in range(DAYS):
        d0 = window_start + timedelta(days=i)
        d1 = d0 + timedelta(days=1)
        p = _period_pnl(d0, d1)
        day_nets.append(q(p["net"]))
        print(
            f"  {d0.date()} NET={p['net']}  "
            f"MDR_in={p['payin_mdr']} MDR_out={p['payout_mdr']} FX={p['payin_fx']} "
            f"trader={p['trader_fee']} agent={p['agent_fee']} exp={p['expenses']}"
        )
    print(f"  SUM day NET window = {q(sum(day_nets, ZERO))}")

    ins = list(
        InOrder.objects.filter(
            status__name="Completed",
            completion_date__gte=since,
        )
        .select_related(
            "solution__merchant__user",
            "solution__payment_system",
            "payment_details__group__trader__team__teamlead__user",
        )
        .order_by("completion_date")
    )
    outs = list(
        OutOrder.objects.filter(
            status__name="Completed",
            completion_date__gte=since,
        )
        .select_related(
            "solution__merchant__user",
            "solution__payment_system",
            "payment_details__group__trader__team__teamlead__user",
        )
        .order_by("completion_date")
    )

    section(f"2) Fee waterfall Completed IN+OUT с {since.date()} (все мерчи)")
    tot = {
        "n_in": 0,
        "n_out": 0,
        "turn_in": ZERO,
        "turn_out": ZERO,
        "mdr": ZERO,
        "trader": ZERO,
        "agent": ZERO,
        "tl": ZERO,
        "fx": ZERO,
        "pnl": ZERO,
        "neg_pnl_n": 0,
        "neg_pnl_sum": ZERO,
        "tl_gt_pnl_n": 0,
        "melbet_in_turn": ZERO,
        "melbet_in_mdr": ZERO,
        "melbet_in_trader": ZERO,
        "melbet_prepaid_burn": ZERO,  # sum(usd − mdr) — сколько prepaid «съели» IN
        "melbet_al_delta": ZERO,  # ожидаемый Δ A−L от Melbet IN: −(usd−mdr) − trader
        "other_in_liab_merchant": ZERO,  # sum(usd − mdr) рост долга мерчу
        "other_in_pnl": ZERO,
        "merchant_credit_check_bad": 0,
    }
    by_merchant = defaultdict(lambda: {
        "turn": ZERO, "mdr": ZERO, "trader": ZERO, "agent": ZERO, "tl": ZERO, "pnl": ZERO, "n": 0,
    })
    by_team = defaultdict(lambda: {
        "turn": ZERO, "trader": ZERO, "tl": ZERO, "pnl": ZERO, "n": 0, "tl_pct": None, "name": "",
    })
    worst = []  # (pnl, id, kind)

    for order in ins:
        tot["n_in"] += 1
        usd = q(order.usd_amount)
        psp = q(order.psp_usd_amount or order.usd_amount)
        mdr = merchant_fee_usd(order)
        tf = trader_fee_usd(order)
        af = q(order.agent_fee)
        fx = q(psp - usd)
        tl = tl_share_for(order)
        pnl = q(mdr + fx - tf - af)
        tot["turn_in"] += usd
        tot["mdr"] += mdr
        tot["trader"] += tf
        tot["agent"] += af
        tot["tl"] += tl
        tot["fx"] += fx
        tot["pnl"] += pnl
        if pnl < 0:
            tot["neg_pnl_n"] += 1
            tot["neg_pnl_sum"] += pnl
        if tl > pnl and pnl >= 0:
            tot["tl_gt_pnl_n"] += 1
        worst.append((pnl, order.id, "IN", usd, mdr, tf, tl))

        # merchant credit sanity: Melbet = amount−fee; else usd−merchant_fee
        if is_melbet_order(order):
            expected_credit = in_order_credit_kzt(order)
            # can't easily re-read ledger; check formula consistency
            formula = q(q(order.amount) - q(order.merchant_fee))
            if formula != expected_credit:
                tot["merchant_credit_check_bad"] += 1
            tot["melbet_in_turn"] += usd
            tot["melbet_in_mdr"] += mdr
            tot["melbet_in_trader"] += tf
            burn = q(usd - mdr)  # prepaid asset shrink
            tot["melbet_prepaid_burn"] += burn
            # A−L: asset Melbet −burn; liability team +tf (TL режется с трейдера)
            tot["melbet_al_delta"] += q(-burn - tf)
        else:
            credit = q(usd - q(order.merchant_fee))
            tot["other_in_liab_merchant"] += credit
            tot["other_in_pnl"] += pnl

        mname = order.solution.merchant.user.username if order.solution_id else "?"
        bm = by_merchant[mname]
        bm["turn"] += usd
        bm["mdr"] += mdr
        bm["trader"] += tf
        bm["agent"] += af
        bm["tl"] += tl
        bm["pnl"] += pnl
        bm["n"] += 1

        try:
            team = order.payment_details.group.trader.team
            tkey = team.id if team else 0
            bt = by_team[tkey]
            bt["turn"] += usd
            bt["trader"] += tf
            bt["tl"] += tl
            bt["pnl"] += pnl
            bt["n"] += 1
            if team:
                bt["name"] = team.name
                bt["tl_pct"] = q(team.teamlead_percentage)
        except Exception:
            pass

    for order in outs:
        tot["n_out"] += 1
        usd = q(order.usd_amount)
        mdr = merchant_fee_usd(order)
        tf = trader_fee_usd(order)
        af = ZERO  # outs обычно без agent
        tl = tl_share_for(order)
        pnl = q(mdr - tf - af)
        tot["turn_out"] += usd
        tot["mdr"] += mdr
        tot["trader"] += tf
        tot["tl"] += tl
        tot["pnl"] += pnl
        if pnl < 0:
            tot["neg_pnl_n"] += 1
            tot["neg_pnl_sum"] += pnl
        worst.append((pnl, order.id, "OUT", usd, mdr, tf, tl))

        mname = order.solution.merchant.user.username if order.solution_id else "?"
        bm = by_merchant[mname]
        bm["turn"] += usd
        bm["mdr"] += mdr
        bm["trader"] += tf
        bm["tl"] += tl
        bm["pnl"] += pnl
        bm["n"] += 1

        try:
            team = order.payment_details.group.trader.team
            tkey = team.id if team else 0
            bt = by_team[tkey]
            bt["turn"] += usd
            bt["trader"] += tf
            bt["tl"] += tl
            bt["pnl"] += pnl
            bt["n"] += 1
            if team:
                bt["name"] = team.name
                bt["tl_pct"] = q(team.teamlead_percentage)
        except Exception:
            pass

    print(f"IN n={tot['n_in']} turn={tot['turn_in']}  OUT n={tot['n_out']} turn={tot['turn_out']}")
    print(f"MDR_usd={tot['mdr']}  trader={tot['trader']}  agent={tot['agent']}  FX={tot['fx']}")
    print(f"platform_pnl (MDR+FX−trader−agent) = {tot['pnl']}")
    print(f"TL share (из trader, % оборота)     = {tot['tl']}")
    print(f"negative-margin deals: n={tot['neg_pnl_n']} sum_pnl={tot['neg_pnl_sum']}")
    print(f"deals where TL > platform_pnl (≥0): n={tot['tl_gt_pnl_n']}")
    print(f"merchant credit formula mismatches: {tot['merchant_credit_check_bad']}")

    section("3) ТЕОРИЯ A — Melbet prepaid burn (почему +70$ не видно в тетради)")
    print("Melbet IN complete:")
    print("  • кредитует Melbet.balance_kzt на (amount−fee) → prepaid/долг Melbet ↓ на ≈(usd−mdr)")
    print("  • платит trader_fee на ЛК трейдера → пассив команде ↑ на trader_fee")
    print("  • day NET считает только (mdr−trader−agent+fx) ≈ 1% оборота")
    print("  • реальный Δ A−L ≈ −(usd−mdr) − trader_fee ≈ −оборот + крошечный спред")
    print()
    print(f"  Melbet IN turn={tot['melbet_in_turn']}  mdr={tot['melbet_in_mdr']}  trader={tot['melbet_in_trader']}")
    print(f"  prepaid BURN (usd−mdr)           = {tot['melbet_prepaid_burn']}")
    print(f"  ожидаемый Δ A−L от Melbet IN     = {tot['melbet_al_delta']}")
    print(f"  «бумажный» Melbet IN pnl         = {q(tot['melbet_in_mdr'] - tot['melbet_in_trader'])}")
    if tot["melbet_in_turn"] > 0:
        print(
            f"  → на ${tot['melbet_in_turn']} оборота Melbet касса тетради падает на "
            f"~${q(-tot['melbet_al_delta'])}, а day NET показывает только спред "
            f"~${q(tot['melbet_in_mdr'] - tot['melbet_in_trader'])}"
        )

    section("3b) Non-Melbet IN: рост долга мерчам")
    print(f"  sum(usd − merchant_fee) → liability мерчам = {tot['other_in_liab_merchant']}")
    print(f"  platform_pnl этих IN                    = {tot['other_in_pnl']}")
    print("  (деньги мерчу: списались с aggregator memo; в A−L пассив ↑, маржа в type=2)")

    section("4) ТЕОРИЯ B/C/D — переплата команде / мерчу / TL")
    # B: negative platform pnl
    if tot["neg_pnl_n"] == 0 and tot["pnl"] >= 0:
        print(f"  B) trader+agent vs MDR+FX: OK — суммарный pnl={tot['pnl']} ≥ 0, "
              f"убыточных сделок={tot['neg_pnl_n']}")
    else:
        print(f"  B) ВОЗМОЖНА переплата команде: neg deals={tot['neg_pnl_n']} "
              f"sum={tot['neg_pnl_sum']}  total_pnl={tot['pnl']}")
    # C
    print(f"  C) мерч credit formula bad count={tot['merchant_credit_check_bad']} "
          f"(0 = мерчу не даём больше amount−fee / usd−fee в create)")
    # D
    print(f"  D) TL режется С трейдера (% оборота), не доп. расход площадки.")
    print(f"     TL total={tot['tl']}; сделок где TL>pnl={tot['tl_gt_pnl_n']}")
    print("     Δ A−L от TL = 0 (пассив trader→пассив TL). Но трейдеру «нетто» меньше.")

    worst.sort(key=lambda x: x[0])
    print("\n  worst 10 deals by platform_pnl:")
    for pnl, oid, kind, usd, mdr, tf, tl in worst[:10]:
        print(f"    {kind} {oid} usd={usd} mdr={mdr} trader={tf} tl={tl} pnl={pnl}")

    section("5) По мерчантам (turn / mdr / trader / tl / pnl)")
    for name, row in sorted(by_merchant.items(), key=lambda kv: kv[1]["pnl"]):
        if row["n"] == 0:
            continue
        print(
            f"  {name}: n={row['n']} turn={row['turn']} mdr={row['mdr']} "
            f"trader={row['trader']} agent={row['agent']} tl={row['tl']} pnl={row['pnl']}"
        )

    section("6) По командам (tl% / turn / trader / tl / pnl)")
    for _, row in sorted(by_team.items(), key=lambda kv: kv[1]["tl"], reverse=True):
        if row["n"] == 0:
            continue
        print(
            f"  {row['name'] or '?'}: tl%={row['tl_pct']} n={row['n']} turn={row['turn']} "
            f"trader={row['trader']} tl={row['tl']} pnl={row['pnl']}"
        )

    section("7) Ставки C2CKZT: mdr_in − trader_mdr vs tl%")
    rates = (
        TraderTeamRates.objects.filter(payment_system__name="C2CKZT")
        .select_related("team", "team__teamlead__user")
        .order_by("team__name")
    )
    tight = 0
    for r in rates:
        # merchant mdr is on MerchantSolution — compare team mdr vs typical melbet 7.5
        team_mdr = q(r.mdr_in)
        tl_pct = q(r.team.teamlead_percentage) if r.team_id else ZERO
        # platform keep vs melbet typical 7.5 if team is Melbet lane
        print(
            f"  team={r.team.name} team_mdr_in={team_mdr} mdr_out={q(r.mdr_out)} "
            f"tl%={tl_pct}  (если Melbet mdr_in=7.5 → keep≈{q(Decimal('7.5') - team_mdr)}% "
            f"до agent; TL={tl_pct}% оборота)"
        )
        if tl_pct > q(Decimal("7.5") - team_mdr):
            tight += 1
    print(f"  teams where tl% > (7.5 − team_mdr): {tight}")

    # Melbet current prepaid
    section("8) Melbet prepaid сейчас")
    melbet = (
        Merchant.objects.filter(user__username__iexact=MELBET_USERNAME)
        .select_related("balance_kzt", "frozen_balance_kzt")
        .first()
    )
    if melbet:
        from basics.cash_register import kzt_to_usd

        kzt = money(
            (melbet.balance_kzt.amount if melbet.balance_kzt_id else 0)
            + (melbet.frozen_balance_kzt.amount if melbet.frozen_balance_kzt_id else 0)
        )
        print(f"  balance_kzt+frozen={kzt}  ≈ usd={kzt_to_usd(kzt)}")
        print("  (отрицательный KZT в кассе = receivable/prepaid Melbet)")

    section("ВЕРДИКТ")
    print("1) Агрегатор type=2 — не реальные деньги. Согласны. В A−L его нет.")
    print("2) Маржа day NET ≠ рост кассы в тетради, пока основной оборот — Melbet prepaid:")
    print("   каждый IN сжигает prepaid ≈ оборот, а NET пишет только спред MDR−trader.")
    print(f"   За окно: Melbet burn≈{tot['melbet_prepaid_burn']} vs Melbet spread≈"
          f"{q(tot['melbet_in_mdr'] - tot['melbet_in_trader'])} vs SUM day NET="
          f"{q(sum(day_nets, ZERO))}.")
    print("3) Переплата команде (B): смотри neg_pnl_n / total pnl выше.")
    print("4) Переплата мерчу (C): credit = amount−fee / usd−fee — bad count выше.")
    print("5) TL (D): не ломает A−L сам по себе (перевод trader↔TL). Ломает «чистоту»")
    print("   маржи трейдера; если TL% > keep% — команда в минусе при формально +NET.")
    print("6) Чтобы касса тетради росла на day NET, нужен приток реальных USDT")
    print("   (Melbet prepaid top-up / вывод с PSP на TronLink) − рост долгов.")

    # TL commission txs in window
    tl_tx = (
        Transaction.objects.filter(
            creation_date__gte=since,
            comment__icontains="Teamlead commission",
        ).aggregate(s=Sum("value"))["s"]
        or 0
    )
    trader_comm = (
        Transaction.objects.filter(
            creation_date__gte=since,
            comment="Commission",
        ).aggregate(s=Sum("value"))["s"]
        or 0
    )
    print(f"\nLedger check window: Commission→traders={money(trader_comm)}  "
          f"Teamlead commission={money(tl_tx)}")
    print("DONE")


main()
