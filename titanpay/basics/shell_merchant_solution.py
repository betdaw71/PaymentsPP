"""Общий helper для shell-скриптов: MerchantSolution без get_or_create.

Не содержит run() — этот модуль только импортируют.
"""
from __future__ import annotations

from decimal import Decimal

from basics.models import PaymentSystem, TrafficType
from merchant.models import Merchant, MerchantSolution

DEFAULT_LIMITS = {
    "min_limit_in": Decimal("1000"),
    "max_limit_in": Decimal("500000"),
    "min_limit_out": Decimal("1000"),
    "max_limit_out": Decimal("500000"),
}


def ensure_merchant_solution(
    merchant: Merchant,
    ps: PaymentSystem,
    traffic: TrafficType,
    *,
    overwrite_limits: bool = False,
    limits: dict | None = None,
):
    """Один MerchantSolution на (merchant, ps, ftd). Дубликаты → status=2.

    overwrite_limits=True только для тестовых мерчантов. На проде не трогаем лимиты/MDR.
    """
    merchant.payment_systems.add(ps)
    limits = limits or DEFAULT_LIMITS
    for ftd in (False, True):
        sols = list(
            MerchantSolution.objects.filter(merchant=merchant, payment_system=ps, ftd=ftd)
        )
        if not sols:
            MerchantSolution.objects.create(
                merchant=merchant,
                payment_system=ps,
                ftd=ftd,
                status=1,
                traffic=traffic,
                mdr_in=Decimal("2.5"),
                mdr_out=Decimal("3.0"),
                autoclose_arbitrage=False,
                **limits,
            )
            print(f"  + MerchantSolution ftd={ftd} ps={ps.name}")
            continue

        keeper = max(sols, key=lambda s: (s.status == 1, s.max_limit_in or 0, s.mdr_in or 0))
        for dup in sols:
            if dup.pk == keeper.pk:
                continue
            if dup.status != 2:
                dup.status = 2
                dup.save(update_fields=["status"])
            print(
                f"  ! duplicate MerchantSolution ftd={ftd} ps={ps.name} "
                f"id={dup.id} → status=2 (kept {keeper.id})"
            )

        fields: list[str] = []
        if keeper.status != 1:
            keeper.status = 1
            fields.append("status")
        if overwrite_limits:
            keeper.traffic = traffic
            keeper.min_limit_in = limits["min_limit_in"]
            keeper.max_limit_in = limits["max_limit_in"]
            fields.extend(["traffic", "min_limit_in", "max_limit_in"])
        if fields:
            keeper.save(update_fields=list(dict.fromkeys(fields)))
        print(f"  ~ MerchantSolution ftd={ftd} ps={ps.name} id={keeper.id}")
