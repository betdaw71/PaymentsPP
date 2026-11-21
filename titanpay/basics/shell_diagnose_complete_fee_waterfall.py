"""Диагностика complete() money flows: MDR / trader / agent / teamlead vs агрегатор.

Теория: дневной NET ~+$70 не виден в (реальные активы − реальные долги);
агрегатор type=2 (~325k) — НЕ реальные деньги. Проверяем:
  • Melbet IN паркует почти весь usd_amount на aggregator (мерч платится с blockchain→KZT)
  • Melbet OUT льёт KZT-суммы (amount+fee) на aggregator (type=2 «USDT»)
  • teamlead_percentage = % от ОБОРОТА (usd_amount), режется с трейдера;
    TL может быть больше platform margin (MDR−trader−agent±FX)

Пример (без БД):
  docker compose exec -T \\
    -e USD=100 -e RATE=500 -e MDR_IN=7.5 -e TRADER_MDR=6.5 -e AGENT_PCT=0.2 -e TL_PCT=0.5 \\
    app python manage.py shell < titanpay/basics/shell_diagnose_complete_fee_waterfall.py

Live Melbet C2CKZT rates + last Completed (опционально):
  docker compose exec -T -e LIVE=1 -e DAYS=3 \\
    app python manage.py shell < titanpay/basics/shell_diagnose_complete_fee_waterfall.py
"""
from __future__ import annotations

import os
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

Q2 = Decimal("0.01")


def money(raw) -> Decimal:
    return Decimal(str(raw or 0)).quantize(Q2, rounding=ROUND_HALF_UP)


def pct_of(base: Decimal, pct: Decimal) -> Decimal:
    return money(base * pct / Decimal("100"))


def section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def print_example(
    *,
    usd: Decimal,
    rate: Decimal,
    mdr_in: Decimal,
    trader_mdr: Decimal,
    agent_pct: Decimal,
    tl_pct: Decimal,
    psp_usd: Decimal | None = None,
    mdr_out: Decimal | None = None,
    trader_mdr_out: Decimal | None = None,
) -> None:
    """Математика как в create()+complete() для Melbet fiat IN/OUT."""
    amount = money(usd * rate)
    psp = money(psp_usd if psp_usd is not None else usd)
    # Melbet IN: merchant_fee в KZT; trader_fee / agent в USDT (agent через KZT→USD)
    merchant_fee_kzt = pct_of(amount, mdr_in)
    merchant_fee_usd = money(merchant_fee_kzt * usd / amount) if amount else Decimal("0")
    trader_fee = pct_of(psp, trader_mdr)
    agent_fee = money(pct_of(amount, agent_pct) * usd / amount) if amount else Decimal("0")
    tl_share = pct_of(usd, tl_pct)
    fx = money(psp - usd)
    platform_pnl = money(merchant_fee_usd + fx - trader_fee - agent_fee)

    for_merchant_kzt = money(amount - merchant_fee_kzt)
    # Melbet InOrder.complete: Δ aggregator = +usd − trader_fee  (мерч с type=3)
    agg_delta_in = money(usd - trader_fee)
    # Non-Melbet: Δ aggregator = merchant_fee − trader_fee
    agg_delta_in_usdt_path = money(merchant_fee_usd - trader_fee)

    section(f"EXAMPLE Melbet KZT PAY-IN  usd={usd} rate={rate} → amount={amount} KZT")
    print("Fees (create):")
    print(f"  merchant_fee = mdr_in% × amount          = {mdr_in}% × {amount} = {merchant_fee_kzt} KZT")
    print(f"                 → USDT via fee×usd/amount = {merchant_fee_usd} USDT")
    print(f"  trader_fee   = trader_mdr% × psp_usd     = {trader_mdr}% × {psp} = {trader_fee} USDT")
    print(f"  agent_fee    = agent% × turnover (USDT)  = {agent_pct}% → {agent_fee} USDT")
    print(f"  teamlead     = TL% × usd_amount          = {tl_pct}% × {usd} = {tl_share} USDT")
    print(f"  FX spread    = psp_usd − merchant_usd    = {psp} − {usd} = {fx}")
    print()
    print("Platform PnL (cash_register / deal_margin; TL НЕ вычитается):")
    print(f"  pnl = mdr_usd + fx − trader − agent = {merchant_fee_usd} + {fx} − {trader_fee} − {agent_fee}")
    print(f"      = {platform_pnl} USDT  ({money(platform_pnl * 100 / usd) if usd else 0}% of turnover)")
    print(f"  TL share = {tl_share} USDT  → TL {'EXCEEDS' if tl_share > platform_pnl else '≤'} platform margin")
    print("  (TL режется с trader.balance_usdt после Commission; не доп. расход площадки)")
    print()
    print("InOrder.complete() Melbet fiat ledger:")
    print(f"  1 Charge  trader.frozen → aggregator(type=2)   +{usd} USDT")
    print(f"  2 Deposit blockchain(type=3) → merchant.KZT    +{for_merchant_kzt} KZT")
    print(f"  3 Deposit aggregator → trader.balance          +{trader_fee} USDT (Commission)")
    print(f"  4 Charge  trader → teamlead.balance            +{tl_share} USDT (Teamlead commission)")
    print(f"  5 Deposit blockchain → agent.balance           +{agent_fee} USDT (Agent commission)")
    print()
    print(f"  ★ Δ aggregator Melbet IN  = +usd − trader_fee = {agg_delta_in} USDT")
    print(f"    (не маржа {platform_pnl}! почти весь оборот паркуется на type=2)")
    print(f"  ★ Δ aggregator USDT-path  = mdr − trader      = {agg_delta_in_usdt_path} USDT (норма)")

    m_out = mdr_out if mdr_out is not None else mdr_in
    t_out = trader_mdr_out if trader_mdr_out is not None else trader_mdr
    merchant_fee_out_kzt = pct_of(amount, m_out)
    trader_fee_out = pct_of(usd, t_out)
    for_merchant_out = money(amount + merchant_fee_out_kzt)
    for_trader_out = money(usd + trader_fee_out)
    payout_pnl = money(
        money(merchant_fee_out_kzt * usd / amount) - trader_fee_out
    ) if amount else Decimal("0")
    tl_out = pct_of(usd, tl_pct)
    agg_delta_out = money(for_merchant_out - for_trader_out)

    section(f"EXAMPLE Melbet KZT PAY-OUT  usd={usd} amount={amount} KZT")
    print(f"  merchant_fee (KZT) = {m_out}% × {amount} = {merchant_fee_out_kzt} KZT")
    print(f"  trader_fee (USDT)  = {t_out}% × {usd} = {trader_fee_out} USDT")
    print(f"  payout_pnl USDT    ≈ {payout_pnl}   TL={tl_out}")
    print("OutOrder.complete() Melbet fiat:")
    print(f"  1 Charge  merchant.frozen_kzt → aggregator   +{for_merchant_out}  ← KZT units на type=2!")
    print(f"  2 Deposit aggregator → trader.balance        +{for_trader_out} USDT")
    print(f"  3 Charge  trader → teamlead                  +{tl_out} USDT")
    print(f"  ★ Δ aggregator Melbet OUT ≈ {agg_delta_out}  (KZT-число минус USDT — раздувает memo)")


