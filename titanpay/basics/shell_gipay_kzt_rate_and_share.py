"""
GiPay KZT: ставка трейдера под договор 5.7% @ XE+4 при платформенном XE+5.

  наша наценка курса +1 п.п. относительно GiPay → mdr_in = 5.7 − 1.0 = 4.7%
  доля трафика 20% — через .env PSP_ROUTING_SHARE_MAP (этот скрипт .env не пишет).

Просмотр:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_gipay_kzt_rate_and_share.py

Ставка 4.7% на C2C/C2CKZT (KZT):
  docker compose exec -T -e APPLY=1 app python manage.py shell < titanpay/basics/shell_gipay_kzt_rate_and_share.py
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.conf import settings

from basics.models import Trader, TraderTeamRates
from basics.utils import xe_kzt_markup_for_ps
from payments.gipay_client import gipay_trader_username
from payments.psp_payin import parse_routing_share_map

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
TRADER_USERNAME = (os.environ.get("TRADER_USERNAME") or gipay_trader_username() or "gipay1").strip()
NEW_MDR = Decimal(os.environ.get("MDR_IN") or "4.70")
PROD_PS = ("C2C", "C2CKZT")
PROD_CURRENCY = "KZT"
GIPAY_FEE = Decimal("5.70")
GIPAY_XE = Decimal("1.04")  # XE+4
PLATFORM_XE_EXPECTED = Decimal("1.05")  # XE+5
SHARE_LINE = '{"gipay1": 20, "payplat1": 80}'


def _xe_pp(markup: Decimal) -> Decimal:
    return (markup - Decimal("1")) * Decimal("100")


def run() -> None:
    trader = (
        Trader.objects.select_related("user", "team")
        .get(user__username=TRADER_USERNAME)
    )
    team = trader.team
    rows = list(
        TraderTeamRates.objects.filter(team=team).select_related(
            "payment_system", "payment_system__currency"
        )
    )
    xe_c2ckzt = xe_kzt_markup_for_ps("C2CKZT")
    xe_c2c = xe_kzt_markup_for_ps("C2C")
    share = parse_routing_share_map()

    print(f"trader={TRADER_USERNAME}  team={team.name}  APPLY={int(APPLY)}")
    print(f"contract: GiPay {GIPAY_FEE}% @ XE+{_xe_pp(GIPAY_XE):.0f}")
    print(
        f"platform XE C2CKZT={xe_c2ckzt} (+{_xe_pp(xe_c2ckzt):.0f}%)  "
        f"C2C={xe_c2c} (+{_xe_pp(xe_c2c):.0f}%)"
    )
    if xe_c2ckzt == PLATFORM_XE_EXPECTED:
        print(f"target mdr_in={NEW_MDR}%  (= {GIPAY_FEE} − 1.0 fx spread)")
    else:
        print(
            f"WARN: C2CKZT markup is {xe_c2ckzt}, not {PLATFORM_XE_EXPECTED}. "
            f"Формула 4.7% рассчитана под XE+5."
        )
    print(f"team.rate_in={team.rate_in}%")
    print("TraderTeamRates:")
    for r in rows:
        cur = r.payment_system.currency.symbol if r.payment_system.currency_id else "?"
        mark = ""
        if r.payment_system.name in PROD_PS and cur == PROD_CURRENCY:
            mark = "  <- prod"
        print(f"  {r.payment_system.name:12} {cur:4} mdr_in={r.mdr_in}% mdr_out={r.mdr_out}%{mark}")
    print(f"PSP_ROUTING_SHARE_MAP now: {share or '{}'}")
    print(f"нужно в .env: PSP_ROUTING_SHARE_MAP={SHARE_LINE}")
    print("  (только gipay1:20 нельзя — тогда первый слот всегда GiPay)")
    print("после правки .env: docker compose up app -d")

    if not APPLY:
        print("\nDRY_RUN. Ставка: docker compose exec -T -e APPLY=1 app python manage.py shell < titanpay/basics/shell_gipay_kzt_rate_and_share.py")
        return

    changed = 0
    if team.rate_in != NEW_MDR:
        team.rate_in = NEW_MDR
        team.save(update_fields=["rate_in"])
        print(f"+ team.rate_in={NEW_MDR}%")
        changed += 1
    else:
        print(f"~ team.rate_in already {NEW_MDR}%")
    for r in rows:
        cur = r.payment_system.currency.symbol if r.payment_system.currency_id else "?"
        if r.payment_system.name not in PROD_PS or cur != PROD_CURRENCY:
            continue
        if r.mdr_in == NEW_MDR:
            print(f"~ mdr_in {r.payment_system.name} {cur} already {NEW_MDR}%")
            continue
        r.mdr_in = NEW_MDR
        r.save(update_fields=["mdr_in"])
        print(f"+ mdr_in {r.payment_system.name} {cur} = {NEW_MDR}%")
        changed += 1
    print(f"APPLY done, rows/fields updated={changed}")


run()
