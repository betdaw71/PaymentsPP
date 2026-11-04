"""Матрица зазора: (MDR+FX) мерча − (MDR+FX) PSP − агент ≥ TARGET%.

Считаем как в тетради: комиссия и курсовая наценка пакетом с каждой стороны,
между пакетами должен оставаться зазор (по умолчанию 1.5%).
Дополнительно колонка exact% — как в кассе (fee±FX на USDT).

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_merchant_rate_cut_matrix.py

  MERCHANTS=aggrepay,pandapay TARGET=1.5 PS=C2CKZT
"""
from __future__ import annotations

import os
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from basics.models import Trader, TraderTeamRates
from merchant.models import Merchant, MerchantSolution
from payments.dual_fx import merchant_fx_markup, psp_fx_markup_for_trader

MERCHANTS = [
    p.strip()
    for p in (os.environ.get("MERCHANTS") or "aggrepay,pandapay").split(",")
    if p.strip()
]
PS_NAME = (os.environ.get("PS") or "C2CKZT").strip()
TARGET = Decimal(str(os.environ.get("TARGET") or "1.5"))
PSP_ORDER = [
    "payplat1",
    "gipay1",
    "patriot1",
    "visionx1",
    "layerone1",
    "prochub1",
    "nexus1",
    "plutus1",
    "bitzone1",
]


def _q(x: Decimal, places="0.01") -> Decimal:
    return x.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def fx_pp(markup: Decimal) -> Decimal:
    return (markup - Decimal("1")) * Decimal("100")


def agent_pct(merchant: Merchant) -> Decimal:
    agent = getattr(merchant, "agent", None)
    if agent is None:
        return Decimal("0")
    return Decimal(str(agent.commission_percent or 0))


def notebook_gap(mdr: Decimal, trader_mdr: Decimal, m_fx: Decimal, p_fx: Decimal, agent: Decimal) -> Decimal:
    """(MDR_m + FX_m) − (MDR_p + FX_p) − agent."""
    return (mdr + m_fx) - (trader_mdr + p_fx) - agent


def min_mdr_notebook(trader_mdr: Decimal, m_fx: Decimal, p_fx: Decimal, agent: Decimal, target: Decimal) -> Decimal:
    # M + m_fx - T - p_fx - A >= target → M >= target + T + p_fx - m_fx + A
    return target + trader_mdr + p_fx - m_fx + agent


def exact_pnl_pct(mdr: Decimal, trader_mdr: Decimal, ratio: Decimal, agent: Decimal) -> Decimal:
    """Касса: (merchant_fee - trader_fee + fx_spread - agent) / merchant_usd * 100."""
    return mdr - trader_mdr * ratio + Decimal("100") * (ratio - Decimal("1")) - agent


def run() -> None:
    print("=" * 88)
    print(
        f"RATE CUT MATRIX (пакет MDR+FX)  PS={PS_NAME}  "
        f"TARGET gap≥{TARGET}%  merchants={','.join(MERCHANTS)}"
    )
    print("  gap = (MDR_merch + FX_merch) − (MDR_psp + FX_psp) − agent")
    print("=" * 88)

    default_mm = Decimal("1.05")

    for uname in MERCHANTS:
        merchant = (
            Merchant.objects.select_related("user", "agent")
            .filter(user__username__iexact=uname)
            .first()
        )
        if merchant is None:
            print(f"\n! {uname}: merchant not found")
            continue
        agent = agent_pct(merchant)
        sols = (
            MerchantSolution.objects.filter(
                merchant=merchant,
                payment_system__name__iexact=PS_NAME,
            )
            .select_related("payment_system", "traffic")
            .order_by("ftd", "id")
        )
        if not sols.exists():
            print(f"\n! {uname}: no MerchantSolution for {PS_NAME}")
            continue

        print(f"\n### {uname}  agent={agent}%")
        for sol in sols:
            mm = merchant_fx_markup(sol.payment_system) or default_mm
            m_fx = fx_pp(mm)
            traffic = getattr(getattr(sol, "traffic", None), "name", None) or "—"
            cur_m = Decimal(str(sol.mdr_in))
            merch_pack = cur_m + m_fx
            print(
                f"  solution id={sol.id}  ftd={sol.ftd}  traffic={traffic}  "
                f"mdr_in={cur_m}%  FX=+{m_fx}%  pack={merch_pack}%  "
                f"limits={sol.min_limit_in}…{sol.max_limit_in}"
            )
            print(
                f"  {'PSP':12} {'T%':>5} {'FX_p':>5} {'pack_p':>7} "
                f"{'gap':>6} {'exact':>6} {'minM':>6} {'maxCut':>7}  note"
            )
            binding = None
            binding_min = Decimal("0")
            for psp in PSP_ORDER:
                trader = (
                    Trader.objects.filter(user__username__iexact=psp)
                    .select_related("user", "team")
                    .first()
                )
                if trader is None or trader.team_id is None:
                    print(f"  {psp:12}  — no trader")
                    continue
                rate = (
                    TraderTeamRates.objects.filter(
                        team=trader.team,
                        payment_system=sol.payment_system,
                    ).first()
                )
                if rate is None:
                    print(f"  {psp:12}  — no TraderTeamRates on {PS_NAME}")
                    continue
                T = Decimal(str(rate.mdr_in))
                pm = psp_fx_markup_for_trader(trader, fallback=mm)
                if pm <= 0:
                    pm = mm
                p_fx = fx_pp(pm)
                psp_pack = T + p_fx
                gap = notebook_gap(cur_m, T, m_fx, p_fx, agent)
                ratio = (mm / pm) if pm else Decimal("1")
                exact = exact_pnl_pct(cur_m, T, ratio, agent)
                floor = min_mdr_notebook(T, m_fx, p_fx, agent, TARGET)
                cut = cur_m - floor
                flag = "OK" if gap >= TARGET else f"BELOW {TARGET}"
                if binding is None or floor > binding_min:
                    binding = psp
                    binding_min = floor
                print(
                    f"  {psp:12} {T:5.2f} {p_fx:5.2f} {psp_pack:7.2f} "
                    f"{_q(gap):6.2f} {_q(exact):6.2f} {_q(floor):6.2f} {_q(cut):7.2f}  {flag}"
                )
            print(
                f"  → единый MDR не ниже {_q(binding_min)}% "
                f"(жёсткий PSP={binding} по пакетному зазору), "
                f"иначе сужай каскад"
            )

    raw_pri = getattr(settings, "PSP_CASCADE_PRIORITY", None) or getattr(
        settings, "PSP_ROUTING_PRIORITY_MAP", None
    ) or ""
    raw_share = getattr(settings, "PSP_ROUTING_SHARE_MAP", None) or ""
    print("\n=== cascade env (global, не per-merchant) ===")
    print(f"  priority={raw_pri}")
    print(f"  PSP_ROUTING_SHARE_MAP={raw_share}")
    print("\nDONE")


run()
