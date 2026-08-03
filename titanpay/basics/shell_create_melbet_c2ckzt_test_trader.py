"""
Локальный тестовый трейдер C2CKZT для melbet_test (без ExpayOne/Protocol API).

Не входит в PSP_TRADER_USERNAMES — заявки можно завершать вручную/shell (complete_after_new).

Роутинг:
  - по умолчанию: группа с наименьшим current_volume (не рандом между трейдерами);
  - на стенде: MELBET_KZT_TEST_TRADER_USERNAME=melbet_c2ckzt_test в .env → всегда этот трейдер.

Запуск:
  docker compose exec app python manage.py shell -c "exec(open('basics/shell_create_melbet_c2ckzt_test_trader.py').read()); run()"

После run() в .env app:
  MELBET_KZT_TEST_TRADER_USERNAME=melbet_c2ckzt_test

  docker compose up -d app
"""
from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone

from basics.models import (
    Balance,
    Currency,
    Language,
    PaymentDetails,
    PaymentDetailsGroup,
    PaymentSystem,
    Trader,
    TraderTeam,
    TraderTeamRates,
    TrafficType,
)

TEAM_NAME = "Melbet KZT Test"
TRADER_USERNAME = "melbet_c2ckzt_test"
DEFAULT_PASSWORD = "MelbetTrader_Test_2026!"
TRADER_EMAIL = "melbet-c2ckzt-test@example.local"
TRAFFIC_NAME = "Standard"
PS_NAME = "C2CKZT"
DEFAULT_AVAILABLE_USDT = Decimal("50000")
DEFAULT_FROZEN_USDT = Decimal("0")


def _virtual_card() -> str:
    card = "5" + uuid.uuid4().hex[:15]
    return "".join(c for c in card if c.isdigit())[:16].ljust(16, "0")


def ensure_group(trader: Trader, currency: Currency, payment_system: PaymentSystem, traffic: TrafficType) -> PaymentDetailsGroup:
    group = PaymentDetailsGroup.objects.filter(trader=trader, payment_system=payment_system).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner="Melbet test trader C2CKZT",
            trader=trader,
            currency=currency,
            payment_system=payment_system,
            status=1,
            amount=Decimal("9999999"),
            in_active=True,
            out_active=True,
            min_amount_out=Decimal("1000"),
            max_amount_out=Decimal("5000000"),
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            current_volume=Decimal("0"),
            current_out_volume=Decimal("0"),
            limit_per_period=Decimal("999999999"),
        )
        group.allowed_traffic.add(traffic)
        PaymentDetails.objects.create(
            group=group,
            status=1,
            amount=Decimal("9999999"),
            card_number=_virtual_card(),
            deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        print(f"  + PaymentDetailsGroup {group.id}")
    else:
        group.status = 1
        group.in_active = True
        group.out_active = True
        group.deposit_number_on = False
        group.work_type = "by_card"
        group.min_amount_out = Decimal("1000")
        group.max_amount_out = Decimal("5000000")
        group.current_volume = Decimal("0")
        group.current_out_volume = Decimal("0")
        group.limit_per_period = Decimal("999999999")
        group.amount = Decimal("9999999")
        group.auto_live = timezone.now()
        group.save()
        group.allowed_traffic.add(traffic)
        if not PaymentDetails.objects.filter(group=group, status=1).exists():
            PaymentDetails.objects.create(
                group=group,
                status=1,
                amount=Decimal("9999999"),
                card_number=_virtual_card(),
                deposit_number=str(uuid.uuid4().int % 10**20).zfill(20),
                sberpay_enabled=False,
                sbp_enabled=False,
            )
        print(f"  ~ PaymentDetailsGroup {group.id} (volume reset)")
    return group


def fund_trader(
    trader: Trader,
    *,
    available_usdt: Decimal | str = DEFAULT_AVAILABLE_USDT,
    frozen_usdt: Decimal | str = DEFAULT_FROZEN_USDT,
) -> None:
    trader.balance_usdt.amount = Decimal(str(available_usdt))
    trader.frozen_balance_usdt.amount = Decimal(str(frozen_usdt))
    trader.balance_usdt.save(update_fields=["amount"])
    trader.frozen_balance_usdt.save(update_fields=["amount"])
    print(
        f"  USDT available={trader.balance_usdt.amount} frozen={trader.frozen_balance_usdt.amount}"
    )


def run(
    password: str = DEFAULT_PASSWORD,
    available_usdt: Decimal | str = DEFAULT_AVAILABLE_USDT,
    frozen_usdt: Decimal | str = DEFAULT_FROZEN_USDT,
) -> dict:
    print("=" * 60)
    print("Melbet C2CKZT local test trader (non-PSP)")
    print("=" * 60)

    lang = Language.objects.first() or Language.objects.create(name="Russian")
    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        kzt = Currency.objects.create(symbol="KZT", name="Kazakhstani Tenge")

    ps = PaymentSystem.objects.filter(name__iexact=PS_NAME, currency=kzt).first()
    if ps is None:
        raise RuntimeError(f"PaymentSystem {PS_NAME} not found — run shell_create_melbet_test_merchant.py first")

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME,
        defaults={"rate_in": Decimal("5"), "rate_out": Decimal("2.5")},
    )
    TraderTeamRates.objects.get_or_create(
        team=team,
        payment_system=ps,
        defaults={"mdr_in": Decimal("5"), "mdr_out": Decimal("2.5")},
    )

    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "Melbet C2CKZT Test"},
    )
    user.set_password(password)
    user.save()

    trader = Trader.objects.filter(user=user).first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=Decimal("0"))
        fr = Balance.objects.create(type=1, amount=Decimal("0"))
        trader = Trader.objects.create(
            user=user,
            language=lang,
            team=team,
            balance_usdt=bal,
            frozen_balance_usdt=fr,
            currency=kzt,
            is_boss=True,
            blocked=False,
        )
        print(f"  + Trader {TRADER_USERNAME}")
    else:
        trader.team = team
        trader.blocked = False
        trader.save(update_fields=["team", "blocked"])
        print(f"  ~ Trader {TRADER_USERNAME}")

    fund_trader(trader, available_usdt=available_usdt, frozen_usdt=frozen_usdt)
    group = ensure_group(trader, kzt, ps, traffic)

    result = {
        "username": TRADER_USERNAME,
        "password": password,
        "trader_id": str(trader.id),
        "group_id": str(group.id),
        "env_line": f"MELBET_KZT_TEST_TRADER_USERNAME={TRADER_USERNAME}",
    }

    print("\n" + "=" * 60)
    print("ГОТОВО")
    print("=" * 60)
    print(f"  Логин трейдера: {TRADER_USERNAME}")
    print(f"  Пароль:         {password}")
    print(f"  Добавьте в .env и перезапустите app:")
    print(f"    {result['env_line']}")
    print(f"    # опционально (уже учтён в коде, если задан MELBET_KZT_TEST_TRADER_USERNAME):")
    print(f"    LIVENESS_EXEMPT_TRADER_USERNAMES={TRADER_USERNAME}")
    print("  Затем: shell_melbet_kzt_order_demo.run() — заявки пойдут на этого трейдера.")
    print("  Complete без вызова ExpayOne: complete_payin() в demo shell или ЛК трейдера.")
    return result


if __name__ == "__main__":
    run()
else:
    print("Run: run() | fund_trader(trader, available_usdt='10000')")
