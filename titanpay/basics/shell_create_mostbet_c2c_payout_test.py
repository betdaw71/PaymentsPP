"""
Тестовый трейдер + группа pay-out C2C (KZT) для мерчанта mostbet.

Проблема: matching groups: 0 / out_active на C2C — pay-out Declined.

Запуск на сервере:
  docker compose exec -T app python manage.py shell < basics/shell_create_mostbet_c2c_payout_test.py

После run() в .env на сервере (и rebuild app):
  LIVENESS_EXEMPT_TRADER_USERNAMES=mostbet_c2c_out_test

Опционально: Head support → controlled_teams → «Mostbet C2C Payout Test»
"""
from __future__ import annotations

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

TEAM_NAME = "Mostbet C2C Payout Test"
TRADER_USERNAME = "mostbet_c2c_out_test"
TRADER_PASSWORD = "ChangeMe_Mostbet_Out_1!"
TRADER_EMAIL = "mostbet_c2c_out_test@example.com"
GROUP_OWNER = "Mostbet C2C payout test drop"
TRAFFIC_NAME = "Standard"
PS_NAME = "C2C"
MERCHANT_USERNAME = "mostbet"


def _unique_card() -> str:
    card = "4" + uuid.uuid4().hex[:15]
    return "".join(c for c in card if c.isdigit())[:16].ljust(16, "0")


def _unique_deposit_number() -> str:
    return str(uuid.uuid4().int % 10**20).zfill(20)


def ensure_payout_group(trader, currency, payment_system, traffic) -> PaymentDetailsGroup:
    group = PaymentDetailsGroup.objects.filter(
        trader=trader, payment_system=payment_system, currency=currency
    ).first()
    if group is None:
        group = PaymentDetailsGroup.objects.create(
            owner=GROUP_OWNER,
            trader=trader,
            currency=currency,
            payment_system=payment_system,
            status=1,
            amount=Decimal("9999999"),
            in_active=False,
            out_active=True,
            min_amount_out=Decimal("20000"),
            max_amount_out=Decimal("500000"),
            work_type="by_card",
            deposit_number_on=False,
            auto_live=timezone.now(),
            limit_per_period=Decimal("50000000"),
        )
        group.allowed_traffic.add(traffic)
        print(f"  + group {group.id}")
    else:
        group.status = 1
        group.out_active = True
        group.amount = max(group.amount, Decimal("9999999"))
        group.min_amount_out = Decimal("20000")
        group.max_amount_out = Decimal("500000")
        group.deposit_number_on = False
        group.auto_live = timezone.now()
        group.save()
        if not group.allowed_traffic.filter(pk=traffic.pk).exists():
            group.allowed_traffic.add(traffic)
        print(f"  ~ group {group.id} (out_active=True)")

    if not PaymentDetails.objects.filter(
        group=group, status=1, card_number__isnull=False, sberpay_enabled=False, sbp_enabled=False
    ).exists():
        card = _unique_card()
        PaymentDetails.objects.create(
            group=group,
            status=1,
            amount=Decimal("9999999"),
            card_number=card,
            deposit_number=_unique_deposit_number(),
            sberpay_enabled=False,
            sbp_enabled=False,
        )
        print(f"  + card ****{card[-4:]}")
    else:
        print("  ~ card already present")

    return group


def run():
    print("=== Mostbet C2C pay-out test trader ===")
    kzt = Currency.objects.filter(symbol="KZT").first()
    if kzt is None:
        raise SystemExit("Currency KZT not found")
    ps = PaymentSystem.objects.filter(name=PS_NAME, currency=kzt).first()
    if ps is None:
        raise SystemExit(f"PaymentSystem {PS_NAME} (KZT) not found")

    traffic, _ = TrafficType.objects.get_or_create(name=TRAFFIC_NAME, defaults={"risk_level": 0})
    team, _ = TraderTeam.objects.get_or_create(
        name=TEAM_NAME, defaults={"rate_in": Decimal("5"), "rate_out": Decimal("2")}
    )
    TraderTeamRates.objects.get_or_create(
        team=team, payment_system=ps, defaults={"mdr_in": Decimal("5"), "mdr_out": Decimal("2.5")}
    )

    lang = Language.objects.first() or Language.objects.create(name="Russian")
    user, created = User.objects.get_or_create(
        username=TRADER_USERNAME,
        defaults={"email": TRADER_EMAIL, "first_name": "Mostbet payout test"},
    )
    if created:
        user.set_password(TRADER_PASSWORD)
        user.save()
        print(f"  + user {TRADER_USERNAME}")

    trader = Trader.objects.filter(user=user).first()
    if trader is None:
        bal = Balance.objects.create(type=0, amount=Decimal("5000"))
        fr = Balance.objects.create(type=1, amount=Decimal("0"))
        trader = Trader.objects.create(
            user=user,
            language=lang,
            team=team,
            balance_usdt=bal,
            frozen_balance_usdt=fr,
            currency=kzt,
            is_boss=False,
            blocked=False,
        )
        print(f"  + trader {TRADER_USERNAME} (USDT 5000 on balance)")
    else:
        trader.blocked = False
        trader.team = team
        trader.save(update_fields=["blocked", "team"])
        if trader.balance_usdt.amount < Decimal("100"):
            trader.balance_usdt.amount = Decimal("5000")
            trader.balance_usdt.save(update_fields=["amount"])
        print(f"  ~ trader {TRADER_USERNAME}")

    group = ensure_payout_group(trader, kzt, ps, traffic)

    from merchant.models import Merchant, MerchantSolution

    m = Merchant.objects.filter(user__username=MERCHANT_USERNAME).first()
    if m:
        sol = MerchantSolution.objects.filter(
            merchant=m, payment_system=ps, ftd=False, status=1
        ).first()
        if sol:
            print(
                f"  merchant {MERCHANT_USERNAME}: pay-out [{sol.min_limit_out} .. {sol.max_limit_out}] "
                f"traffic={sol.traffic.name}"
            )
        else:
            print(f"  ! no MerchantSolution C2C ftd=false for {MERCHANT_USERNAME}")

    print("\nDone.")
    print(f"  1) .env: LIVENESS_EXEMPT_TRADER_USERNAMES={TRADER_USERNAME}")
    print("     docker compose up -d app  (перечитать env)")
    print("  2) Head support: controlled_teams →", TEAM_NAME)
    print("  3) Проверка роутинга 57000 KZT:")
    print(
        "     docker compose exec -T app python manage.py shell -c "
        "\"from decimal import Decimal; from trade.utils import choose_trader_out; "
        "from basics.models import PaymentSystem; from merchant.models import MerchantSolution, Merchant; "
        "m=Merchant.objects.get(user__username='mostbet'); "
        "sol=MerchantSolution.objects.get(merchant=m,payment_system__name='C2C',ftd=False,status=1); "
        "ps=sol.payment_system; d,usd,ok=choose_trader_out(Decimal('57000'),ps,sol.traffic); "
        "print('ok',ok,'trader', d.group.trader.user.username if d else None)\""
    )
    print(f"  group_id={group.id}")


if __name__ == "__main__":
    run()
else:
    print("Run: run()")
