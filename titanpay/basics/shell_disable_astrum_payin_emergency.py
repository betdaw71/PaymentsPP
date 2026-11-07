"""СРОЧНО: выключить Astrum pay-in группы (невыдачи).

  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_disable_astrum_payin_emergency.py
"""
from __future__ import annotations

import os

from django.conf import settings

from basics.models import PaymentDetailsGroup, Trader
from payments.astrum_client import astrum_trader_username
from payments.psp_payin import parse_routing_share_map

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}


def run() -> None:
    username = (os.environ.get("TRADER_USERNAME") or astrum_trader_username() or "astrum_kzt").strip()
    share = parse_routing_share_map()
    print(f"=== EMERGENCY disable Astrum pay-in ({username}) APPLY={int(APPLY)} ===")
    print(f"SHARE now: {{{', '.join(f'{k}:{v}' for k, v in share.items())}}}" if share else "SHARE now: {}")
    if username.lower() in share:
        print(
            f"! {username} ЕЩЁ в PSP_ROUTING_SHARE_MAP — убери из .env и "
            "docker compose up -d app"
        )
    print(f"PSP_ROUTING_PRIORITY_MAP={getattr(settings, 'PSP_ROUTING_PRIORITY_MAP', '')}")

    trader = Trader.objects.filter(user__username__iexact=username).first()
    if trader is None:
        print(f"! trader {username} not found")
        return

    n = 0
    for g in PaymentDetailsGroup.objects.filter(trader=trader).select_related("payment_system"):
        ps = g.payment_system.name if g.payment_system_id else "?"
        print(f"  before {ps}: in_active={g.in_active} status={g.status}")
        if not APPLY:
            continue
        changed = []
        if g.in_active:
            g.in_active = False
            changed.append("in_active=False")
        if g.status == 1:
            g.status = 0
            changed.append("status=0")
        if changed:
            g.save()
            n += 1
            print(f"    + {changed}")
    if APPLY:
        print(f"DISABLED groups={n}")
    else:
        print("DRY_RUN. APPLY=1 to disable.")


run()