def print_code_map() -> None:
    section("CODE MAP (file:line)")
    print("Fee compute @ create:")
    print("  trade/models.py InOrder.create ~153–173  merchant_payin_fee / mdr_in×psp_usd / agent")
    print("  merchant/tiered_mdr.py:34–38             Melbet → merchant_fee_in_kzt(amount, mdr)")
    print("  merchant/kzt_settlement.py:144–153       fee KZT; credit=amount−fee; freeze=amount+fee")
    print("  merchant/agent_fee.py:5–22               Melbet: (amount×pct)×usd/amount → USDT")
    print("  trade/utils.py:11–41                     OutOrder calculate_fees (mdr_out spread)")
    print("  trade/models.py OutOrder.create ~1058–64 Melbet: fee KZT + trader_fee USDT")
    print()
    print("complete() transfers:")
    print("  trade/models.py InOrder.complete 322–402")
    print("    Melbet: charge usd→agg; blockchain→KZT credit; agg→trader_fee; trader→TL; agent from chain")
    print("  trade/models.py OutOrder.complete 1174–1232")
    print("    Melbet: frozen_kzt→agg (KZT!); agg→trader usd+fee; trader→TL")
    print("  TL formula: usd_amount × teamlead_percentage / 100  (оборот, НЕ trader_fee)")
    print("    InOrder 386–398  OutOrder 1220–1232  payments/deal_margin.py:4–5,164")
    print()
    print("PnL vs касса:")
    print("  basics/cash_register.py:329–335,444–510  day NET = MDR+FX − trader − agent (−exp)")
    print("  basics/cash_register.py:6,729–745         aggregator type=2 = memo, НЕ в A−L")
    print("  deal_margin: TL показан отдельно, в platform_pnl не входит")


