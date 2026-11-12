"""Включить Astrum (asterisk) pay-in: группы + MDR 6%, баланс может уходить в минус (credit).

Перед этим:
  1) git pull && docker compose up -d --build app
  2) astrum_probe должен быть НЕ 403
  3) в .env share с astrum_kzt, например:
     PSP_ROUTING_SHARE_MAP={"gipay1":10,"patriot1":25,"visionx1":30,"prochub1":5,"astrum_kzt":30}

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_enable_astrum_payin.py

  APPLY=1 — записать группы/credit/mdr.
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from basics.models import PaymentDetailsGroup, Trader, TraderTeamRates
from payments.astrum_client import astrum_trader_username
from payments.psp_payin import parse_routing_share_map

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
TARGET_MDR = Decimal(str(os.environ.get("MDR") or "6.00"))
WANT_CREDIT = Decimal(str(os.environ.get("CREDIT") or "50000"))
SHARE_HINT = '{"gipay1":10,"patriot1":25,"visionx1":30,"prochub1":5,"astrum_kzt":30}'


def run() -> None:
    username = (os.environ.get("TRADER_USERNAME") or astrum_trader_username() or "astrum_kzt").strip()
    share = parse_routing_share_map()
    print(f"=== Enable Astrum pay-in ({username}) APPLY={int(APPLY)} ===")
    print(f"SHARE now: {{{', '.join(f'{k}:{v}' for k, v in share.items())}}}" if share else "SHARE now: {}")
    print(f"нужно в .env: PSP_ROUTING_SHARE_MAP={SHARE_HINT}")
    if username.lower() not in share:
        print(f"! {username} нет в SHARE — после APPLY группы ON, но lottery его не возьмёт")

    api_ok = bool((getattr(settings, "ASTRUM_API_KEY", None) or "").strip())
    key_ok = bool((getattr(settings, "ASTRUM_PRIVATE_KEY", None) or "").strip())
    mt = (getattr(settings, "ASTRUM_METHOD_TYPE_ID", None) or "").strip()
    print(f"ASTRUM_API_KEY={int(api_ok)} PRIVATE_KEY={int(key_ok)} METHOD_TYPE_ID={mt or '-'}")
    if not api_ok or not key_ok:
        print("! нет API key / private key — create pay-in упадёт, пойдёт fallback")
    if not mt:
        print("! ASTRUM_METHOD_TYPE_ID пустой — поставь id из: python manage.py astrum_probe --methods")

    trader = (
        Trader.objects.filter(user__username__iexact=username)
        .select_related("user", "team", "balance_usdt")
        .first()
    )
    if trader is None:
        print(f"! trader {username} not found")
        return

    bal = Decimal(str(trader.balance_usdt.amount if trader.balance_usdt_id else 0))
    credit = Decimal(str(getattr(trader, "credit_limit", 0) or 0))
    print(f"blocked={int(trader.blocked)} bal={bal} credit={credit} avail≈{bal+credit}")

    if APPLY:
        if trader.blocked:
            trader.blocked = False
            trader.save(update_fields=["blocked"])
            print("+ unblocked")
        if credit < WANT_CREDIT:
            trader.credit_limit = WANT_CREDIT
            trader.save(update_fields=["credit_limit"])
            print(f"+ credit {credit} -> {WANT_CREDIT}")

    for g in PaymentDetailsGroup.objects.filter(trader=trader).select_related(
        "payment_system", "payment_system__currency"
    ):
        ps = g.payment_system
        cur = ps.currency.symbol if ps and ps.currency_id else "?"
        print(f"  before {ps.name if ps else '?'}/{cur}: in={g.in_active} st={g.status}")
        if not APPLY:
            continue
        changed = []
        if not g.in_active:
            g.in_active = True
            changed.append("in_active")
        if g.status != 1:
            g.status = 1
            changed.append("status")
        if changed:
            g.auto_live = timezone.now()
            g.save()
            print(f"    + {changed}")

        if trader.team_id and ps is not None:
            rate, created = TraderTeamRates.objects.get_or_create(
                team=trader.team,
                payment_system=ps,
                defaults={"mdr_in": TARGET_MDR, "mdr_out": Decimal("2.5")},
            )
            if not created and rate.mdr_in != TARGET_MDR:
                print(f"    mdr {rate.mdr_in}% -> {TARGET_MDR}%")
                rate.mdr_in = TARGET_MDR
                rate.save(update_fields=["mdr_in"])
            else:
                print(f"    mdr={rate.mdr_in}%")

    print("\nПосле APPLY: при ошибке Astrum (403/нет реквизита) каскад уходит на следующих PSP.")
    print("  diagnose_routing mostbet --ps C2CKZT --amount 5000 --ftd false")
    print("  astrum_probe --info --balance --methods")
    if not APPLY:
        print("DRY_RUN. APPLY=1 to enable.")


run()
