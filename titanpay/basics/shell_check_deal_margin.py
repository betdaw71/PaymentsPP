"""Проверка маржи merchant×trader на сумму (как в фильтре роутинга).

  docker compose exec -T \\
    -e MERCHANT=aggrepay -e TRADER=patriot1 -e AMOUNT=5000 -e PS=C2CKZT \\
    app python manage.py shell < titanpay/basics/shell_check_deal_margin.py
"""
from __future__ import annotations

import os
from decimal import Decimal

from basics.models import PaymentSystem, Trader
from merchant.models import Merchant
from payments.deal_margin import deal_margin_min_pct, quote_deal_margin

MERCHANT = (os.environ.get("MERCHANT") or "aggrepay").strip()
TRADER = (os.environ.get("TRADER") or "patriot1").strip()
AMOUNT = Decimal(str(os.environ.get("AMOUNT") or "5000"))
PS = (os.environ.get("PS") or "C2CKZT").strip()

merchant = Merchant.objects.select_related("user", "agent").filter(user__username__iexact=MERCHANT).first()
trader = Trader.objects.select_related("user", "team").filter(user__username__iexact=TRADER).first()
ps = PaymentSystem.objects.filter(name=PS).first()
if not all([merchant, trader, ps]):
    print(f"FAIL merchant={merchant} trader={trader} ps={ps}")
    raise SystemExit(1)

q = quote_deal_margin(amount=AMOUNT, payment_system=ps, trader=trader, merchant=merchant)
print(f"min_pct={deal_margin_min_pct()}%")
if q is None:
    print("cannot quote (no solution / no team rates)")
else:
    print(
        f"amount={q.amount} merchant_usd={q.merchant_usd} psp_usd={q.psp_usd}\n"
        f"rates m={q.merchant_rate} t={q.psp_rate}  mdr m={q.merchant_mdr}% t={q.trader_mdr}%\n"
        f"fees m={q.merchant_fee} t={q.trader_fee} agent={q.agent_fee} "
        f"tl={q.teamlead_share} (tl%{q.teamlead_pct}) fx={q.fx_spread}\n"
        f"PLATFORM pnl={q.platform_pnl} USDT  ({q.platform_pct}%)  ok={q.ok}"
    )
print("DONE")