def print_live(days: int) -> None:
    from django.db.models import Sum

    from basics.cash_register import (
        melbet_fiat_merchant_fee_usd_expr,
        melbet_fiat_trader_fee_usd_expr,
        money as cr_money,
        snapshot,
    )
    from basics.models import Balance, PaymentSystem, TraderTeamRates
    from merchant.kzt_settlement import MELBET_USERNAME, uses_melbet_fiat_settlement
    from merchant.models import Merchant, MerchantSolution
    from trade.models import InOrder, OutOrder, Transaction

    section(f"LIVE Melbet snapshot + last {days}d Completed")
    snap = snapshot()
    print(f"Касса A−L={snap['cash']}  day NET={snap['pnl']['day']['net']}  month NET={snap['pnl']['month']['net']}")
    print(f"memo.platform_aggregator={snap['memo']['platform_aggregator']}")
    agg = Balance.objects.filter(type=2).first()
    print(f"Balance type=2 amount now={cr_money(agg.amount if agg else 0)}")

    merchant = (
        Merchant.objects.filter(user__username__iexact=MELBET_USERNAME)
        .select_related("user", "agent", "balance_kzt", "balance")
        .first()
    )
    if merchant is None:
        print("melbet merchant not found — skip live rates")
        return

    ps = PaymentSystem.objects.filter(name="C2CKZT").first()
    sols = list(
        MerchantSolution.objects.filter(merchant=merchant, payment_system=ps, status=1).order_by("ftd", "id")
    )
    print(f"melbet agent_pct={getattr(merchant.agent, 'commission_percent', None)}")
    for s in sols:
        print(f"  solution ftd={s.ftd} mdr_in={s.mdr_in}% mdr_out={s.mdr_out}%")

    rates = list(
        TraderTeamRates.objects.filter(payment_system=ps).select_related("team", "team__teamlead__user")[:15]
    )
    print("sample team rates C2CKZT (first 15):")
    for r in rates:
        tl = r.team.teamlead.user.username if r.team.teamlead_id and r.team.teamlead.user_id else "-"
        print(
            f"  team={r.team.name} mdr_in={r.mdr_in} mdr_out={r.mdr_out} "
            f"tl={tl} tl%={r.team.teamlead_percentage}"
        )

    since = timezone.now() - timedelta(days=days)
    ins = InOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=since,
        solution__merchant=merchant,
        solution__payment_system=ps,
    )
    outs = OutOrder.objects.filter(
        status__name="Completed",
        completion_date__gte=since,
        solution__merchant=merchant,
        solution__payment_system=ps,
    )
    mdr_expr = melbet_fiat_merchant_fee_usd_expr()
    tf_expr = melbet_fiat_trader_fee_usd_expr()
    in_agg = ins.aggregate(
        turn=Sum("usd_amount"),
        mdr=Sum(mdr_expr),
        tf=Sum(tf_expr),
        agent=Sum("agent_fee"),
        n=Sum("usd_amount"),  # placeholder count via len
    )
    out_agg = outs.aggregate(
        turn=Sum("usd_amount"),
        mdr=Sum(mdr_expr),
        tf=Sum(tf_expr),
    )
    print(f"Completed IN  n={ins.count()} turn={cr_money(in_agg['turn'])} "
          f"mdr_usd={cr_money(in_agg['mdr'])} trader={cr_money(in_agg['tf'])} agent={cr_money(in_agg['agent'])}")
    print(f"Completed OUT n={outs.count()} turn={cr_money(out_agg['turn'])} "
          f"mdr_usd={cr_money(out_agg['mdr'])} trader={cr_money(out_agg['tf'])}")

    # Aggregator flows linked to Melbet C2CKZT orders
    if agg:
        in_ids = list(ins.values_list("id", flat=True)[:5000])
        out_ids = list(outs.values_list("id", flat=True)[:5000])
        into_in = (
            Transaction.objects.filter(to_balance=agg, linked_in_order_id__in=in_ids).aggregate(s=Sum("value"))["s"]
            or 0
        )
        out_of_in = (
            Transaction.objects.filter(from_balance=agg, linked_in_order_id__in=in_ids).aggregate(s=Sum("value"))["s"]
            or 0
        )
        into_out = (
            Transaction.objects.filter(to_balance=agg, linked_out_order_id__in=out_ids).aggregate(s=Sum("value"))["s"]
            or 0
        )
        out_of_out = (
            Transaction.objects.filter(from_balance=agg, linked_out_order_id__in=out_ids).aggregate(s=Sum("value"))["s"]
            or 0
        )
        print("Aggregator flows linked to Melbet C2CKZT Completed (window):")
        print(f"  IN  into_agg={cr_money(into_in)} out_of_agg={cr_money(out_of_in)} "
              f"net={cr_money(Decimal(str(into_in)) - Decimal(str(out_of_in)))}")
        print(f"  OUT into_agg={cr_money(into_out)} out_of_agg={cr_money(out_of_out)} "
              f"net={cr_money(Decimal(str(into_out)) - Decimal(str(out_of_out)))}")
        print("  (Melbet IN net ≈ sum(usd−trader_fee); OUT into_agg часто ≫ USDT — это KZT units)")

    # Sample one recent IN and show TL vs margin
    sample = (
        ins.select_related(
            "solution__merchant__agent",
            "solution__payment_system",
            "payment_details__group__trader__team__teamlead",
        )
        .order_by("-completion_date")
        .first()
    )
    if sample is not None:
        usd = money(sample.usd_amount)
        amt = money(sample.amount)
        mf = money(sample.merchant_fee)
        mf_usd = money(mf * usd / amt) if amt and uses_melbet_fiat_settlement(
            sample.solution.merchant, sample.solution.payment_system
        ) else mf
        tf = money(sample.trader_fee)
        af = money(sample.agent_fee)
        psp = money(sample.psp_usd_amount or sample.usd_amount)
        fx = money(psp - usd)
        pnl = money(mf_usd + fx - tf - af)
        team = sample.payment_details.group.trader.team if sample.payment_details_id else None
        tl_pct = money(team.teamlead_percentage) if team else Decimal("0")
        tl = pct_of(usd, tl_pct)
        print()
        print(f"sample IN {sample.id} amount={amt} usd={usd} psp_usd={psp}")
        print(f"  merchant_fee raw={mf} → usd={mf_usd}  trader_fee={tf} agent={af}")
        print(f"  platform_pnl={pnl}  tl%={tl_pct} tl_share={tl}  "
              f"TL_vs_pnl={'EXCEEDS' if tl > pnl else 'ok'}")


