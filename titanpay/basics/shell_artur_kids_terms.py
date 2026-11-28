"""Условия artur_kids: MDR, курс (XE), маржа площадки vs трейдер/PSP.

  docker compose exec -T -e MERCHANT=artur_kids -e AMOUNT=10000 -e PS=C2CKZT \\
    app python manage.py shell < titanpay/basics/shell_artur_kids_terms.py

  HOURS=24 — ещё сводка Success за окно
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from basics.models import PaymentSystem, Trader, TraderTeamRates
from basics.utils import xe_kzt_markup_for_merchant, xe_kzt_markup_for_ps
from merchant.models import Merchant, MerchantSolution
from merchant.tiered_mdr import effective_mdr_in
from payments.deal_margin import deal_margin_min_pct, quote_deal_margin
from payments.dual_fx import merchant_fx_markup, psp_fx_markup_for_trader, quote_dual_fx
from payments.models import PayIn
from trade.models import InOrder

MERCHANT = (os.environ.get("MERCHANT") or "artur_kids").strip()
AMOUNT = Decimal(str(os.environ.get("AMOUNT") or "10000"))
PS_NAME = (os.environ.get("PS") or "C2CKZT").strip()
HOURS = float(os.environ.get("HOURS") or "24")
TRADERS = [
    t.strip()
    for t in (os.environ.get("TRADERS") or "astrum_kzt,patriot1,gipay1,payplat1,resdfe,resdfe1").split(",")
    if t.strip()
]


def _money(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"))


print("=" * 72)
print(f"Merchant terms / margin  merchant={MERCHANT}  amount={AMOUNT}  ps={PS_NAME}")
print("=" * 72)

merchant = Merchant.objects.select_related("user", "agent").filter(user__username__iexact=MERCHANT).first()
if merchant is None:
    print(f"FAIL: merchant {MERCHANT!r} not found")
    raise SystemExit(1)

ps = PaymentSystem.objects.select_related("currency").filter(name__iexact=PS_NAME).first()
if ps is None:
    print(f"FAIL: PS {PS_NAME!r} not found")
    raise SystemExit(1)

sols = list(
    MerchantSolution.objects.filter(merchant=merchant, payment_system=ps, status=1)
    .select_related("traffic")
    .order_by("ftd", "id")
)
print(f"\nMerchantSolution ({PS_NAME}):")
if not sols:
    print("  (нет активных)")
for sol in sols:
    eff = effective_mdr_in(sol, AMOUNT)
    print(
        f"  ftd={sol.ftd} traffic={getattr(sol.traffic, 'name', None)} "
        f"mdr_in={sol.mdr_in}% effective@{AMOUNT}={eff}% "
        f"limits=[{sol.min_limit_in}..{sol.max_limit_in}]"
    )

stored = Decimal(str(ps.get_rate()))
ps_markup = xe_kzt_markup_for_ps(ps.name)
mm = xe_kzt_markup_for_merchant(MERCHANT, ps.name)
xe_map = getattr(settings, "XE_KZT_MARKUP_BY_MERCHANT", "") or ""
print(f"\nКурс / XE markup:")
print(f"  PS.usdt_exchange_rate (stored): {stored}  ← это курс в PS (обычно XE×ps_markup)")
print(f"  XE_KZT_MARKUP_BY_PS[{PS_NAME}]:   {ps_markup}  (1.05 = xe+5)")
print(f"  XE_KZT_MARKUP_BY_MERCHANT[{MERCHANT}]: {mm}")
print(f"  raw XE_KZT_MARKUP_BY_MERCHANT env: {xe_map}")
if mm == ps_markup:
    print(f"  → у {MERCHANT} НЕТ отдельной наценки → merchant_rate = PS rate = {stored}")
else:
    merchant_rate = (stored * mm / ps_markup).quantize(Decimal("0.001"))
    print(f"  → пересчёт: merchant_rate = {stored} × {mm}/{ps_markup} = {merchant_rate}")

agent = getattr(merchant, "agent", None)
agent_pct = Decimal(str(getattr(agent, "commission_percent", 0) or 0)) if agent else Decimal("0")
print(f"\nAgent: {getattr(getattr(agent, 'user', None), 'username', None) or '—'}  commission={agent_pct}%")

print(f"\nМаржа площадки (min={deal_margin_min_pct()}%) на amount={AMOUNT}:")
print(
    f"  формула: pnl = merchant_fee(mdr%) + (psp_usd − merchant_usd) − trader_fee − agent_fee"
)
for uname in TRADERS:
    trader = Trader.objects.select_related("user", "team").filter(user__username__iexact=uname).first()
    if trader is None:
        print(f"  {uname}: нет такого трейдера")
        continue
    team_rate = None
    if trader.team_id:
        team_rate = TraderTeamRates.objects.filter(team_id=trader.team_id, payment_system=ps).first()
    fx = quote_dual_fx(amount=AMOUNT, payment_system=ps, trader=trader, merchant=merchant)
    q = quote_deal_margin(amount=AMOUNT, payment_system=ps, trader=trader, merchant=merchant)
    tmdr = team_rate.mdr_in if team_rate else "—"
    pm = psp_fx_markup_for_trader(trader, fallback=mm)
    line = (
        f"  {uname:12} trader_mdr={tmdr}%  xe_psp={pm}  "
        f"rates m={fx.merchant_rate} t={fx.psp_rate}  "
        f"usd m={fx.merchant_usd} t={fx.psp_usd}"
    )
    if q is None:
        print(line + "  → cannot quote")
    else:
        print(
            line
            + f"\n               fees m={q.merchant_fee} t={q.trader_fee} agent={q.agent_fee} "
            f"fx_spread={q.fx_spread}  PLATFORM={q.platform_pnl} USDT ({q.platform_pct}%) ok={q.ok}"
        )

# Recent success sample
since = timezone.now() - timedelta(hours=HOURS)
orders = (
    InOrder.objects.filter(
        solution__merchant=merchant,
        creation_date__gte=since,
        status__name="Completed",
    )
    .select_related(
        "solution",
        "payment_details__group__trader__user",
        "status",
    )
    .order_by("-creation_date")[:30]
)
n_completed = InOrder.objects.filter(
    solution__merchant=merchant, creation_date__gte=since, status__name="Completed"
).count()
print(f"\nCompleted InOrder за {HOURS}h: {n_completed}")
by_trader = Counter()
samples = []
for order in orders:
    trader = getattr(getattr(getattr(order, "payment_details", None), "group", None), "trader", None)
    uname = getattr(getattr(trader, "user", None), "username", None) or "—"
    by_trader[uname] += 1
    if len(samples) < 8:
        mr = Decimal(str(order.merchant_rate or 0))
        pr = Decimal(str(order.psp_rate or 0))
        usd = Decimal(str(order.usd_amount or 0))
        psp_usd = Decimal(str(order.psp_usd_amount or 0))
        mfee = Decimal(str(order.merchant_fee or 0))
        tfee = Decimal(str(order.trader_fee or 0))
        afee = Decimal(str(order.agent_fee or 0))
        fx = _money(psp_usd - usd) if psp_usd else Decimal("0")
        pnl = _money(mfee + fx - tfee - afee)
        samples.append(
            f"  {order.creation_date} {order.amount} → {uname}  "
            f"m_rate={mr} psp_rate={pr} usd={usd} psp_usd={psp_usd}  "
            f"fees m={mfee} t={tfee} a={afee} fx={fx}  pnl≈{pnl}"
        )

print("  by trader:")
for name, n in by_trader.most_common():
    print(f"    {name}: {n}")
print("  samples:")
for line in samples:
    print(line)

print(
    f"""
=== Как читать ===
• «Ставка 8%» = MerchantSolution.mdr_in → комиссия с merchant_usd (не с fiat).
• Курс мерчанта = PS.usdt_exchange_rate, если нет ключа в XE_KZT_MARKUP_BY_MERCHANT.
  Сейчас default map только pandapay/aggrepay=1.04; {MERCHANT} → как PS (обычно xe+5 / {ps_markup}).
• Доходность площадки ≠ 8%:
    pnl = 8%×merchant_usd + (psp_usd−merchant_usd) − trader_mdr×psp_usd − agent%
  Если trader xe ниже мерчанта (напр. 1.03 vs 1.05) — fx_spread > 0 (плюс).
  Если trader_mdr высокий — 8% «съедается».
"""
)
print("Готово.")
