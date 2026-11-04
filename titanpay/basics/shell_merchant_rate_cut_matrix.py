"""Матрица доходности: текущий MDR мерчанта vs PSP при цели ≥ TARGET%.

Показывает live MerchantSolution.mdr_in / агента и минимальную ставку,
до которой можно опуститься на каждом провайдере без падения ниже TARGET.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_merchant_rate_cut_matrix.py

  MERCHANTS=aggrepay,pandapay TARGET=1.5 PS=C2CKZT
"""
from __future__ import annotations

import json
import os
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

from basics.models import Trader, TraderTeamRates
from merchant.models import Agent, Merchant, MerchantSolution
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


def agent_pct(merchant: Merchant) -> Decimal:
    row = Agent.objects.filter(merchant=merchant).order_by("id").first()
    if row is None:
        return Decimal("0")
    return Decimal(str(row.commission_percent or 0))


def yield_pct(mdr: Decimal, trader_mdr: Decimal, ratio: Decimal, agent: Decimal) -> Decimal:
    # pnl% of merchant_usd = M - T*r + 100*(r-1) - A
    return mdr - trader_mdr * ratio + Decimal("100") * (ratio - Decimal("1")) - agent


def min_mdr(trader_mdr: Decimal, ratio: Decimal, agent: Decimal, target: Decimal) -> Decimal:
    return target + trader_mdr * ratio - Decimal("100") * (ratio - Decimal("1")) + agent


def run() -> None:
    print("=" * 78)
    print(f"RATE CUT MATRIX  PS={PS_NAME}  TARGET≥{TARGET}%  merchants={','.join(MERCHANTS)}")
    print("=" * 78)

    # resolve PS markup from a sample solution later; default xe+5
    default_mm = Decimal("1.05")

    for uname in MERCHANTS:
        merchant = (
            Merchant.objects.select_related("user")
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
            traffic = getattr(getattr(sol, "traffic", None), "name", None) or "—"
            print(
                f"  solution id={sol.id}  ftd={sol.ftd}  traffic={traffic}  "
                f"mdr_in={sol.mdr_in}%  fx_markup={mm}  "
                f"limits={sol.min_limit_in}…{sol.max_limit_in}"
            )
            cur_m = Decimal(str(sol.mdr_in))
            print(
                f"  {'PSP':12} {'T%':>5} {'FX':>5} {'r':>6} {'now%':>6} "
                f"{'minM':>6} {'maxCut':>7}  note"
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
                # bitzone may use P2P — if markup equals merchant, r=1
                if pm <= 0:
                    pm = mm
                ratio = (mm / pm) if pm else Decimal("1")
                y = yield_pct(cur_m, T, ratio, agent)
                floor = min_mdr(T, ratio, agent, TARGET)
                cut = cur_m - floor
                flag = "OK" if y >= TARGET else "BELOW 1.5"
                if binding is None or floor > binding_min:
                    binding = psp
                    binding_min = floor
                print(
                    f"  {psp:12} {T:5.2f} {pm:5.3f} {ratio:6.4f} {_q(y):6.2f} "
                    f"{_q(floor):6.2f} {_q(cut):7.2f}  {flag}"
                )
            print(
                f"  → единый MDR не ниже {_q(binding_min)}% "
                f"(жёсткий PSP={binding}), иначе режь только дешёвый каскад"
            )

    # cascade hint from env
    raw_pri = getattr(settings, "PSP_CASCADE_PRIORITY", None) or ""
    raw_share = getattr(settings, "PSP_ROUTING_SHARE_MAP", None) or ""
    print("\n=== cascade env (global, не per-merchant) ===")
    print(f"  PSP_CASCADE_PRIORITY={raw_pri}")
    print(f"  PSP_ROUTING_SHARE_MAP={raw_share}")
    print("\nDONE")


run()
