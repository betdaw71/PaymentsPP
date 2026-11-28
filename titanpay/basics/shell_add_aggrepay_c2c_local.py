"""Aggrepay: MerchantSolution C2C KZT, mdr_in=8.5, курс xe+5.

C2CKZT не меняет (там остаётся прежний MDR и xe+4).
Курс C2C для aggrepay зашит как xe+5, общий ключ aggrepay=1.04 на C2CKZT остаётся.
Явный aggrepay:c2c в XE_KZT_MARKUP_BY_MERCHANT перекрывает.

  docker compose exec -T app python manage.py shell \\
    < titanpay/basics/shell_add_aggrepay_c2c_local.py

  docker compose exec -T -e APPLY=1 app python manage.py shell \\
    < titanpay/basics/shell_add_aggrepay_c2c_local.py
"""
from __future__ import annotations

import os
from decimal import Decimal

from basics.models import Currency, PaymentSystem, TrafficType
from basics.utils import xe_kzt_markup_for_merchant
from merchant.models import Merchant, MerchantSolution

APPLY = (os.environ.get("APPLY") or "").strip().lower() in {"1", "true", "yes"}
USERNAME = (os.environ.get("MERCHANT") or "aggrepay").strip()
PS_NAME = (os.environ.get("PS") or "C2C").strip()
MDR_IN = Decimal(str(os.environ.get("MDR") or "8.5"))
TRAFFIC_NAME = (os.environ.get("TRAFFIC") or "Standard").strip()


def run() -> None:
    print(f"=== {USERNAME} {PS_NAME} KZT mdr_in={MDR_IN} APPLY={int(APPLY)} ===")
    print(f"markup C2C={xe_kzt_markup_for_merchant(USERNAME, 'C2C')} (1.05 = xe+5)")
    print(f"markup C2CKZT={xe_kzt_markup_for_merchant(USERNAME, 'C2CKZT')} (1.04 = xe+4)")

    merchant = Merchant.objects.filter(user__username__iexact=USERNAME).select_related("user").first()
    if merchant is None:
        print(f"FAIL: merchant {USERNAME} not found")
        return
    kzt = Currency.objects.filter(symbol="KZT").first()
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first() if kzt else None
    if ps is None:
        print(f"FAIL: PaymentSystem {PS_NAME} KZT not found")
        return
    traffic = TrafficType.objects.filter(name=TRAFFIC_NAME).first()
    if traffic is None:
        print(f"FAIL: traffic {TRAFFIC_NAME} not found")
        return

    donor = (
        MerchantSolution.objects.filter(
            merchant=merchant, payment_system__name="C2CKZT", payment_system__currency=kzt
        )
        .order_by("-max_limit_in")
        .first()
    )
    limits = {
        "min_limit_in": donor.min_limit_in if donor else Decimal("1000"),
        "max_limit_in": donor.max_limit_in if donor else Decimal("1000000"),
        "min_limit_out": donor.min_limit_out if donor else Decimal("1000"),
        "max_limit_out": donor.max_limit_out if donor else Decimal("1000000"),
    }
    print(f"limits from {'C2CKZT' if donor else 'defaults'}: {limits}")

    existing = list(
        MerchantSolution.objects.filter(merchant=merchant, payment_system=ps).select_related("traffic")
    )
    for sol in existing:
        tname = getattr(getattr(sol, "traffic", None), "name", None)
        print(
            f"  have id={sol.id} ftd={sol.ftd} status={sol.status} "
            f"mdr_in={sol.mdr_in} traffic={tname}"
        )
        if not APPLY:
            continue
        fields = []
        if sol.mdr_in != MDR_IN:
            sol.mdr_in = MDR_IN
            fields.append("mdr_in")
        if sol.status != 1:
            sol.status = 1
            fields.append("status")
        if fields:
            sol.save(update_fields=fields)
            print(f"    wrote {fields}")

    have_ftd = {sol.ftd for sol in existing if getattr(getattr(sol, "traffic", None), "name", None) == TRAFFIC_NAME}
    for ftd in (False, True):
        if ftd in have_ftd:
            continue
        print(f"  missing ftd={ftd} traffic={TRAFFIC_NAME}")
        if not APPLY:
            continue
        sol = MerchantSolution.objects.create(
            status=1,
            payment_system=ps,
            merchant=merchant,
            traffic=traffic,
            ftd=ftd,
            mdr_in=MDR_IN,
            mdr_out=Decimal("0"),
            **limits,
        )
        print(f"    + solution {sol.id}")

    if not APPLY:
        print("dry-run. APPLY=1 запишет mdr и недостающие ftd.")
    print("DONE")


run()