def main() -> None:
    usd = money(os.environ.get("USD") or "100")
    rate = money(os.environ.get("RATE") or "500")
    mdr_in = money(os.environ.get("MDR_IN") or "7.5")
    trader_mdr = money(os.environ.get("TRADER_MDR") or "6.5")
    agent_pct = money(os.environ.get("AGENT_PCT") or "0.2")
    tl_pct = money(os.environ.get("TL_PCT") or "0.5")
    mdr_out = money(os.environ.get("MDR_OUT") or "3.0")
    trader_mdr_out = money(os.environ.get("TRADER_MDR_OUT") or "2.5")
    psp_raw = os.environ.get("PSP_USD")
    psp_usd = money(psp_raw) if psp_raw else None
    live = (os.environ.get("LIVE") or "").strip().lower() in {"1", "true", "yes"}
    days = int(os.environ.get("DAYS") or "3")

    section("VERDICT")
    print("1) Агрегатор type=2 — учётный memo, НЕ реальные деньги (кошелёк/PSP/обязательства).")
    print("2) Melbet IN: на aggregator паркуется usd−trader_fee (memo); мерчу KZT с type=3.")
    print("   В РЕАЛЬНОЙ кассе (тетрадь): prepaid Melbet ↓ на (usd−mdr), пассив команде ↑ на trader_fee.")
    print("   Δ A−L ≈ −(usd−mdr)−trader ≈ −оборот + крошечный спред — НЕ +day NET.")
    print("3) Melbet OUT: amount+fee (KZT) на aggregator — memo; реал = списание Melbet + trader.")
    print("4) teamlead_percentage = % от usd_amount; режется с трейдера (пассив↔пассив).")
    print("   TL > platform margin возможен; A−L сам не ломает, «чистоту» маржи трейдера — да.")
    print("5) Утечка в команду/мерча: смотри shell_diagnose_real_money_fee_leak.py")
    print("   (neg pnl deals / credit≠amount−fee / Melbet prepaid burn vs SUM day NET).")
    print("6) day NET ≠ рост тетради, пока маржа не стала USDT на кошельке / не снизила реальный долг.")

    print_code_map()
    print_example(
        usd=usd,
        rate=rate,
        mdr_in=mdr_in,
        trader_mdr=trader_mdr,
        agent_pct=agent_pct,
        tl_pct=tl_pct,
        psp_usd=psp_usd,
        mdr_out=mdr_out,
        trader_mdr_out=trader_mdr_out,
    )

    # Second example: tight margin where TL > pnl (как в test_deal_margin)
    section("TIGHT-MARGIN CASE (TL > platform pnl) — как payments/tests/test_deal_margin.py")
    print_example(
        usd=Decimal("100.00"),
        rate=Decimal("525"),
        mdr_in=Decimal("6.0"),
        trader_mdr=Decimal("6.5"),
        agent_pct=Decimal("0.2"),
        tl_pct=Decimal("0.5"),
        psp_usd=Decimal("100.96"),
        mdr_out=Decimal("3.0"),
        trader_mdr_out=Decimal("2.5"),
    )

    if live:
        print_live(days)

    print()
    print("DONE")


main()
