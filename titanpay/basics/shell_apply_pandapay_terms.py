"""Pandapay: MDR 7.20% на C2CKZT/C2C + напоминание про xe+4 и каскад.

Курс xe+4 и каскад — через .env (см. вывод). Этот скрипт только mdr_in.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_apply_pandapay_terms.py

  APPLY=1 — записать mdr_in=7.20
"""
from __future__ import annotations

import os
from decimal import Decimal

from merchant.models import Merchant, MerchantSolution

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
MERCHANT = (os.environ.get("MERCHANT") or "pandapay").strip()
TARGET_MDR = Decimal(str(os.environ.get("MDR") or "7.20"))
PS_NAMES = tuple(
    p.strip()
    for p in (os.environ.get("PS") or "C2CKZT,C2C").split(",")
    if p.strip()
)


def run() -> None:
    print(f"APPLY={int(APPLY)}  merchant={MERCHANT}  mdr→{TARGET_MDR}  ps={PS_NAMES}")
    merchant = (
        Merchant.objects.select_related("user", "agent")
        .filter(user__username__iexact=MERCHANT)
        .first()
    )
    if merchant is None:
        print("! merchant not found")
        return
    agent = getattr(merchant, "agent", None)
    agent_pct = getattr(agent, "commission_percent", None) if agent else 0
    print(f"  agent={agent_pct}%")

    sols = (
        MerchantSolution.objects.filter(
            merchant=merchant,
            payment_system__name__in=PS_NAMES,
        )
        .select_related("payment_system", "traffic")
        .order_by("payment_system__name", "ftd", "id")
    )
    n = 0
    for sol in sols:
        # мусорные/выключенные лимиты не трогаем по умолчанию
        weird = sol.mdr_in == 0 or (
            sol.max_limit_in is not None
            and sol.min_limit_in is not None
            and sol.max_limit_in < sol.min_limit_in
        )
        mark = " SKIP weird" if weird else ""
        if weird:
            print(
                f"  {sol.payment_system.name} ftd={sol.ftd} "
                f"mdr={sol.mdr_in} limits={sol.min_limit_in}…{sol.max_limit_in}{mark}"
            )
            continue
        n += 1
        if sol.mdr_in != TARGET_MDR:
            print(
                f"  {sol.payment_system.name} ftd={sol.ftd} "
                f"{sol.mdr_in}% → {TARGET_MDR}%  "
                f"limits={sol.min_limit_in}…{sol.max_limit_in}"
            )
            if APPLY:
                sol.mdr_in = TARGET_MDR
                sol.save(update_fields=["mdr_in"])
        else:
            print(
                f"  {sol.payment_system.name} ftd={sol.ftd} "
                f"{sol.mdr_in}% (ok)  limits={sol.min_limit_in}…{sol.max_limit_in}"
            )
    print(f"  solutions touched/listed (non-weird)={n}")
    print(
        "\n.env (уже дефолт в settings, проверь на сервере):\n"
        '  XE_KZT_MARKUP_BY_MERCHANT={"pandapay":"1.04"}\n'
        '  PSP_ROUTING_PRIORITY_BY_MERCHANT='
        '{"pandapay":{"patriot1":1,"gipay1":2,"payplat1":3,'
        '"prochub1":4,"layerone1":5,"plutus1":6}}\n'
        "\nПроверка каскада:\n"
        "  python manage.py diagnose_routing pandapay --ps C2CKZT --amount 7010 --ftd false"
    )
    print("DONE")


run()
