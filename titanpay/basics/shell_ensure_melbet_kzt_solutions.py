"""
Prod melbet: MerchantSolution для C2CKZT — STD (ftd=False) и FTD (ftd=True).

Melbet API не передаёт ftd в теле запроса: используется только
MelbetIntegrationConfig.default_ftd при выборе решения.

Запуск:
  docker compose exec -T app python manage.py shell < titanpay/basics/shell_ensure_melbet_kzt_solutions.py

Переопределение MDR/лимитов (опционально):
  MELBET_KZT_MDR_IN=6.5 MELBET_KZT_MIN_IN=1000 ...
"""
from __future__ import annotations

import os
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction

from basics.models import Currency, PaymentSystem, TrafficType
from merchant.kzt_settlement import MELBET_USERNAME, ensure_kzt_balances
from merchant.models import Merchant, MerchantSolution
from payments.integrations.melbet.models import MelbetIntegrationConfig

MERCHANT_USERNAME = os.environ.get("MELBET_MERCHANT_USERNAME", MELBET_USERNAME)
PS_NAME = "C2CKZT"
TRAFFIC_NAME = "Standard"

DEFAULTS = {
    "mdr_in": Decimal(os.environ.get("MELBET_KZT_MDR_IN", "6.5")),
    "mdr_out": Decimal(os.environ.get("MELBET_KZT_MDR_OUT", "6.5")),
    "min_limit_in": Decimal(os.environ.get("MELBET_KZT_MIN_IN", "1000")),
    "max_limit_in": Decimal(os.environ.get("MELBET_KZT_MAX_IN", "1000000")),
    "min_limit_out": Decimal(os.environ.get("MELBET_KZT_MIN_OUT", "1000")),
    "max_limit_out": Decimal(os.environ.get("MELBET_KZT_MAX_OUT", "1000000")),
}


def _copy_from_existing(merchant: Merchant, ps: PaymentSystem) -> dict:
    ref = (
        MerchantSolution.objects.filter(merchant=merchant, payment_system=ps, status=1)
        .order_by("-ftd")
        .first()
    )
    if ref is None:
        return dict(DEFAULTS)
    return {
        "mdr_in": ref.mdr_in,
        "mdr_out": ref.mdr_out,
        "min_limit_in": ref.min_limit_in,
        "max_limit_in": ref.max_limit_in,
        "min_limit_out": ref.min_limit_out,
        "max_limit_out": ref.max_limit_out,
    }


def _pick_keeper(solutions: list[MerchantSolution]) -> MerchantSolution:
    def rank(s: MerchantSolution) -> tuple:
        return (s.status == 1, s.mdr_in, s.max_limit_in)

    return max(solutions, key=rank)


def _dedupe_and_ensure(
    merchant: Merchant,
    ps: PaymentSystem,
    traffic: TrafficType,
    ftd: bool,
    base: dict,
) -> tuple[MerchantSolution, bool]:
    """Один MerchantSolution на (merchant, ps, ftd); дубли → status=2."""
    qs = MerchantSolution.objects.filter(merchant=merchant, payment_system=ps, ftd=ftd)
    solutions = list(qs)

    if not solutions:
        sol = MerchantSolution.objects.create(
            merchant=merchant,
            payment_system=ps,
            ftd=ftd,
            status=1,
            traffic=traffic,
            autoclose_arbitrage=False,
            **base,
        )
        return sol, True

    keeper = _pick_keeper(solutions)
    for dup in solutions:
        if dup.pk == keeper.pk:
            continue
        if dup.status != 2:
            dup.status = 2
            dup.save(update_fields=["status"])
        print(f"  ! duplicate deactivated ftd={ftd} id={dup.id} (kept {keeper.id})")

    if keeper.status != 1:
        keeper.status = 1
    for field, value in base.items():
        setattr(keeper, field, value)
    keeper.traffic = traffic
    keeper.save()
    return keeper, False


@transaction.atomic
def run() -> None:
    print("=" * 60)
    print(f"Melbet KZT solutions — {MERCHANT_USERNAME} / {PS_NAME}")
    print("=" * 60)

    user = User.objects.filter(username=MERCHANT_USERNAME).first()
    if user is None or not hasattr(user, "merchant"):
        raise SystemExit(f"Merchant user {MERCHANT_USERNAME!r} not found")
    merchant = user.merchant

    currency = Currency.objects.filter(symbol="KZT").first()
    if currency is None:
        raise SystemExit("Currency KZT not found")
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=currency).first()
    if ps is None:
        raise SystemExit(f"PaymentSystem {PS_NAME} not found — create via melbet test shell or admin")

    ensure_kzt_balances(merchant)
    if not merchant.payment_systems.filter(pk=ps.pk).exists():
        merchant.payment_systems.add(ps)
        print(f"  + linked PS {PS_NAME} to merchant")
    else:
        print(f"  ~ PS {PS_NAME} already on merchant")

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    base = _copy_from_existing(merchant, ps)
    print(f"  ~ rates/limits template: mdr_in={base['mdr_in']}% limits_in={base['min_limit_in']}..{base['max_limit_in']}")

    for ftd, label in ((False, "STD (ftd=False)"), (True, "FTD (ftd=True)")):
        sol, created = _dedupe_and_ensure(merchant, ps, traffic, ftd, base)
        tag = "+" if created else "~"
        print(
            f"  {tag} {label} id={sol.id} status={sol.status} "
            f"mdr_in={sol.mdr_in}% [{sol.min_limit_in}..{sol.max_limit_in}]"
        )

    cfg = MelbetIntegrationConfig.objects.filter(merchant=merchant, active=True).first()
    if cfg is None:
        print("\n  ! MelbetIntegrationConfig not found — создайте в админке")
    else:
        print(f"\n  MelbetIntegrationConfig.default_ftd = {cfg.default_ftd}")
        print(
            "  → Все deposit Melbet сейчас идут в MerchantSolution с ftd="
            f"{cfg.default_ftd} (не смотрим на _ftd_/_ttd_ в callback_url)."
        )
        missing = []
        for ftd in (False, True):
            if not MerchantSolution.objects.filter(
                merchant=merchant, payment_system=ps, ftd=ftd, status=1
            ).exists():
                missing.append("STD" if not ftd else "FTD")
        if missing:
            print(f"  ! Нет активного решения: {', '.join(missing)}")
        elif cfg.default_ftd and not MerchantSolution.objects.filter(
            merchant=merchant, payment_system=ps, ftd=True, status=1
        ).exists():
            print("  ! default_ftd=True, но FTD solution отсутствует — будет 400")
        elif not cfg.default_ftd and not MerchantSolution.objects.filter(
            merchant=merchant, payment_system=ps, ftd=False, status=1
        ).exists():
            print("  ! default_ftd=False, но STD solution отсутствует — будет 400")

    print("\nГОТОВО. Проверка:")
    print(
        f"  python manage.py diagnose_routing --merchant {MERCHANT_USERNAME} "
        f"--ps {PS_NAME} --amount 5000"
    )


run()
